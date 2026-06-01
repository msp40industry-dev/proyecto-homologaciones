"""
build_graph.py — Construye el grafo KAG de relaciones entre CRs (Sección I).

Lee las 76 fichas CR del JSON parseado, extrae relaciones estructuradas del
campo `informacion_adicional` usando LLM + with_structured_output(), y guarda
el resultado en scripts_graph/graph.json.

Uso:
    python scripts_graph/build_graph.py                  # procesa todas las fichas
    python scripts_graph/build_graph.py --cr 2.1 5.1    # reprocesa solo estas CRs y hace merge
    python scripts_graph/build_graph.py --dry-run        # sin llamar al LLM
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from langchain_openai import ChatOpenAI

JSON_PATH   = ROOT / "json" / "fichas_cr_seccion1_v3.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "graph.json"

MODELO = os.environ.get("MODELO_RAZONAMIENTO", "gpt-4o")

# Fichas en paralelo — reducido para respetar el límite de TPM
MAX_CONCURRENTE = 2

# Reintentos ante rate limit (429)
MAX_REINTENTOS  = 4
BACKOFF_BASE    = 2.0   # segundos; se duplica en cada reintento


# ── Schema de extracción LLM ──────────────────────────────────────────────────

class RelacionCR(BaseModel):
    cr_destino: Optional[str] = Field(
        None,
        description=(
            "Código de la CR destino, ej. '2.9'. "
            "None si no hay CR asociada (incorporación física sin tramitar otra CR)."
        )
    )
    tipo: str = Field(
        ...,
        description=(
            "Tipo de relación: "
            "'implica_cr' — esta reforma implica tramitar también otra CR; "
            "'obliga_incorporar' — hay que incorporar algo físicamente (puede ser sin tramitar CR); "
            "'restriccion' — restricción, exención o condición que modifica la aplicación de esta CR."
        )
    )
    condicion: Optional[str] = Field(
        None,
        description=(
            "Condición bajo la que aplica esta relación (texto libre). "
            "None si aplica siempre, sin condición."
        )
    )
    sin_tramitar_cr: bool = Field(
        False,
        description=(
            "True si hay que incorporar físicamente algo pero sin tramitar la CR adicional asociada. "
            "Solo aplica cuando tipo='obliga_incorporar'."
        )
    )
    fuente_literal: str = Field(
        ...,
        description="Fragmento literal del texto del manual del que se extrajo esta relación."
    )


class RelacionesExtraidas(BaseModel):
    relaciones: list[RelacionCR] = Field(
        default_factory=list,
        description="Relaciones encontradas. Lista vacía si no hay ninguna."
    )


# ── Prompt ────────────────────────────────────────────────────────────────────

PROMPT_EXTRACCION = """\
Eres un experto en el Manual de Reformas de Vehículos DGT (España).

Analiza el campo INFORMACIÓN ADICIONAL de la ficha CR-{cr} y extrae \
ÚNICAMENTE las relaciones con otras CRs o con elementos que deban \
incorporarse físicamente al vehículo.

Tipos de relaciones a extraer:
- implica_cr: esta reforma implica tramitar también otra CR (con o sin condición)
- obliga_incorporar: esta reforma obliga a incorporar físicamente algo en el vehículo \
(puede ser sin tramitar la CR asociada)
- restriccion: hay una restricción, exención o condición que limita o modifica \
la aplicación de esta CR (por fecha de matriculación, equipamiento de serie, \
categoría del vehículo, etc.)

Reglas estrictas:
1. Preserva en fuente_literal el fragmento exacto del texto del que extraes la relación.
2. Si la condición es explícita (ej: "si modifica la potencia máxima"), ponla en condicion.
3. Si el texto dice "sin tramitar el CR asociado" o expresión equivalente, \
marca sin_tramitar_cr=True.
4. Si no hay ninguna relación relevante, devuelve lista vacía.
5. No inventes relaciones que no estén en el texto.

---
CR-{cr} — {descripcion}

INFORMACIÓN ADICIONAL:
{informacion_adicional}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _limpiar_fecha(fecha_revision: str) -> str:
    """'Junio 2022 Página 1 de 2' → 'Junio 2022'"""
    return fecha_revision.split("Página")[0].strip()


def _revision_fuente(ficha: dict) -> str:
    fecha = _limpiar_fecha(ficha.get("fecha_revision", ""))
    revision = ficha.get("revision", "")
    return f"{revision} - {fecha}" if fecha else revision


def _ars_por_categoria(actos_reglamentarios: list) -> tuple[dict, list[str]]:
    """
    Transforma la lista de ARs en:
      - dict {categoria: [ARs aplicables]}
      - list de categorías bloqueadas (X = reforma imposible en esa categoría)

    Valores del preámbulo (Apartado 4):
      (1), (2), (3) → AR aplicable con esa modalidad
      -             → AR no aplica a esa categoría
      X             → Reforma IMPOSIBLE en esa categoría (coincide con NO en campo aplicación)
    """
    resultado: dict[str, list] = {}
    bloqueadas: set[str] = set()

    for ar in actos_reglamentarios:
        for cat, nivel in ar.get("aplicabilidad", {}).items():
            if not nivel:
                continue
            nivel_limpio = nivel.strip()
            if nivel_limpio.upper() == "X":
                bloqueadas.add(cat)
            elif nivel_limpio not in ("", "-"):
                resultado.setdefault(cat, []).append({
                    "sistema": ar.get("sistema", ""),
                    "referencia": ar.get("referencia", ""),
                    "nivel": nivel_limpio,
                })

    return resultado, sorted(bloqueadas)


def _requiere_proyecto(ficha: dict) -> bool:
    return ficha.get("documentacion_necesaria", {}).get("Proyecto Técnico", "NO") == "SI"


def _nodo_desde_ficha(ficha: dict) -> dict:
    ars, bloqueadas = _ars_por_categoria(ficha.get("actos_reglamentarios", []))
    return {
        "codigo": ficha["cr"],
        "descripcion": ficha.get("descripcion_cr", ""),
        "via": ficha.get("via_tramitacion", ""),
        "categorias_aplicables": ficha.get("categorias_aplicables", []),
        "categorias_bloqueadas": bloqueadas,
        "requiere_proyecto": _requiere_proyecto(ficha),
        "revision_fuente": _revision_fuente(ficha),
        "ars_por_categoria": ars,
    }


# ── Extracción LLM con reintentos ─────────────────────────────────────────────

async def _extraer_relaciones(
    ficha: dict,
    llm_con_schema,
    semaforo: asyncio.Semaphore,
) -> list[dict]:
    """Llama al LLM con reintentos exponenciales ante 429."""
    informacion_adicional = ficha.get("informacion_adicional") or ""
    if not informacion_adicional.strip():
        return []

    prompt = PROMPT_EXTRACCION.format(
        cr=ficha["cr"],
        descripcion=ficha.get("descripcion_cr", ""),
        informacion_adicional=informacion_adicional,
    )

    ultimo_error = None
    for intento in range(MAX_REINTENTOS):
        try:
            async with semaforo:
                resultado: RelacionesExtraidas = await llm_con_schema.ainvoke(prompt)

            edges = []
            for rel in resultado.relaciones:
                edges.append({
                    "cr_origen": f"CR-{ficha['cr']}",
                    "cr_destino": f"CR-{rel.cr_destino}" if rel.cr_destino else None,
                    "tipo": rel.tipo,
                    "condicion": rel.condicion,
                    "sin_tramitar_cr": rel.sin_tramitar_cr,
                    "fuente_literal": rel.fuente_literal,
                })
            return edges

        except Exception as e:
            ultimo_error = e
            if "429" in str(e) or "rate_limit" in str(e).lower():
                espera = BACKOFF_BASE * (2 ** intento)
                print(f"  [429] CR-{ficha['cr']} — reintento {intento+1}/{MAX_REINTENTOS} en {espera:.0f}s")
                await asyncio.sleep(espera)
            else:
                raise  # error no recuperable

    raise RuntimeError(f"CR-{ficha['cr']} falló tras {MAX_REINTENTOS} reintentos: {ultimo_error}")


# ── Merge con grafo existente ─────────────────────────────────────────────────

def _cargar_grafo_existente() -> dict | None:
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    return None


def _merge(grafo_base: dict, nodos_nuevos: dict, edges_nuevos: list, crs_reprocesadas: list[str]) -> dict:
    """Actualiza el grafo base: reemplaza nodos y edges de las CRs reprocesadas."""
    nodos = dict(grafo_base["nodos"])
    nodos.update(nodos_nuevos)

    # Eliminar edges anteriores de las CRs reprocesadas y añadir los nuevos
    keys_reprocesadas = {f"CR-{cr}" for cr in crs_reprocesadas}
    edges = [
        e for e in grafo_base["edges"]
        if e["cr_origen"] not in keys_reprocesadas
    ]
    edges.extend(edges_nuevos)

    return {
        "version": grafo_base["version"],
        "generado": datetime.now().isoformat(timespec="seconds"),
        "manual": grafo_base["manual"],
        "nodos": nodos,
        "edges": edges,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

async def construir_grafo(crs_filtro: list[str] | None, dry_run: bool) -> None:
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    todas_las_fichas = data["fichas"]
    fichas = todas_las_fichas
    modo_merge = False

    if crs_filtro:
        fichas = [f for f in todas_las_fichas if f["cr"] in crs_filtro]
        modo_merge = OUTPUT_PATH.exists()
        print(f"Procesando {len(fichas)} ficha(s): {[f['cr'] for f in fichas]}")
        if modo_merge:
            print("  (modo merge — se actualiza el grafo existente)")
    else:
        print(f"Procesando {len(fichas)} fichas...")

    nodos_nuevos = {f"CR-{f['cr']}": _nodo_desde_ficha(f) for f in fichas}
    edges_nuevos: list[dict] = []

    if dry_run:
        print("[dry-run] Sin llamadas al LLM — edges vacíos.")
    else:
        llm = ChatOpenAI(model=MODELO, temperature=0)
        llm_con_schema = llm.with_structured_output(RelacionesExtraidas)
        semaforo = asyncio.Semaphore(MAX_CONCURRENTE)

        tareas = [_extraer_relaciones(f, llm_con_schema, semaforo) for f in fichas]
        resultados = await asyncio.gather(*tareas, return_exceptions=True)

        for ficha, resultado in zip(fichas, resultados):
            if isinstance(resultado, Exception):
                print(f"  [ERROR] CR-{ficha['cr']}: {resultado}")
            else:
                edges_nuevos.extend(resultado)
                n = len(resultado)
                if n:
                    print(f"  CR-{ficha['cr']}: {n} relación(es) extraída(s)")

    # Serializar (merge o grafo completo)
    if modo_merge:
        grafo_base = _cargar_grafo_existente()
        grafo = _merge(grafo_base, nodos_nuevos, edges_nuevos, crs_filtro)
    else:
        grafo = {
            "version": "1.0",
            "generado": datetime.now().isoformat(timespec="seconds"),
            "manual": {
                "fuente": data["metadata"]["fuente"],
                "revision": data["metadata"]["revision_manual"],
            },
            "nodos": {f"CR-{f['cr']}": _nodo_desde_ficha(f) for f in todas_las_fichas},
            "edges": edges_nuevos,
        }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(grafo, f, ensure_ascii=False, indent=2)

    print(f"\nGrafo guardado en {OUTPUT_PATH}")
    print(f"  Nodos : {len(grafo['nodos'])}")
    print(f"  Edges : {len(grafo['edges'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye el grafo KAG de relaciones entre CRs")
    parser.add_argument("--cr", nargs="+", metavar="CR", help="Reprocesar solo estas CRs y hacer merge con el grafo existente")
    parser.add_argument("--dry-run", action="store_true", help="Sin llamadas al LLM")
    args = parser.parse_args()

    asyncio.run(construir_grafo(
        crs_filtro=args.cr,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()

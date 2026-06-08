"""
build_graph.py — Construye el grafo KAG de relaciones entre CRs (todas las secciones).

Lee las fichas CR de los JSON parseados, extrae relaciones estructuradas del
campo `informacion_adicional` usando LLM + with_structured_output(), y guarda
el resultado en scripts_graph/graph.json.

Claves de nodo: CR-{seccion}-{cr}  ej. CR-I-5.1, CR-II-5.1, CR-III-5.1

Uso:
    python scripts_graph/build_graph.py                        # procesa todas las secciones
    python scripts_graph/build_graph.py --seccion I            # solo una sección
    python scripts_graph/build_graph.py --cr I:2.1 I:5.1      # reprocesa CRs concretas (merge)
    python scripts_graph/build_graph.py --dry-run              # sin llamar al LLM
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
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

JSON_PATH_I      = ROOT / "json" / "fichas_cr_seccion1_v3.json"
JSON_PATH_EXTRA  = ROOT / "json" / "fichas_cr_secciones_ii_iii_iv.json"
OUTPUT_PATH      = Path(__file__).resolve().parent / "graph.json"
NORMATIVAS_PATH  = ROOT / "json" / "normativas_ar.json"

# Detecta directivas/reglamentos EU en texto libre (excluye CEPE/ONU y ECE)
_PAT_AR_TEXTO = re.compile(
    r'\b(?:'
    r'\d{2,4}/\d+/C(?:EE|E)'                                # Directivas: 70/222/CEE, 97/27/CE
    r'|R(?:eglamento)?\s*\(UE\)\s*(?:N[oº°]\s*)?\d{4}/\d+' # R(UE) 168/2013, Reglamento (UE) 2019/2144
    r')',
    re.IGNORECASE,
)

# Referencias que NO son directivas EU y deben excluirse del inventario
_PAT_EXCLUIR_REF = re.compile(
    r'CEPE/ONU|(?:\bECE\b)|^ISO\b',
    re.IGNORECASE,
)

# Detecta un anexo al final de la referencia: "2001/85/CE (Anexo VII)"
_PAT_ANEXO = re.compile(r'\(\s*(Anexo[^)]+)\)\s*$', re.IGNORECASE)


def _normalizar_ref(ref: str) -> tuple[str, str | None]:
    """
    Devuelve (referencia_normalizada, anexo_o_None).

    - Extrae el anexo si lo hay:  '2001/85/CE (Anexo VII)'  → ('2001/85/CE', 'Anexo VII')
    - Añade la barra faltante:    '2003/97CE'               → ('2003/97/CE', None)
    """
    anexo: str | None = None
    m = _PAT_ANEXO.search(ref)
    if m:
        anexo = m.group(1).strip()
        ref = ref[:m.start()].strip()

    # Normalizar barra faltante antes de CE/CEE: "97CE" → "97/CE"
    ref = re.sub(r'(\d)(C(?:EE|E))\b', r'\1/\2', ref, flags=re.IGNORECASE)

    return ref, anexo

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
        "seccion": ficha.get("seccion", "I"),
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

            seccion = ficha.get("seccion", "I")
            edges = []
            for rel in resultado.relaciones:
                edges.append({
                    "cr_origen": f"CR-{seccion}-{ficha['cr']}",
                    # Las CRs referenciadas en informacion_adicional pertenecen a la misma sección
                    "cr_destino": f"CR-{seccion}-{rel.cr_destino}" if rel.cr_destino else None,
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

def _cargar_todas_las_fichas(seccion_filtro: str | None) -> list[dict]:
    """Carga fichas de todos los JSONs disponibles, opcionalmente filtrando por sección."""
    fichas: list[dict] = []

    with open(JSON_PATH_I, encoding="utf-8") as f:
        data_i = json.load(f)
    fichas.extend(data_i["fichas"])

    if JSON_PATH_EXTRA.exists():
        with open(JSON_PATH_EXTRA, encoding="utf-8") as f:
            data_extra = json.load(f)
        fichas.extend(data_extra["fichas"])

    if seccion_filtro:
        fichas = [f for f in fichas if f.get("seccion", "I") == seccion_filtro.upper()]

    return fichas


async def construir_grafo(
    crs_filtro: list[str] | None,
    seccion_filtro: str | None,
    dry_run: bool,
) -> None:
    todas_las_fichas = _cargar_todas_las_fichas(seccion_filtro)
    fichas = todas_las_fichas
    modo_merge = False

    # crs_filtro formato: "I:2.1" o "II:5.1"
    if crs_filtro:
        claves_filtro = set(crs_filtro)  # ej. {"I:2.1", "II:5.1"}
        fichas = [
            f for f in todas_las_fichas
            if f"{f.get('seccion','I')}:{f['cr']}" in claves_filtro
        ]
        modo_merge = OUTPUT_PATH.exists()
        print(f"Procesando {len(fichas)} ficha(s): {[f['cr'] for f in fichas]}")
        if modo_merge:
            print("  (modo merge — se actualiza el grafo existente)")
    else:
        print(f"Procesando {len(fichas)} fichas (sección: {seccion_filtro or 'todas'})...")

    def _clave(f: dict) -> str:
        return f"CR-{f.get('seccion','I')}-{f['cr']}"

    nodos_nuevos = {_clave(f): _nodo_desde_ficha(f) for f in fichas}
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
                print(f"  [ERROR] {_clave(ficha)}: {resultado}")
            else:
                edges_nuevos.extend(resultado)
                n = len(resultado)
                if n:
                    print(f"  {_clave(ficha)}: {n} relación(es) extraída(s)")

    # Serializar (merge o grafo completo)
    if modo_merge:
        grafo_base = _cargar_grafo_existente()
        crs_clave = [f"{f.get('seccion','I')}:{f['cr']}" for f in fichas]
        grafo = _merge(grafo_base, nodos_nuevos, edges_nuevos, crs_clave)
    else:
        grafo = {
            "version": "2.0",
            "generado": datetime.now().isoformat(timespec="seconds"),
            "manual": {
                "fuente": "Manual de Reformas de Vehículos — Todas las secciones",
                "revision": "7ª (Revisión 7.2)",
            },
            "nodos": {_clave(f): _nodo_desde_ficha(f) for f in todas_las_fichas},
            "edges": edges_nuevos,
        }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(grafo, f, ensure_ascii=False, indent=2)

    print(f"\nGrafo guardado en {OUTPUT_PATH}")
    print(f"  Nodos : {len(grafo['nodos'])}")
    print(f"  Edges : {len(grafo['edges'])}")
    # Desglose por sección
    por_sec: dict[str, int] = {}
    for k in grafo["nodos"]:
        sec = k.split("-")[1] if "-" in k else "?"
        por_sec[sec] = por_sec.get(sec, 0) + 1
    for sec in sorted(por_sec):
        print(f"  Sección {sec}: {por_sec[sec]} nodos")

    # Exportar inventario de normativas AR siempre que se construya o actualice el grafo
    _exportar_normativas(grafo)


def _exportar_normativas(grafo: dict) -> None:
    """
    Extrae referencias normativas EU únicas del grafo y guarda json/normativas_ar.json.

    Fuente 1 — tablas de ARs (nodos): estructuradas, deterministas.
    Fuente 2 — informacion_adicional (edges): texto libre; puede contener refs
               adicionales no presentes en las tablas.

    Se excluyen: CEPE/ONU, ECE, ISO (no son directivas EU consultables en EUR-Lex).
    Se normalizan: barra faltante ('2003/97CE' → '2003/97/CE').
    Se separan: anexos ('2001/85/CE (Anexo VII)' → ref + metadato 'anexo').
    """
    # referencia_normalizada → {secciones, fuentes, anexos}
    acumulado: dict[str, dict] = {}

    def _registrar(ref_raw: str, sec: str, fuente: str) -> None:
        if _PAT_EXCLUIR_REF.search(ref_raw):
            return
        ref, anexo = _normalizar_ref(ref_raw)
        if not ref:
            return
        entry = acumulado.setdefault(ref, {"secciones": set(), "fuentes": set(), "anexos": set()})
        entry["secciones"].add(sec)
        entry["fuentes"].add(fuente)
        if anexo:
            entry["anexos"].add(anexo)

    # 1. Tablas de ARs (nodos)
    for _, nodo in grafo["nodos"].items():
        sec = nodo.get("seccion", "I")
        for ars in nodo.get("ars_por_categoria", {}).values():
            for ar in ars:
                ref_raw = ar.get("referencia", "").strip()
                if ref_raw:
                    _registrar(ref_raw, sec, "tabla_ar")

    # 2. Texto libre de edges (informacion_adicional)
    for edge in grafo["edges"]:
        fuente_txt = edge.get("fuente_literal", "")
        sec = edge["cr_origen"].split("-")[1] if "-" in edge["cr_origen"] else "I"
        for m in _PAT_AR_TEXTO.finditer(fuente_txt):
            _registrar(m.group().strip(), sec, "informacion_adicional")

    todas = sorted(acumulado)
    solo_texto = [r for r in todas if acumulado[r]["fuentes"] == {"informacion_adicional"}]

    referencias = [
        {
            "referencia": ref,
            "fuentes":    sorted(acumulado[ref]["fuentes"]),
            "secciones":  sorted(acumulado[ref]["secciones"]),
            **({"anexos": sorted(acumulado[ref]["anexos"])} if acumulado[ref]["anexos"] else {}),
        }
        for ref in todas
    ]

    output = {
        "generado":       datetime.now().isoformat(timespec="seconds"),
        "total":          len(referencias),
        "desde_tabla_ar": sum(1 for r in todas if "tabla_ar" in acumulado[r]["fuentes"]),
        "solo_en_texto":  len(solo_texto),
        "referencias":    referencias,
    }

    with open(NORMATIVAS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nNormativas AR exportadas: {NORMATIVAS_PATH}")
    print(f"  Total referencias únicas : {len(referencias)}")
    print(f"  De tablas de ARs         : {output['desde_tabla_ar']}")
    print(f"  Solo en texto libre      : {len(solo_texto)}")
    if solo_texto:
        print(f"  Adicionales (texto)      : {solo_texto}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye el grafo KAG de relaciones entre CRs")
    parser.add_argument("--cr", nargs="+", metavar="SEC:CR",
                        help="Reprocesar CRs concretas (ej. I:2.1 II:5.1) y hacer merge")
    parser.add_argument("--seccion", choices=["I", "II", "III", "IV"],
                        help="Procesar solo una sección")
    parser.add_argument("--dry-run", action="store_true", help="Sin llamadas al LLM")
    args = parser.parse_args()

    asyncio.run(construir_grafo(
        crs_filtro=args.cr,
        seccion_filtro=args.seccion,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()

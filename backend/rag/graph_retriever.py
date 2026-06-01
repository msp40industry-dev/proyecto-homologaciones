"""
graph_retriever.py — Traversal del grafo KAG para enriquecer la identificación de CRs.

Complementa el retrieval semántico de ChromaDB con relaciones estructuradas extraídas
del campo informacion_adicional de cada ficha CR:

  - implica_cr       → CRs adicionales que deben tramitarse junto a la reforma
  - obliga_incorporar → elementos físicos a incorporar (sin tramitar CR adicional)
  - restriccion      → condiciones, exenciones o limitaciones para este vehículo concreto

Uso desde identificador_cr.py:
    from rag.graph_retriever import enriquecer_con_grafo

    resultado = await enriquecer_con_grafo(
        crs=["2.1", "5.1"],
        categoria="M1",
        descripcion_reforma="Instalación de turbo con aumento de potencia",
        fecha_matriculacion="15/03/2018",
    )
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

ROOT       = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "scripts_graph" / "graph.json"

MODELO = None   # se inicializa lazy desde config para no importar en tests


# Descripciones exactas del Apartado 4 del Preámbulo (Sección I)
DESCRIPCIONES_MODALIDAD: dict[str, str] = {
    "(1)": "El AR se aplica en su última actualización en vigor a fecha de tramitación de la reforma.",
    "(2)": (
        "El AR se aplica en la actualización en vigor en la fecha de primera matriculación del vehículo, "
        "si la homologación del mismo exige el AR incluido en la tabla. Si el AR no fuera exigido "
        "para la homologación del vehículo en la fecha de su primera matriculación, se aplicará al "
        "menos el AR en la primera versión incluida en el Real Decreto 2028/1986."
    ),
    "(3)": (
        "El AR se aplica en la actualización previa a la entrada en vigor de los Reglamentos "
        "Delegados y de Ejecución que desarrollan los Reglamentos (UE) Nº 167/2013 o 168/2013."
    ),
}


# ── Modelos de salida ─────────────────────────────────────────────────────────

class CRImplicada(BaseModel):
    codigo: str             = Field(..., description="Código de la CR adicional, ej. '2.9'")
    cr_origen: str          = Field(..., description="CR que implica a esta, ej. '2.1'")
    condicion: Optional[str]= Field(None, description="Condición bajo la que aplica")
    fuente_literal: str     = Field(..., description="Texto del manual del que se extrae")


class Incorporacion(BaseModel):
    cr_origen: str          = Field(..., description="CR que obliga a esta incorporación")
    descripcion: str        = Field(..., description="Qué hay que incorporar físicamente")
    condicion: Optional[str]= Field(None)
    sin_tramitar_cr: bool   = Field(True)
    fuente_literal: str     = Field(...)


class Restriccion(BaseModel):
    cr_origen: str          = Field(..., description="CR afectada por esta restricción")
    descripcion: str        = Field(..., description="Descripción de la restricción o exención")
    condicion: str          = Field(..., description="Condición bajo la que aplica")
    fuente_literal: str     = Field(...)


class ARConModalidad(BaseModel):
    sistema: str            = Field(..., description="Sistema afectado, ej. 'Frenado'")
    referencia: str         = Field(..., description="Código normativo, ej. '71/320/CEE'")
    nivel: str              = Field(..., description="Modalidad: '(1)', '(2)' o '(3)'")
    descripcion_modalidad: str = Field(..., description="Descripción exacta del preámbulo")


class ResultadoGrafo(BaseModel):
    categoria_bloqueada:  bool              = Field(False,
                             description="True si X en la tabla: reforma imposible para esta categoría")
    crs_bloqueadas:       list[str]         = Field(default_factory=list,
                             description="CRs donde la categoría está bloqueada")
    crs_implicadas:       list[CRImplicada] = Field(default_factory=list)
    incorporaciones:      list[Incorporacion]= Field(default_factory=list)
    restricciones:        list[Restriccion] = Field(default_factory=list)
    ars_por_cr:           dict[str, list[ARConModalidad]] = Field(default_factory=dict,
                             description="ARs con modalidad descrita para cada CR")


# ── Schema para evaluación de condiciones ─────────────────────────────────────

class _EvaluacionCondicion(BaseModel):
    indice: int  = Field(..., description="Índice de la condición (0-based)")
    aplica: bool = Field(..., description="True si la condición aplica a este vehículo/reforma")
    motivo: str  = Field(..., description="Explicación breve de por qué aplica o no")


class _EvaluacionCondiciones(BaseModel):
    evaluaciones: list[_EvaluacionCondicion] = Field(default_factory=list)


# ── Carga del grafo (singleton) ───────────────────────────────────────────────

@lru_cache(maxsize=1)
def _cargar_grafo() -> dict:
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró {GRAPH_PATH}\n"
            "Genera el grafo con: python scripts_graph/build_graph.py"
        )
    with open(GRAPH_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_llm():
    global MODELO
    if MODELO is None:
        import os
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        MODELO = os.environ.get("MODELO_RAZONAMIENTO", "gpt-4o")
    return ChatOpenAI(model=MODELO, temperature=0)


def _ars_para_categoria(nodo: dict, categoria: str) -> list[dict]:
    return nodo.get("ars_por_categoria", {}).get(categoria, [])


def _edges_de_crs(grafo: dict, crs: list[str]) -> list[dict]:
    """Devuelve todos los edges que salen de las CRs dadas."""
    keys = {f"CR-{cr}" for cr in crs}
    return [e for e in grafo["edges"] if e["cr_origen"] in keys]


# ── Evaluación de condiciones con LLM ─────────────────────────────────────────

PROMPT_EVALUACION = """\
Eres un experto en el Manual de Reformas de Vehículos DGT (España).

Evalúa qué condiciones de la lista aplican al siguiente vehículo y reforma:

VEHÍCULO:
  Categoría           : {categoria}
  Fecha matriculación : {fecha_matriculacion}

DESCRIPCIÓN DE LA REFORMA:
{descripcion_reforma}

CONDICIONES A EVALUAR (una por línea, con su índice):
{condiciones_texto}

Para cada condición indica si aplica (true/false) y un motivo breve.
Si no tienes datos suficientes para decidir, marca aplica=true (precaución).
"""


async def _evaluar_condiciones(
    condiciones: list[str],
    categoria: str,
    descripcion_reforma: str,
    fecha_matriculacion: str,
) -> list[bool]:
    """Evalúa en lote qué condiciones aplican a este vehículo. Devuelve lista de bool."""
    if not condiciones:
        return []

    condiciones_texto = "\n".join(
        f"{i}. {c}" for i, c in enumerate(condiciones)
    )
    prompt = PROMPT_EVALUACION.format(
        categoria=categoria,
        fecha_matriculacion=fecha_matriculacion or "desconocida",
        descripcion_reforma=descripcion_reforma,
        condiciones_texto=condiciones_texto,
    )

    llm = _get_llm().with_structured_output(_EvaluacionCondiciones)
    resultado: _EvaluacionCondiciones = await llm.ainvoke(prompt)

    # Mapear índice → aplica; si falta algún índice, asumir True (precaución)
    mapa = {ev.indice: ev.aplica for ev in resultado.evaluaciones}
    return [mapa.get(i, True) for i in range(len(condiciones))]


# ── Función principal ─────────────────────────────────────────────────────────

async def enriquecer_con_grafo(
    crs: list[str],
    categoria: str,
    descripcion_reforma: str,
    fecha_matriculacion: str = "",
) -> ResultadoGrafo:
    """
    Dado un conjunto de CRs identificadas, traversa el grafo KAG y devuelve:
      - CRs adicionales que implican (con condición evaluada)
      - Incorporaciones físicas obligatorias (sin CR adicional)
      - Restricciones activas para este vehículo
      - ARs filtrados por categoría para todas las CRs del grafo

    Args:
        crs:                 Códigos sin prefijo, ej. ["2.1", "5.1"]
        categoria:           Categoría del vehículo, ej. "M1"
        descripcion_reforma: Texto libre de la reforma
        fecha_matriculacion: Fecha de primera matriculación, ej. "15/03/2018"
    """
    grafo = _cargar_grafo()
    edges = _edges_de_crs(grafo, crs)

    # Separar edges por tipo
    edges_implica      = [e for e in edges if e["tipo"] == "implica_cr"]
    edges_incorporar   = [e for e in edges if e["tipo"] == "obliga_incorporar"]
    edges_restriccion  = [e for e in edges if e["tipo"] == "restriccion"]

    # Recoger todas las condiciones para evaluación en lote
    condiciones_implica     = [e.get("condicion") or "" for e in edges_implica]
    condiciones_incorporar  = [e.get("condicion") or "" for e in edges_incorporar]
    condiciones_restriccion = [e.get("condicion") or "" for e in edges_restriccion]

    todas_condiciones = condiciones_implica + condiciones_incorporar + condiciones_restriccion
    n_implica     = len(edges_implica)
    n_incorporar  = len(edges_incorporar)

    # Evaluar con LLM — una sola llamada para todo
    aplican = await _evaluar_condiciones(
        condiciones=todas_condiciones,
        categoria=categoria,
        descripcion_reforma=descripcion_reforma,
        fecha_matriculacion=fecha_matriculacion,
    )

    aplican_implica     = aplican[:n_implica]
    aplican_incorporar  = aplican[n_implica: n_implica + n_incorporar]
    aplican_restriccion = aplican[n_implica + n_incorporar:]

    # Construir resultado
    crs_implicadas: list[CRImplicada] = []
    for edge, aplica in zip(edges_implica, aplican_implica):
        if aplica and edge.get("cr_destino"):
            codigo_destino = edge["cr_destino"].replace("CR-", "")
            crs_implicadas.append(CRImplicada(
                codigo=codigo_destino,
                cr_origen=edge["cr_origen"].replace("CR-", ""),
                condicion=edge.get("condicion"),
                fuente_literal=edge.get("fuente_literal", ""),
            ))

    incorporaciones: list[Incorporacion] = []
    for edge, aplica in zip(edges_incorporar, aplican_incorporar):
        if aplica:
            incorporaciones.append(Incorporacion(
                cr_origen=edge["cr_origen"].replace("CR-", ""),
                descripcion=edge.get("fuente_literal", "")[:200],
                condicion=edge.get("condicion"),
                sin_tramitar_cr=edge.get("sin_tramitar_cr", True),
                fuente_literal=edge.get("fuente_literal", ""),
            ))

    restricciones: list[Restriccion] = []
    for edge, aplica in zip(edges_restriccion, aplican_restriccion):
        if aplica:
            restricciones.append(Restriccion(
                cr_origen=edge["cr_origen"].replace("CR-", ""),
                descripcion=edge.get("fuente_literal", "")[:200],
                condicion=edge.get("condicion", ""),
                fuente_literal=edge.get("fuente_literal", ""),
            ))

    # ARs por categoría para todas las CRs (directo del grafo, sin llamada extra a ChromaDB)
    crs_todas = list(set(crs) | {c.codigo for c in crs_implicadas})
    ars_por_cr: dict[str, list[ARConModalidad]] = {}
    crs_bloqueadas: list[str] = []

    for cr in crs_todas:
        nodo = grafo["nodos"].get(f"CR-{cr}")
        if nodo:
            if categoria in nodo.get("categorias_bloqueadas", []):
                crs_bloqueadas.append(cr)
            ars_raw = _ars_para_categoria(nodo, categoria)
            if ars_raw:
                ars_por_cr[cr] = [
                    ARConModalidad(
                        sistema=ar["sistema"],
                        referencia=ar["referencia"],
                        nivel=ar["nivel"],
                        descripcion_modalidad=DESCRIPCIONES_MODALIDAD.get(ar["nivel"], ar["nivel"]),
                    )
                    for ar in ars_raw
                ]

    return ResultadoGrafo(
        categoria_bloqueada=bool(crs_bloqueadas),
        crs_bloqueadas=sorted(crs_bloqueadas),
        crs_implicadas=crs_implicadas,
        incorporaciones=incorporaciones,
        restricciones=restricciones,
        ars_por_cr=ars_por_cr,
    )

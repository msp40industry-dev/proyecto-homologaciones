"""
graph.py — Grafo LangGraph para la generación del proyecto técnico Vía A.

Flujo:
  identificador_cr
       ↓
  [redactor_memoria, redactor_pliego, redactor_conclusiones]  (paralelo)
       ↓
  revision_humana  ← interrupt() — el ingeniero aprueba o pide reescritura
       ↓  (si hay reescrituras → vuelve al agente correspondiente)
  ensamblador
       ↓
  OUTPUT: .docx
"""

from __future__ import annotations
import uuid
from typing import Annotated, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from langgraph.graph.message import add_messages
import operator

from proyecto_tecnico.models import (
    EntradaProyecto,
    FichaCR,
    ARFiltrado,
    SeccionGenerada,
    EstadoRevision,
)
from proyecto_tecnico.agents.identificador_cr import identificar_crs
from proyecto_tecnico.agents.redactor_memoria import redactar_memoria
from proyecto_tecnico.agents.redactor_pliego import redactar_pliego
from proyecto_tecnico.agents.redactor_conclusiones import redactar_conclusiones
from proyecto_tecnico.agents.ensamblador import ensamblar_documento


# ─────────────────────────────────────────────
#  ESTADO DEL GRAFO
# ─────────────────────────────────────────────

class EstadoProyecto(TypedDict):
    # ── Entrada del ingeniero ──────────────────
    proyecto_id: str
    entrada: EntradaProyecto

    # ── Generado por el Agente 1 ───────────────
    crs_identificados: list[FichaCR]
    ars_filtrados: list[ARFiltrado]

    # ── Secciones generadas por los agentes ────
    # Clave: id_seccion (ej. "peticionario", "antecedentes", ...)
    secciones: Annotated[dict[str, SeccionGenerada], lambda x, y: {**x, **y}]

    # ── Control de flujo ──────────────────────
    # Secciones que necesitan regenerarse tras revisión del ingeniero
    secciones_a_regenerar: list[str]

    # ── Output final ──────────────────────────
    docx_path: Optional[str]
    error: Optional[str]


# ─────────────────────────────────────────────
#  NODOS DEL GRAFO
# ─────────────────────────────────────────────

async def nodo_identificador_cr(estado: EstadoProyecto) -> dict:
    """
    Agente 1: Identifica los CRs aplicables y filtra los ARs por categoría.
    Reutiliza la ChromaDB existente del módulo RAG.
    """
    try:
        crs, ars = await identificar_crs(
            descripcion=estado["entrada"].descripcion_reforma,
            crs_indicados=estado["entrada"].crs_indicados,
            categoria=estado["entrada"].vehiculo.categoria,
        )
        return {
            "crs_identificados": crs,
            "ars_filtrados": ars,
        }
    except Exception as e:
        return {"error": f"Error en identificación de CRs: {str(e)}"}


async def nodo_redactor_memoria(estado: EstadoProyecto) -> dict:
    try:
        secciones_nuevas = await redactar_memoria(
            entrada=estado["entrada"],
            crs=estado["crs_identificados"],
            ars=estado["ars_filtrados"],
            secciones_existentes=estado.get("secciones", {}),
            secciones_a_regenerar=estado.get("secciones_a_regenerar", []),
        )
        print(f"[memoria] secciones generadas: {list(secciones_nuevas.keys())}")
        return {"secciones": secciones_nuevas}
    except Exception as e:
        import traceback
        print(f"[memoria] ERROR: {e}")
        print(traceback.format_exc())
        return {"secciones": {}}


async def nodo_redactor_pliego(estado: EstadoProyecto) -> dict:
    try:
        secciones_nuevas = await redactar_pliego(
            entrada=estado["entrada"],
            crs=estado["crs_identificados"],
            secciones_existentes=estado.get("secciones", {}),
            secciones_a_regenerar=estado.get("secciones_a_regenerar", []),
        )
        print(f"[pliego] secciones generadas: {list(secciones_nuevas.keys())}")
        return {"secciones": secciones_nuevas}
    except Exception as e:
        print(f"[pliego] ERROR: {e}")
        return {"secciones": {}}


async def nodo_redactor_conclusiones(estado: EstadoProyecto) -> dict:
    try:
        secciones_nuevas = await redactar_conclusiones(
            entrada=estado["entrada"],
            crs=estado["crs_identificados"],
            ars=estado["ars_filtrados"],
            secciones_existentes=estado.get("secciones", {}),
            secciones_a_regenerar=estado.get("secciones_a_regenerar", []),
        )
        print(f"[conclusiones] secciones generadas: {list(secciones_nuevas.keys())}")
        return {"secciones": secciones_nuevas}
    except Exception as e:
        print(f"[conclusiones] ERROR: {e}")
        return {"secciones": {}}


def nodo_revision_humana(estado: EstadoProyecto) -> dict:
    """
    Punto de interrupción: el grafo se pausa aquí.
    El ingeniero revisa las secciones desde Streamlit y llama a
    graph.update_state() con las revisiones.
    Si todas están aprobadas → continúa al ensamblador.
    Si hay reescrituras → vuelve a los agentes correspondientes.
    """
    # Verificar si hay secciones pendientes de revisión
    secciones = estado.get("secciones", {})
    pendientes = [
        sid for sid, sec in secciones.items()
        if sec.revision.estado == "pendiente"
    ]

    if pendientes:
        # Pausa el grafo — Streamlit mostrará las secciones al ingeniero
        revisiones = interrupt({
            "tipo": "revision_secciones",
            "secciones_pendientes": pendientes,
            "secciones": {
                sid: {
                    "titulo": sec.titulo,
                    "contenido": sec.contenido,
                    "requiere_adjunto": sec.requiere_adjunto,
                    "adjunto_descripcion": sec.adjunto_descripcion,
                }
                for sid, sec in secciones.items()
            }
        })

        # Procesar las revisiones recibidas del ingeniero
        # revisiones es un dict: {id_seccion: {"estado": "aprobado"|"reescribir", "motivo": str}}
        secciones_actualizadas = dict(secciones)
        secciones_a_regenerar = []

        for sid, rev in revisiones.items():
            if sid in secciones_actualizadas:
                sec = secciones_actualizadas[sid]
                sec.revision = EstadoRevision(
                    estado=rev["estado"],
                    motivo=rev.get("motivo"),
                    iteraciones=sec.revision.iteraciones,
                )
                if rev["estado"] == "reescribir":
                    secciones_a_regenerar.append(sid)

                # Guardar adjunto si viene en la revisión
                if rev.get("adjunto_bytes"):
                    sec.adjunto_bytes = rev["adjunto_bytes"]
                    sec.adjunto_nombre = rev.get("adjunto_nombre")

        return {
            "secciones": secciones_actualizadas,
            "secciones_a_regenerar": secciones_a_regenerar,
        }

    return {"secciones_a_regenerar": []}


async def nodo_ensamblador(estado: EstadoProyecto) -> dict:
    """
    Agente 5 (sin LLM): Monta el Word final con python-docx.
    """
    try:
        docx_path = await ensamblar_documento(
            proyecto_id=estado["proyecto_id"],
            entrada=estado["entrada"],
            secciones=estado["secciones"],
            crs=estado["crs_identificados"],
            ars=estado["ars_filtrados"],
        )
        return {"docx_path": docx_path}
    except Exception as e:
        return {"error": f"Error en ensamblado del documento: {str(e)}"}


# ─────────────────────────────────────────────
#  CONDICIONES DE ENRUTAMIENTO
# ─────────────────────────────────────────────

def enrutar_a_redactores(estado: EstadoProyecto) -> list[str]:
    if estado.get("error"):
        return [END]
    return ["redactor_memoria", "redactor_pliego", "redactor_conclusiones"]


def tras_revision(estado: EstadoProyecto) -> list[str]:
    """
    Tras la revisión humana:
    - Si hay secciones a regenerar → enruta a los agentes correspondientes
    - Si todo aprobado → va al ensamblador
    """
    if estado.get("secciones_a_regenerar"):
        return enrutar_regeneracion(estado)
    return ["ensamblador"]


def _seccion_pertenece_a_memoria(sid: str) -> bool:
    ids_memoria = {
        "peticionario", "objeto", "antecedentes",
        "identificacion_vehiculo", "descripcion_reforma"
    }
    return sid in ids_memoria


def _seccion_pertenece_a_pliego(sid: str) -> bool:
    ids_pliego = {
        "calidad_materiales", "normas_ejecucion",
        "certificados", "taller_ejecutor"
    }
    return sid in ids_pliego


def _seccion_pertenece_a_conclusiones(sid: str) -> bool:
    return sid == "conclusiones"


def enrutar_regeneracion(estado: EstadoProyecto) -> list[str]:
    """
    Determina qué agentes deben regenerar sus secciones.
    Devuelve lista de nodos a ejecutar.
    """
    a_regenerar = estado.get("secciones_a_regenerar", [])
    nodos = set()
    for sid in a_regenerar:
        if _seccion_pertenece_a_memoria(sid):
            nodos.add("redactor_memoria")
        elif _seccion_pertenece_a_pliego(sid):
            nodos.add("redactor_pliego")
        elif _seccion_pertenece_a_conclusiones(sid):
            nodos.add("redactor_conclusiones")
    return list(nodos) if nodos else ["revision_humana"]


# ─────────────────────────────────────────────
#  CONSTRUCCIÓN DEL GRAFO
# ─────────────────────────────────────────────

def construir_grafo() -> StateGraph:
    builder = StateGraph(EstadoProyecto)

    # Añadir nodos
    builder.add_node("identificador_cr",      nodo_identificador_cr)
    builder.add_node("redactor_memoria",       nodo_redactor_memoria)
    builder.add_node("redactor_pliego",        nodo_redactor_pliego)
    builder.add_node("redactor_conclusiones",  nodo_redactor_conclusiones)
    builder.add_node("revision_humana",        nodo_revision_humana)
    builder.add_node("ensamblador",            nodo_ensamblador)

    # Punto de entrada
    builder.set_entry_point("identificador_cr")

    # Identificador → comprueba error → agentes en paralelo
    builder.add_conditional_edges(
        "identificador_cr",
        enrutar_a_redactores,
        ["redactor_memoria", "redactor_pliego", "redactor_conclusiones", END]
    )
    builder.add_edge("redactor_memoria",      "revision_humana")
    builder.add_edge("redactor_pliego",       "revision_humana")
    builder.add_edge("redactor_conclusiones", "revision_humana")

    # Revisión → ensamblar o regenerar (en el agente correcto según la sección)
    builder.add_conditional_edges(
        "revision_humana",
        tras_revision,
        ["redactor_memoria", "redactor_pliego", "redactor_conclusiones", "ensamblador"]
    )

    # Ensamblador → fin
    builder.add_edge("ensamblador", END)

    return builder


# ─────────────────────────────────────────────
#  INSTANCIA GLOBAL (con checkpointer en memoria)
# ─────────────────────────────────────────────

_checkpointer = MemorySaver()
_builder = construir_grafo()
grafo = _builder.compile(
    checkpointer=_checkpointer,
    interrupt_before=["revision_humana"],
)


# ─────────────────────────────────────────────
#  HELPERS PARA EL BACKEND
# ─────────────────────────────────────────────

def crear_estado_inicial(entrada: EntradaProyecto) -> EstadoProyecto:
    """Crea el estado inicial del grafo a partir de la entrada del ingeniero."""
    return EstadoProyecto(
        proyecto_id=str(uuid.uuid4()),
        entrada=entrada,
        crs_identificados=[],
        ars_filtrados=[],
        secciones={},
        secciones_a_regenerar=[],
        docx_path=None,
        error=None,
    )

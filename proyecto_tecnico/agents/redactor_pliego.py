"""
redactor_pliego.py — Agente 3 (gpt-4o-mini)

Genera las secciones del Pliego de Condiciones (3.1–3.4):
  3.1 Calidad de materiales
  3.2 Normas de ejecución
  3.3 Certificados y autorizaciones
  3.4 Taller ejecutor
"""

from __future__ import annotations
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from proyecto_tecnico.models import (
    EntradaProyecto, FichaCR, SeccionGenerada, EstadoRevision
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

_SYSTEM = """Eres un redactor técnico especializado en proyectos de reforma de vehículos en España.
Redactas el Pliego de Condiciones en lenguaje formal de ingeniería, en español.
El pliego establece los requisitos técnicos y legales que deben cumplirse.
Sé preciso y cita normativa cuando sea relevante.
Si algún dato no está disponible, escribe [COMPLETAR]."""

_PROMPTS = {

    "calidad_materiales": """Redacta la sección "3.1 Calidad de materiales" del Pliego de Condiciones.
Describe los requisitos de calidad que deben cumplir los materiales y componentes empleados en la reforma.
Incluye:
- Requisitos generales de calidad
- Referencias a normativa aplicable (UNE, ISO, ECE si procede)
- Requisitos específicos para los componentes instalados (usa los datos de componentes proporcionados)
- Exigencia de certificados de homologación cuando aplique""",

    "normas_ejecucion": """Redacta la sección "3.2 Normas de ejecución" del Pliego de Condiciones.
Describe las normas técnicas que deben seguirse durante la ejecución de la reforma.
Incluye:
- Normativa de aplicación (Manual de Reformas DGT, Reglamento UE 2018/858, ARs aplicables)
- Procedimientos de montaje requeridos
- Controles de calidad durante la ejecución
- Requisitos del personal técnico que ejecuta la reforma""",

    "certificados": """Redacta la sección "3.3 Certificados y autorizaciones" del Pliego de Condiciones.
Lista toda la documentación que debe acompañar a la reforma:
- Documentación exigida por cada CR aplicable (usa la lista de documentación de las fichas CR)
- Certificados de homologación de los componentes
- Declaraciones de conformidad
- Cualquier autorización administrativa requerida
Organiza la información por CR si hay varios.""",

    "taller_ejecutor": """Redacta la sección "3.4 Taller ejecutor" del Pliego de Condiciones.
Describe los requisitos que debe cumplir el taller que ejecuta la reforma.
Incluye:
- Datos del taller ejecutor (usa los datos proporcionados)
- Requisitos de autorización y equipamiento
- Responsabilidades del taller
- Referencia a la normativa que regula los talleres de reforma""",
}


async def redactar_pliego(
    entrada: EntradaProyecto,
    crs: list[FichaCR],
    secciones_existentes: dict[str, SeccionGenerada],
    secciones_a_regenerar: list[str],
) -> dict[str, SeccionGenerada]:
    ids_pliego = list(_PROMPTS.keys())

    if secciones_a_regenerar:
        a_procesar = [sid for sid in secciones_a_regenerar if sid in ids_pliego]
    else:
        a_procesar = ids_pliego

    resultado: dict[str, SeccionGenerada] = {}

    for sid in a_procesar:
        motivo = None
        iteraciones = 0
        if sid in secciones_existentes:
            rev = secciones_existentes[sid].revision
            if rev.estado == "reescribir":
                motivo = rev.motivo
                iteraciones = rev.iteraciones + 1
            else:
                iteraciones = rev.iteraciones

        instruccion = _PROMPTS[sid]
        if motivo and sid in secciones_existentes:
            instruccion = f"""{instruccion}

REESCRITURA SOLICITADA POR EL INGENIERO.
Motivo: "{motivo}"
Versión anterior:
---
{secciones_existentes[sid].contenido}
---
Corrige el problema indicado."""

        contexto = _construir_contexto(entrada, crs)
        respuesta = await _llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=f"{instruccion}\n\nDATOS DEL PROYECTO:\n{contexto}"),
        ])

        resultado[sid] = SeccionGenerada(
            id_seccion=sid,
            titulo=_titulo(sid),
            contenido=respuesta.content.strip(),
            revision=EstadoRevision(estado="pendiente", iteraciones=iteraciones),
            requiere_adjunto=False,
        )

    return resultado


def _construir_contexto(entrada: EntradaProyecto, crs: list[FichaCR]) -> str:
    taller = entrada.taller
    v = entrada.vehiculo

    crs_con_docs = "\n".join([
        f"  CR {cr.codigo} — {cr.denominacion}:\n"
        + "\n".join([f"    · {doc}" for doc in cr.documentacion])
        for cr in crs
    ])

    componentes = "\n".join([
        f"  - {c.descripcion}"
        + (f" | {c.marca} {c.modelo}" if c.marca else "")
        + (f" | Homologación: {c.numero_homologacion}" if c.numero_homologacion else "")
        for c in entrada.componentes
    ]) or "  [No especificados]"

    return f"""TALLER EJECUTOR:
  {taller.nombre}
  {taller.direccion}, {taller.localidad} ({taller.provincia})
  Nº autorización: {taller.numero_autorizacion or '[COMPLETAR]'}

VEHÍCULO: {v.marca} {v.modelo} — {v.bastidor} — Categoría {v.categoria}

CRs Y DOCUMENTACIÓN EXIGIBLE:
{crs_con_docs or '  [No disponible]'}

COMPONENTES INSTALADOS:
{componentes}

DESCRIPCIÓN DE LA REFORMA:
{entrada.descripcion_reforma}"""


def _titulo(sid: str) -> str:
    titulos = {
        "calidad_materiales": "3.1 Calidad de materiales",
        "normas_ejecucion":   "3.2 Normas de ejecución",
        "certificados":       "3.3 Certificados y autorizaciones",
        "taller_ejecutor":    "3.4 Taller ejecutor",
    }
    return titulos.get(sid, sid)

"""
redactor_conclusiones.py — Agente 4 (gpt-4o-mini)

Genera la sección 8. Conclusiones del proyecto técnico.
"""

from __future__ import annotations
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from proyecto_tecnico.models import (
    EntradaProyecto, FichaCR, ARFiltrado, SeccionGenerada, EstadoRevision
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

_SYSTEM = """Eres un redactor técnico especializado en proyectos de reforma de vehículos en España.
Redactas la sección de Conclusiones en lenguaje formal de ingeniería, en español.
Las conclusiones deben ser formales, precisas y declarar la viabilidad técnica de la reforma.
Cita los CRs y la normativa aplicable."""

_PROMPT = """Redacta la sección "8. Conclusiones" del proyecto técnico.
Las conclusiones deben:
1. Declarar que la reforma cumple con los requisitos técnicos y normativos aplicables.
2. Citar expresamente los CRs implicados y la categoría del vehículo.
3. Mencionar los Actos Reglamentarios que deben verificarse en la ITV.
4. Afirmar que el ingeniero considera técnicamente viable la reforma y que la firma
   bajo su responsabilidad profesional.
5. Incluir lugar, fecha y espacio para firma y sello del ingeniero.

Formato: 3-5 párrafos formales. Al final, bloque de firma."""


async def redactar_conclusiones(
    entrada: EntradaProyecto,
    crs: list[FichaCR],
    ars: list[ARFiltrado],
    secciones_existentes: dict[str, SeccionGenerada],
    secciones_a_regenerar: list[str],
) -> dict[str, SeccionGenerada]:

    if secciones_a_regenerar and "conclusiones" not in secciones_a_regenerar:
        return {}

    motivo = None
    iteraciones = 0
    if "conclusiones" in secciones_existentes:
        rev = secciones_existentes["conclusiones"].revision
        if rev.estado == "reescribir":
            motivo = rev.motivo
            iteraciones = rev.iteraciones + 1
        else:
            iteraciones = rev.iteraciones

    instruccion = _PROMPT
    if motivo and "conclusiones" in secciones_existentes:
        instruccion = f"""{instruccion}

REESCRITURA SOLICITADA POR EL INGENIERO.
Motivo: "{motivo}"
Versión anterior:
---
{secciones_existentes["conclusiones"].contenido}
---
Corrige el problema indicado."""

    contexto = _construir_contexto(entrada, crs, ars)
    respuesta = await _llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"{instruccion}\n\nDATOS DEL PROYECTO:\n{contexto}"),
    ])

    return {
        "conclusiones": SeccionGenerada(
            id_seccion="conclusiones",
            titulo="8. Conclusiones",
            contenido=respuesta.content.strip(),
            revision=EstadoRevision(estado="pendiente", iteraciones=iteraciones),
            requiere_adjunto=False,
        )
    }


def _construir_contexto(
    entrada: EntradaProyecto,
    crs: list[FichaCR],
    ars: list[ARFiltrado],
) -> str:
    v = entrada.vehiculo
    ing = entrada.ingeniero

    crs_texto = ", ".join([f"CR {cr.codigo} ({cr.denominacion})" for cr in crs])
    ars_texto = "\n".join([
        f"  - {ar.sistema} {ar.referencia} | {ar.nivel_exigencia}"
        for ar in ars
    ])

    return f"""VEHÍCULO: {v.marca} {v.modelo} | Bastidor: {v.bastidor} | Categoría: {v.categoria}
INGENIERO: {ing.nombre} {ing.apellidos} — Colegiado nº {ing.numero_colegiado}
COLEGIO: {ing.colegio_profesional}
FECHA: {entrada.fecha_proyecto or '[COMPLETAR]'}
LOCALIDAD: {entrada.taller.localidad}

CRs APLICABLES: {crs_texto or '[Ninguno]'}
DESCRIPCIÓN DE LA REFORMA: {entrada.descripcion_reforma}

ACTOS REGLAMENTARIOS A VERIFICAR EN ITV:
{ars_texto or '  [Ninguno]'}"""

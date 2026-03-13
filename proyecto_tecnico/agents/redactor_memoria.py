"""
redactor_memoria.py — Agente 2 (gpt-4o)

Genera las siguientes secciones del proyecto técnico:
  - 0.  Peticionario
  - 1.1 Objeto
  - 1.2 Antecedentes (incluye tabla de ARs)
  - 1.3.1 Identificación del vehículo
  - 1.4 Descripción de la reforma
      1.4.1 Desmontajes realizados
      1.4.2 Variaciones y sustituciones
      1.4.3 Materiales empleados
      1.4.4 Montajes realizados
"""

from __future__ import annotations
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from proyecto_tecnico.models import (
    EntradaProyecto, FichaCR, ARFiltrado, SeccionGenerada, EstadoRevision
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

# ─── Prompts de sistema por sección ──────────────────────────────────────────

_SYSTEM_BASE = """Eres un redactor técnico especializado en proyectos de reforma de vehículos en España.
Redactas secciones de proyectos técnicos en lenguaje formal de ingeniería, en español.
Eres preciso, conciso y citas siempre los CRs y ARs correctamente.
No añades información que no esté en los datos proporcionados.
Si algún dato es desconocido, escribe [COMPLETAR]."""

_PROMPTS: dict[str, str] = {

    "peticionario": """Redacta la sección "0. Peticionario" del proyecto técnico.
Usa los datos del vehículo, taller e ingeniero proporcionados.
Formato: párrafo breve con los datos del solicitante (propietario del vehículo = taller ejecutor
o el propio propietario si se indica) y el ingeniero redactor.
Incluye: nombre/razón social, NIF (escribe [COMPLETAR] si no se proporciona), dirección, teléfono, email.""",

    "objeto": """Redacta la sección "1.1 Objeto" del proyecto técnico.
Describe brevemente el objeto del proyecto: identificación del vehículo y tipo de reforma.
Formato: 2-3 párrafos. Cita los CRs implicados.""",

    "antecedentes": """Redacta la sección "1.2 Antecedentes" del proyecto técnico.
Debe incluir:
1. Párrafo introductorio que describe la situación previa y la reforma solicitada.
2. Un párrafo mencionando los CRs aplicables con su denominación oficial.
3. Referencia a la normativa: Manual de Reformas de Vehículos (DGT) y Reglamento (UE) 2018/858.

IMPORTANTE: NO incluyas ninguna tabla en markdown (ni con barras | ni con guiones ---).
Las tablas de Códigos de Reforma y Actos Reglamentarios se generarán automáticamente en el documento.
Redacta únicamente texto en párrafos.""",

    "identificacion_vehiculo": """Redacta 1-2 frases introductorias para la sección "1.3.1 Identificación del vehículo".
Indica brevemente que a continuación se recogen los datos identificativos del vehículo objeto de la reforma.

IMPORTANTE: NO incluyas ninguna tabla, ni listas de datos con barras | ni guiones.
La ficha técnica con todos los datos del vehículo se genera automáticamente en el documento.""",

    "descripcion_reforma": """Redacta la sección "1.4 Descripción de la reforma" con 4 subsecciones:

1.4.1 Desmontajes realizados
  Lista los elementos desmontados del vehículo antes de la reforma.
  Infiere de la descripción qué elementos habrían sido desmontados.
  Si no es posible determinarlo con certeza, escribe [COMPLETAR].

1.4.2 Variaciones y sustituciones
  Describe los cambios realizados: qué se ha sustituido, modificado o añadido.
  Referencia los componentes con marca, modelo y nº de homologación cuando estén disponibles.

1.4.3 Materiales empleados
  Lista los materiales y componentes instalados con sus referencias técnicas.
  Usa los datos de componentes proporcionados. Si hay datos de homologación, inclúyelos.

1.4.4 Montajes realizados
  Describe el proceso de montaje de los elementos nuevos.
  Sé técnico y preciso. Si no hay datos suficientes, escribe [COMPLETAR] en los puntos específicos.""",
}


async def redactar_memoria(
    entrada: EntradaProyecto,
    crs: list[FichaCR],
    ars: list[ARFiltrado],
    secciones_existentes: dict[str, SeccionGenerada],
    secciones_a_regenerar: list[str],
) -> dict[str, SeccionGenerada]:
    """
    Genera o regenera las secciones de la memoria.
    Si secciones_a_regenerar está vacío → genera todas.
    Si tiene valores → solo regenera las indicadas con el motivo de la revisión.
    """
    ids_memoria = list(_PROMPTS.keys())

    # Determinar qué secciones procesar
    if secciones_a_regenerar:
        a_procesar = [sid for sid in secciones_a_regenerar if sid in ids_memoria]
    else:
        a_procesar = ids_memoria

    resultado: dict[str, SeccionGenerada] = {}

    for sid in a_procesar:
        motivo_reescritura = None
        if sid in secciones_existentes:
            rev = secciones_existentes[sid].revision
            if rev.estado == "reescribir":
                motivo_reescritura = rev.motivo
                iteraciones = rev.iteraciones + 1
            else:
                iteraciones = rev.iteraciones
        else:
            iteraciones = 0

        contenido = await _generar_seccion(
            sid=sid,
            entrada=entrada,
            crs=crs,
            ars=ars,
            motivo_reescritura=motivo_reescritura,
            contenido_anterior=secciones_existentes.get(sid, None),
        )

        resultado[sid] = SeccionGenerada(
            id_seccion=sid,
            titulo=_titulo(sid),
            contenido=contenido,
            revision=EstadoRevision(
                estado="pendiente",
                iteraciones=iteraciones,
            ),
            requiere_adjunto=False,
        )

    return resultado


async def _generar_seccion(
    sid: str,
    entrada: EntradaProyecto,
    crs: list[FichaCR],
    ars: list[ARFiltrado],
    motivo_reescritura: str | None,
    contenido_anterior: SeccionGenerada | None,
) -> str:
    contexto = _construir_contexto(entrada, crs, ars)

    instruccion = _PROMPTS[sid]
    if motivo_reescritura and contenido_anterior:
        instruccion = f"""{instruccion}

IMPORTANTE — Esta sección ya fue generada y el ingeniero ha solicitado una reescritura.
Motivo indicado por el ingeniero: "{motivo_reescritura}"
Versión anterior para referencia:
---
{contenido_anterior.contenido}
---
Genera una nueva versión corrigiendo el problema indicado."""

    respuesta = await _llm.ainvoke([
        SystemMessage(content=_SYSTEM_BASE),
        HumanMessage(content=f"{instruccion}\n\nDATOS DEL PROYECTO:\n{contexto}"),
    ])

    return respuesta.content.strip()


def _construir_contexto(
    entrada: EntradaProyecto,
    crs: list[FichaCR],
    ars: list[ARFiltrado],
) -> str:
    v = entrada.vehiculo
    ing = entrada.ingeniero
    taller = entrada.taller

    crs_texto = "\n".join([
        f"  - CR {cr.codigo}: {cr.denominacion} (Vía {cr.via})"
        for cr in crs
    ])

    ars_texto = "\n".join([
        f"  - {ar.sistema} {ar.referencia} | CR {ar.codigo_cr} | {ar.nivel_exigencia}: {ar.descripcion_nivel}"
        for ar in ars
    ])

    componentes_texto = "\n".join([
        f"  - {c.descripcion}"
        + (f" | Marca: {c.marca}" if c.marca else "")
        + (f" | Modelo: {c.modelo}" if c.modelo else "")
        + (f" | Ref: {c.referencia}" if c.referencia else "")
        + (f" | Homologación: {c.numero_homologacion}" if c.numero_homologacion else "")
        for c in entrada.componentes
    ]) or "  [No se han especificado componentes]"

    return f"""VEHÍCULO:
  Marca: {v.marca} | Modelo: {v.modelo}
  Bastidor: {v.bastidor} | Matrícula: {v.matricula}
  Fecha matriculación: {v.fecha_matriculacion} | Categoría: {v.categoria}
  Color: {v.color or '[COMPLETAR]'} | Km: {v.kilometraje or '[COMPLETAR]'}

INGENIERO REDACTOR:
  {ing.nombre} {ing.apellidos}
  Titulación: {ing.titulacion}
  Nº colegiado: {ing.numero_colegiado} — {ing.colegio_profesional}

TALLER EJECUTOR:
  {taller.nombre}
  {taller.direccion}, {taller.localidad} ({taller.provincia})
  Nº autorización: {taller.numero_autorizacion or '[COMPLETAR]'}

DESCRIPCIÓN DE LA REFORMA:
{entrada.descripcion_reforma}

CRs IDENTIFICADOS:
{crs_texto or '  [Ninguno identificado]'}

ACTOS REGLAMENTARIOS (filtrados para {entrada.vehiculo.categoria}):
{ars_texto or '  [Ninguno aplicable]'}

COMPONENTES INSTALADOS:
{componentes_texto}

FECHA DEL PROYECTO: {entrada.fecha_proyecto or '[COMPLETAR]'}
Nº EXPEDIENTE: {entrada.numero_expediente or '[COMPLETAR]'}"""


def _titulo(sid: str) -> str:
    titulos = {
        "peticionario":          "0. Peticionario",
        "objeto":                "1.1 Objeto",
        "antecedentes":          "1.2 Antecedentes",
        "identificacion_vehiculo": "1.3.1 Identificación del vehículo",
        "descripcion_reforma":   "1.4 Descripción de la reforma",
    }
    return titulos.get(sid, sid)

"""
router_proyecto_tecnico.py — Endpoints FastAPI para el generador de proyectos técnicos.

Incluir en main.py con:
    from proyecto_tecnico.router_proyecto_tecnico import router as router_pt
    app.include_router(router_pt, prefix="/proyecto-tecnico", tags=["Proyecto Técnico"])
"""

from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from proyecto_tecnico.models import (
    EntradaProyecto, SolicitudRevision, RespuestaGeneracion
)
from proyecto_tecnico.graph import grafo, crear_estado_inicial
from proyecto_tecnico.validador_crs import validar_crs, ResultadoValidacion

router = APIRouter()


# ─────────────────────────────────────────────
#  POST /proyecto-tecnico/validar-crs
# ─────────────────────────────────────────────

class SolicitudValidarCRs(BaseModel):
    crs: list[str]
    descripcion: str
    categoria: str


@router.post("/validar-crs", response_model=ResultadoValidacion)
async def endpoint_validar_crs(solicitud: SolicitudValidarCRs):
    """
    Valida los CRs indicados por el usuario antes de iniciar la generación.

    Fases:
      1. Recupera cada CR por metadata exacta en ChromaDB.
      2. Clasifica en vía A (incluir) y otros (excluir).
      3. Analiza informacion_adicional de todos los CRs con el LLM:
         si la descripción activa una condición → recupera y clasifica el CR adicional.
      4. Devuelve resumen completo con CRs incluidos, excluidos y adicionales descubiertos.

    Si no hay ningún CR vía A → valido=False con mensaje_bloqueo y documentacion_requerida.
    Si hay CRs adicionales descubiertos → valido=True con crs_adicionales para mostrar al usuario.
    """
    if not solicitud.crs:
        # Sin CRs indicados: el sistema los identificará automáticamente en la generación
        return ResultadoValidacion(
            valido=True,
            crs_incluidos=[],
            crs_excluidos=[],
            crs_adicionales=[],
            mensaje_bloqueo=None,
            documentacion_requerida={},
        )

    try:
        resultado = await validar_crs(
            crs_indicados=solicitud.crs,
            descripcion=solicitud.descripcion,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en validación de CRs: {str(e)}")

    return resultado

# ─────────────────────────────────────────────
#  POST /proyecto-tecnico/generar
# ─────────────────────────────────────────────

@router.post("/generar", response_model=RespuestaGeneracion)
async def generar_proyecto(entrada: EntradaProyecto):
    """
    Inicia la generación del proyecto técnico.
    Ejecuta el grafo hasta el punto de interrupción (revision_humana).
    Devuelve las secciones generadas para que el frontend las muestre al ingeniero.
    """
    estado_inicial = crear_estado_inicial(entrada)
    config = {"configurable": {"thread_id": estado_inicial["proyecto_id"]}}

    try:
        async for _ in grafo.astream(estado_inicial, config=config):
            pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en generación: {str(e)}")

    estado_final = grafo.get_state(config)
    valores = estado_final.values

    if valores.get("error"):
        raise HTTPException(status_code=422, detail=valores["error"])

    return RespuestaGeneracion(
        proyecto_id=valores["proyecto_id"],
        secciones=list(valores.get("secciones", {}).values()),
        crs_identificados=valores.get("crs_identificados", []),
        ars_filtrados=valores.get("ars_filtrados", []),
    )


# ─────────────────────────────────────────────
#  POST /proyecto-tecnico/{proyecto_id}/revisar
# ─────────────────────────────────────────────

@router.post("/{proyecto_id}/revisar")
async def revisar_seccion(proyecto_id: str, solicitud: SolicitudRevision):
    """
    Registra la revisión de una sección (aprobado o reescribir).
    Si es reescritura, el grafo regenera automáticamente la sección.
    """
    config = {"configurable": {"thread_id": proyecto_id}}

    estado = grafo.get_state(config)
    if not estado:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    secciones = dict(estado.values.get("secciones", {}))
    if solicitud.id_seccion not in secciones:
        raise HTTPException(status_code=404, detail=f"Sección '{solicitud.id_seccion}' no encontrada")

    # Actualizar revisión
    sec = secciones[solicitud.id_seccion]
    from proyecto_tecnico.models import EstadoRevision
    sec.revision = EstadoRevision(
        estado=solicitud.estado,
        motivo=solicitud.motivo,
        iteraciones=sec.revision.iteraciones + (1 if solicitud.estado == "reescribir" else 0),
    )
    secciones[solicitud.id_seccion] = sec

    # Si hay reescritura, reanudar el grafo
    if solicitud.estado == "reescribir":
        grafo.update_state(config, {
            "secciones": secciones,
            "secciones_a_regenerar": [solicitud.id_seccion],
        }, as_node="revision_humana")
        try:
            async for _ in grafo.astream(None, config=config):
                pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error en regeneración: {str(e)}")

        estado_nuevo = grafo.get_state(config)
        seccion_regenerada = estado_nuevo.values["secciones"].get(solicitud.id_seccion)
        return {"mensaje": "Sección regenerada", "seccion": seccion_regenerada}

    # Solo aprobar: actualizar estado
    grafo.update_state(config, {"secciones": secciones})
    return {"mensaje": f"Sección '{solicitud.id_seccion}' marcada como {solicitud.estado}"}


# ─────────────────────────────────────────────
#  POST /proyecto-tecnico/{proyecto_id}/adjunto
# ─────────────────────────────────────────────

@router.post("/{proyecto_id}/adjunto")
async def subir_adjunto(
    proyecto_id: str,
    id_seccion: str = Form(...),
    fichero: UploadFile = File(...),
):
    """Sube un adjunto para una sección del proyecto."""
    config = {"configurable": {"thread_id": proyecto_id}}
    estado = grafo.get_state(config)
    if not estado:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    secciones = dict(estado.values.get("secciones", {}))
    if id_seccion not in secciones:
        raise HTTPException(status_code=404, detail=f"Sección '{id_seccion}' no encontrada")

    contenido = await fichero.read()
    secciones[id_seccion].adjunto_bytes = contenido
    secciones[id_seccion].adjunto_nombre = fichero.filename

    grafo.update_state(config, {"secciones": secciones})
    return {"mensaje": f"Adjunto '{fichero.filename}' guardado en sección '{id_seccion}'"}


# ─────────────────────────────────────────────
#  POST /proyecto-tecnico/{proyecto_id}/documento
# ─────────────────────────────────────────────

@router.post("/{proyecto_id}/documento")
async def generar_documento(proyecto_id: str):
    """
    Genera el documento Word final cuando todas las secciones están aprobadas.
    """
    config = {"configurable": {"thread_id": proyecto_id}}
    estado = grafo.get_state(config)
    if not estado:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    valores = estado.values
    secciones = valores.get("secciones", {})

    # Verificar que todas las secciones están aprobadas
    pendientes = [
        sid for sid, sec in secciones.items()
        if sec.revision.estado != "aprobado"
    ]
    if pendientes:
        raise HTTPException(
            status_code=422,
            detail=f"Secciones pendientes de aprobación: {', '.join(pendientes)}"
        )

    # Reanudar el grafo con secciones_a_regenerar vacío → va al ensamblador
    grafo.update_state(config, {"secciones_a_regenerar": []}, as_node="revision_humana")

    try:
        async for _ in grafo.astream(None, config=config):
            pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en ensamblado: {str(e)}")

    estado_final = grafo.get_state(config)
    docx_path = estado_final.values.get("docx_path")

    if not docx_path or not Path(docx_path).exists():
        raise HTTPException(status_code=500, detail="Error al generar el documento")

    return {"mensaje": "Documento generado", "docx_path": docx_path}


# ─────────────────────────────────────────────
#  GET /proyecto-tecnico/{proyecto_id}/descargar
# ─────────────────────────────────────────────

@router.get("/{proyecto_id}/descargar")
async def descargar_documento(proyecto_id: str):
    """Descarga el documento Word generado."""
    config = {"configurable": {"thread_id": proyecto_id}}
    estado = grafo.get_state(config)
    if not estado:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    docx_path = estado.values.get("docx_path")
    if not docx_path or not Path(docx_path).exists():
        raise HTTPException(status_code=404, detail="Documento no generado todavía")

    return FileResponse(
        path=docx_path,
        filename=Path(docx_path).name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

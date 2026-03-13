"""
models.py — Esquemas de datos para el generador de proyectos técnicos Vía A.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
#  ENTRADA DEL INGENIERO
# ─────────────────────────────────────────────

class DatosVehiculo(BaseModel):
    marca: str = Field(..., description="Marca del vehículo, ej. 'Volkswagen'")
    modelo: str = Field(..., description="Modelo del vehículo, ej. 'Golf'")
    bastidor: str = Field(..., description="Número de bastidor (VIN), 17 caracteres")
    matricula: str = Field(..., description="Matrícula del vehículo, ej. '1234 ABC'")
    fecha_matriculacion: str = Field(..., description="Fecha de primera matriculación, ej. '15/03/2018'")
    categoria: str = Field(..., description="Categoría del vehículo, ej. 'M1', 'N1', 'N2'")
    color: Optional[str] = Field(None, description="Color del vehículo")
    kilometraje: Optional[str] = Field(None, description="Kilometraje actual, ej. '85.000 km'")


class Componente(BaseModel):
    descripcion: str = Field(..., description="Descripción del componente, ej. 'Turbocompresor'")
    marca: Optional[str] = Field(None, description="Marca del componente")
    modelo: Optional[str] = Field(None, description="Modelo o referencia comercial")
    referencia: Optional[str] = Field(None, description="Referencia técnica del fabricante")
    numero_homologacion: Optional[str] = Field(None, description="Número de homologación del componente")


class Taller(BaseModel):
    nombre: str
    direccion: str
    localidad: str
    provincia: str
    telefono: Optional[str] = None
    email: Optional[str] = None
    numero_autorizacion: Optional[str] = Field(None, description="Nº de autorización del taller")


class Ingeniero(BaseModel):
    nombre: str
    apellidos: str
    titulacion: str = Field(..., description="Ej. 'Ingeniero Técnico Industrial'")
    numero_colegiado: str
    colegio_profesional: str
    telefono: Optional[str] = None
    email: Optional[str] = None


class EntradaProyecto(BaseModel):
    """
    Datos que introduce el ingeniero en el formulario Streamlit.
    Es la entrada principal al grafo LangGraph.
    """
    # Datos del vehículo
    vehiculo: DatosVehiculo

    # Descripción libre de las reformas realizadas
    descripcion_reforma: str = Field(
        ...,
        min_length=20,
        description="Descripción detallada de todas las reformas realizadas por el ingeniero"
    )

    # CRs que el ingeniero ya conoce (puede estar vacío)
    crs_indicados: list[str] = Field(
        default_factory=list,
        description="Lista de CRs que el ingeniero identifica, ej. ['2.1', '4.4']. Puede estar vacía."
    )

    # Componentes instalados
    componentes: list[Componente] = Field(
        default_factory=list,
        description="Componentes instalados en la reforma"
    )

    # Taller ejecutor
    taller: Taller

    # Ingeniero redactor
    ingeniero: Ingeniero

    # Datos de expediente (opcionales)
    numero_expediente: Optional[str] = Field(None, description="Nº de expediente interno del ingeniero")
    fecha_proyecto: Optional[str] = Field(None, description="Fecha del proyecto, ej. '11/03/2026'")


# ─────────────────────────────────────────────
#  DATOS INTERMEDIOS (generados por los agentes)
# ─────────────────────────────────────────────

class FichaCR(BaseModel):
    """Ficha CR recuperada del RAG."""
    codigo: str = Field(..., description="Código CR, ej. '2.1'")
    denominacion: str = Field(..., description="Nombre oficial de la reforma")
    via: str = Field(..., description="Vía de tramitación: 'A', 'B', 'C' o combinación")
    documentacion: list[str] = Field(default_factory=list, description="Documentación exigible")
    informacion_adicional: Optional[str] = None
    ars: list[dict] = Field(default_factory=list, description="Actos Reglamentarios con aplicabilidad por categoría")
    texto_completo: Optional[str] = Field(None, description="Texto completo recuperado del RAG")


class ARFiltrado(BaseModel):
    """AR filtrado para la categoría del vehículo."""
    sistema: str
    referencia: str
    nivel_exigencia: str = Field(..., description="'(1)', '(2)' o '(3)'")
    descripcion_nivel: str = Field(..., description="Descripción del nivel de exigencia")
    codigo_cr: str = Field(..., description="CR al que pertenece este AR")


# ─────────────────────────────────────────────
#  SECCIONES GENERADAS
# ─────────────────────────────────────────────

class EstadoRevision(BaseModel):
    estado: str = Field(..., description="'pendiente', 'aprobado' o 'reescribir'")
    motivo: Optional[str] = Field(None, description="Motivo si el estado es 'reescribir'")
    iteraciones: int = Field(default=0, description="Número de veces que se ha regenerado esta sección")


class SeccionGenerada(BaseModel):
    id_seccion: str = Field(..., description="Identificador único, ej. 'antecedentes'")
    titulo: str = Field(..., description="Título de la sección, ej. '1.2 Antecedentes'")
    contenido: str = Field(..., description="Texto generado por el LLM")
    revision: EstadoRevision = Field(
        default_factory=lambda: EstadoRevision(estado="pendiente")
    )
    requiere_adjunto: bool = Field(default=False)
    adjunto_descripcion: Optional[str] = Field(
        None,
        description="Descripción del adjunto esperado, ej. 'Cálculos justificativos (PDF)'"
    )
    adjunto_bytes: Optional[bytes] = Field(None, description="Contenido del fichero subido")
    adjunto_nombre: Optional[str] = Field(None, description="Nombre del fichero subido")


# ─────────────────────────────────────────────
#  RESPUESTAS DE LA API
# ─────────────────────────────────────────────

class RespuestaGeneracion(BaseModel):
    """Respuesta del endpoint POST /proyecto-tecnico/generar"""
    proyecto_id: str
    secciones: list[SeccionGenerada]
    crs_identificados: list[FichaCR]
    ars_filtrados: list[ARFiltrado]
    mensaje: str = "Proyecto técnico generado correctamente"


class SolicitudRevision(BaseModel):
    """Body del endpoint POST /proyecto-tecnico/{id}/revisar"""
    id_seccion: str
    estado: str = Field(..., description="'aprobado' o 'reescribir'")
    motivo: Optional[str] = None


class SolicitudAdjunto(BaseModel):
    """Metadata del adjunto (el fichero va como multipart/form-data)"""
    proyecto_id: str
    id_seccion: str


class SolicitudGenerarDocumento(BaseModel):
    """Body del endpoint POST /proyecto-tecnico/{id}/documento"""
    proyecto_id: str
    formato: str = Field(default="docx", description="'docx' (por ahora solo Word)")

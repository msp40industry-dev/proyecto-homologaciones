"""
Backend FastAPI — POC Sistema RAG de Reformas de Vehículos

Endpoints:
    GET  /health          → estado del servidor
    POST /consulta        → consulta RAG principal
    GET  /categorias      → lista de categorías disponibles
    GET  /vias            → lista de vías de tramitación
"""

import sys
from pathlib import Path

# Añadir raíz y backend/ al path 
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag.chain import consultar
from proyecto_tecnico.router_proyecto_tecnico import router as router_pt


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="POC Reformas de Vehículos — RAG API",
    description="API de consulta sobre el Manual de Reformas DGT (Sección I) y Reglamento (UE) 2018/858",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # en producción limitar a la URL del frontend
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(router_pt, prefix="/proyecto-tecnico", tags=["Proyecto Técnico"])

# ─── Modelos ──────────────────────────────────────────────────────────────────

class MensajeHistorial(BaseModel):
    role:    str  # "user" o "assistant"
    content: str


class ConsultaRequest(BaseModel):
    pregunta:  str                      = Field(..., min_length=1, max_length=1000,
                                                example="¿Qué documentación necesito para instalar un turbo en un M1?")
    categoria: str | None               = Field(None, example="M1",
                                                description="Filtro opcional por categoría de vehículo (M1, M2, N1...)")
    via:       str | None               = Field(None, example="A",
                                                description="Filtro opcional por vía de tramitación (A, B, C, D)")
    historial: list[MensajeHistorial]   = Field(default_factory=list,
                                                description="Turnos anteriores de la conversación (máx. 4 turnos)")


class FuenteResponse(BaseModel):
    tipo:     str
    cr:       str | None  = None
    via:      str | None  = None
    apartado: str | None  = None
    titulo:   str | None  = None
    paginas:  int | None  = None


class ConsultaResponse(BaseModel):
    respuesta: str
    fuentes:   list[FuenteResponse]
    n_docs:    int


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health", tags=["sistema"])
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/categorias", tags=["referencia"])
def get_categorias():
    return {
        "M": ["M1", "M2", "M3"],
        "N": ["N1", "N2", "N3"],
        "O": ["O1", "O2", "O3", "O4"],
    }


@app.get("/vias", tags=["referencia"])
def get_vias():
    return [
        {"via": "A", "descripcion": "Proyecto Técnico + CFO + IC + CT"},
        {"via": "B", "descripcion": "Informe de Conformidad + CT"},
        {"via": "C", "descripcion": "Solo Certificado de Taller"},
        {"via": "D", "descripcion": "Solo Documentación adicional"},
    ]


@app.post("/consulta", response_model=ConsultaResponse, tags=["rag"])
def post_consulta(body: ConsultaRequest):
    try:
        resultado = consultar(
            pregunta=body.pregunta,
            categoria=body.categoria,
            via=body.via,
            historial=[m.model_dump() for m in body.historial],
        )
        return ConsultaResponse(
            respuesta=resultado["respuesta"],
            fuentes=[FuenteResponse(**f) for f in resultado["fuentes"]],
            n_docs=resultado["n_docs"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

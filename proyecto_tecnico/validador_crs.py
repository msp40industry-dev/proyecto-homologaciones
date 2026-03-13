"""
validador_crs.py — Lógica de validación de Códigos de Reforma (CRs) antes de generar el proyecto técnico.

Fases:
  1. Recuperar cada CR indicado por el usuario desde ChromaDB (metadata exacta).
  2. Clasificar en vía A (incluir en proyecto) y otros (excluir).
  3. Analizar informacion_adicional de TODOS los CRs (sean vía A o no) con el LLM:
     si la descripción del usuario activa una condición que apunta a otro CR → recuperarlo y clasificarlo.
  4. Deduplicar (un CR solo puede aparecer una vez).
  5. Devolver resumen completo: CRs incluidos, excluidos, adicionales descubiertos, motivos.
  6. Si no queda ningún CR vía A → bloquear con documentación requerida.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

# ─── Config ───────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).resolve().parents[1]
CHROMA_DIR = BASE_DIR / "scripts_index" / "chroma_db"

# ─── Modelos de respuesta ─────────────────────────────────────────────────────


class CRValidado(BaseModel):
    cr: str
    descripcion: str
    via: str                                    # "A", "B", "C"
    incluido: bool                              # True = va al proyecto
    motivo_exclusion: Optional[str] = None      # si incluido=False
    es_adicional: bool = False                  # True = descubierto via informacion_adicional
    cr_origen: Optional[str] = None             # CR que lo mencionó en informacion_adicional


class ResultadoValidacion(BaseModel):
    valido: bool                          # True si hay al menos un CR vía A
    crs_incluidos: list[CRValidado]       # CRs que van al proyecto (vía A)
    crs_excluidos: list[CRValidado]       # CRs que no van (vía B/C o excluidos)
    crs_adicionales: list[CRValidado]     # Descubiertos vía informacion_adicional (incluidos o no)
    mensaje_bloqueo: Optional[str]        # Si valido=False, mensaje explicativo
    documentacion_requerida: dict         # Si valido=False, qué documentación se necesita


# ─── Helpers ChromaDB ─────────────────────────────────────────────────────────

def _get_coleccion() -> Chroma:
    return Chroma(
        collection_name="fichas_cr",
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
        persist_directory=str(CHROMA_DIR),
    )


def _recuperar_ficha_cr(col: Chroma, cr: str) -> Optional[Document]:
    """Recupera una ficha CR por código exacto usando metadata."""
    resultado = col.get(
        where={"cr": cr},
        include=["documents", "metadatas"],
    )
    if resultado["documents"]:
        return Document(
            page_content=resultado["documents"][0],
            metadata=resultado["metadatas"][0],
        )
    return None


def _extraer_documentacion(doc: Document) -> dict:
    """
    Extrae documentación requerida del texto de la ficha.
    Busca el patrón 'Documentación exigible: ...' en el chunk indexado.
    """
    texto = doc.page_content
    docs = {}
    for linea in texto.split("\n"):
        if linea.startswith("Documentación exigible:"):
            partes = linea.replace("Documentación exigible:", "").strip()
            for item in partes.split(","):
                item = item.strip()
                if ": " in item:
                    k, v = item.split(": ", 1)
                    docs[k.strip()] = v.strip()
    return docs


# ─── Fase 3: Análisis LLM de informacion_adicional ───────────────────────────

_SISTEMA_ANALISIS = """Eres un experto en el Manual de Reformas de Vehículos de la DGT española.

Tu tarea es analizar el campo "Información adicional" de una ficha CR y determinar si la 
descripción de la reforma del usuario activa alguna condición que implique revisar otro 
Código de Reforma (CR) distinto.

REGLAS:
- Solo debes identificar CRs ADICIONALES explícitamente mencionados en la información adicional.
- Analiza si la descripción del usuario encaja con la condición descrita.
- Si la condición NO aplica a la descripción del usuario, no reportes ningún CR adicional.
- Si la información adicional no menciona otros CRs, responde con lista vacía.
- Responde ÚNICAMENTE con JSON válido, sin texto adicional.

Formato de respuesta:
{
  "crs_adicionales": [
    {
      "cr": "X.XX",
      "condicion": "descripción breve de la condición que se cumple",
      "aplica": true
    }
  ]
}
"""


def _analizar_informacion_adicional(
    cr: str,
    texto_ficha: str,
    descripcion_usuario: str,
    llm: ChatOpenAI,
) -> list[dict]:
    """
    Llama al LLM para detectar CRs adicionales mencionados en informacion_adicional
    que se activen por la descripción del usuario.
    Devuelve lista de {"cr": "X.XX", "condicion": "...", "aplica": True}.
    """
    # Extraer solo la línea de información adicional del texto indexado
    info_adicional = ""
    for linea in texto_ficha.split("\n"):
        if linea.startswith("Información adicional:"):
            info_adicional = linea.replace("Información adicional:", "").strip()
            break

    if not info_adicional:
        return []

    prompt = f"""CR analizado: {cr}
Información adicional de la ficha: {info_adicional}
Descripción de la reforma del usuario: {descripcion_usuario}

¿La descripción del usuario activa alguna condición de la información adicional que implique 
revisar otro CR? Identifica solo CRs explícitamente mencionados."""

    try:
        respuesta = llm.invoke([
            SystemMessage(content=_SISTEMA_ANALISIS),
            HumanMessage(content=prompt),
        ])
        datos = json.loads(respuesta.content.strip())
        return [
            item for item in datos.get("crs_adicionales", [])
            if item.get("aplica", False)
        ]
    except Exception:
        return []


# ─── Función principal ────────────────────────────────────────────────────────

async def validar_crs(
    crs_indicados: list[str],
    descripcion: str,
) -> ResultadoValidacion:
    """
    Valida los CRs indicados por el usuario aplicando la lógica completa de 4 fases.
    """
    col = _get_coleccion()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    crs_incluidos: list[CRValidado] = []
    crs_excluidos: list[CRValidado] = []
    crs_adicionales_resultado: list[CRValidado] = []

    # CR codes ya procesados para deduplicar
    procesados: set[str] = set()

    # ── Fase 1 + 2: Recuperar y clasificar CRs indicados ─────────────────────
    fichas_recuperadas: dict[str, Document] = {}  # cr -> Document

    for cr in crs_indicados:
        if cr in procesados:
            continue
        procesados.add(cr)

        doc = _recuperar_ficha_cr(col, cr)
        if doc is None:
            # CR no encontrado en la base de datos
            crs_excluidos.append(CRValidado(
                cr=cr,
                descripcion="No encontrado en la base de datos",
                via="?",
                incluido=False,
                motivo_exclusion="CR no encontrado en el Manual de Reformas indexado.",
            ))
            continue

        fichas_recuperadas[cr] = doc
        meta = doc.metadata
        via = meta.get("via_tramitacion", "?")

        # Extraer descripción del CR del texto del chunk (primera línea)
        desc_cr = doc.page_content.split("\n")[0].replace(f"CR {cr}: ", "").strip()

        if via == "A":
            crs_incluidos.append(CRValidado(
                cr=cr,
                descripcion=desc_cr,
                via=via,
                incluido=True,
            ))
        else:
            crs_excluidos.append(CRValidado(
                cr=cr,
                descripcion=desc_cr,
                via=via,
                incluido=False,
                motivo_exclusion=f"Vía {via} — no requiere Proyecto Técnico.",
            ))

    # ── Fase 3: Analizar informacion_adicional de TODOS los CRs recuperados ──
    # (tanto los vía A como los vía B/C)
    crs_adicionales_detectados: dict[str, dict] = {}  # cr_nuevo -> {condicion, cr_origen}

    for cr, doc in fichas_recuperadas.items():
        adicionales = _analizar_informacion_adicional(cr, doc.page_content, descripcion, llm)
        for item in adicionales:
            cr_nuevo = item["cr"]
            if cr_nuevo not in procesados and cr_nuevo not in crs_adicionales_detectados:
                crs_adicionales_detectados[cr_nuevo] = {
                    "condicion": item["condicion"],
                    "cr_origen": cr,
                }

    # ── Fase 4: Recuperar y clasificar CRs adicionales descubiertos ──────────
    for cr_nuevo, info in crs_adicionales_detectados.items():
        procesados.add(cr_nuevo)
        doc = _recuperar_ficha_cr(col, cr_nuevo)

        if doc is None:
            crs_adicionales_resultado.append(CRValidado(
                cr=cr_nuevo,
                descripcion="No encontrado en la base de datos",
                via="?",
                incluido=False,
                motivo_exclusion="CR adicional no encontrado en el Manual de Reformas indexado.",
                es_adicional=True,
                cr_origen=info["cr_origen"],
            ))
            continue

        meta = doc.metadata
        via = meta.get("via_tramitacion", "?")
        desc_cr = doc.page_content.split("\n")[0].replace(f"CR {cr_nuevo}: ", "").strip()

        if via == "A":
            cr_validado = CRValidado(
                cr=cr_nuevo,
                descripcion=desc_cr,
                via=via,
                incluido=True,
                es_adicional=True,
                cr_origen=info["cr_origen"],
            )
            crs_adicionales_resultado.append(cr_validado)
            # También añadir a incluidos para el proyecto
            crs_incluidos.append(cr_validado)
        else:
            cr_validado = CRValidado(
                cr=cr_nuevo,
                descripcion=desc_cr,
                via=via,
                incluido=False,
                motivo_exclusion=(
                    f"Vía {via} — no requiere Proyecto Técnico. "
                    f"Condición activada: {info['condicion']}"
                ),
                es_adicional=True,
                cr_origen=info["cr_origen"],
            )
            crs_adicionales_resultado.append(cr_validado)
            crs_excluidos.append(cr_validado)

    # ── Fase 5: Determinar si el resultado es válido ──────────────────────────
    valido = len(crs_incluidos) > 0

    mensaje_bloqueo = None
    documentacion_requerida: dict = {}

    if not valido:
        # Recopilar documentación requerida de los CRs excluidos
        for cr in list(fichas_recuperadas.keys()) + list(crs_adicionales_detectados.keys()):
            doc = fichas_recuperadas.get(cr) or _recuperar_ficha_cr(col, cr)
            if doc:
                docs = _extraer_documentacion(doc)
                documentacion_requerida.update(docs)

        vias = list({
            c.via for c in crs_excluidos + crs_adicionales_resultado if c.via != "?"
        })
        mensaje_bloqueo = (
            f"Ninguno de los CRs identificados ({', '.join(crs_indicados)}) "
            f"requiere Proyecto Técnico (Vía A). "
            f"La tramitación es por Vía {'/'.join(vias)}. "
            f"Documentación necesaria: {', '.join(documentacion_requerida.keys()) or 'ver fichas CR'}."
        )

    return ResultadoValidacion(
        valido=valido,
        crs_incluidos=crs_incluidos, 
        crs_excluidos=crs_excluidos,
        crs_adicionales=crs_adicionales_resultado,
        mensaje_bloqueo=mensaje_bloqueo,
        documentacion_requerida=documentacion_requerida,
    )
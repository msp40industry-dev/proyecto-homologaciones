"""
identificador_cr.py — Agente 1 (gpt-4o)

Responsabilidad:
  - Si el ingeniero ya indicó CRs: recupera las fichas directamente del RAG.
  - Si no indicó CRs (o solo algunos): usa retrieval semántico sobre la descripción
    de la reforma para identificarlos.
  - En ambos casos, detecta referencias cruzadas en el campo informacion_adicional
    (ej. "implica también el CR 2.1").
  - Filtra los ARs por la categoría del vehículo.
  - Devuelve lista de FichaCR y lista de ARFiltrado.
"""

from __future__ import annotations
import json
import re
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # PROYECTO_HOMOLOGACIONES/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))   # para encontrar rag/

from rag.retriever import recuperar
from proyecto_tecnico.models import FichaCR, ARFiltrado

_CHROMA_DIR = ROOT / "scripts_index" / "chroma_db"

# Modelo: gpt-4o — tarea crítica de razonamiento
_llm = ChatOpenAI(model="gpt-4o", temperature=0.0)

DESCRIPCIONES_NIVEL = {
    "(1)": "Se aplica en su última actualización en vigor a fecha de tramitación",
    "(2)": "Se aplica en la actualización en vigor a fecha de primera matriculación del vehículo",
    "(3)": "Se aplica en la actualización previa a la entrada en vigor de los Reglamentos Delegados UE 167/2013 o 168/2013",
}

SYSTEM_PROMPT = """Eres un experto técnico en el Manual de Reformas de la DGT (España).
Tu tarea es analizar la descripción de una reforma de vehículo y determinar qué Códigos de Reforma (CR) aplican.

Se te proporcionará:
1. La descripción de la reforma realizada por el ingeniero.
2. Los documentos de las fichas CR recuperadas del sistema RAG.

Debes responder ÚNICAMENTE con un JSON válido con esta estructura:
{
  "crs_identificados": [
    {
      "codigo": "2.1",
      "justificacion": "La reforma descrita corresponde a una modificación del motor..."
    }
  ],
  "crs_adicionales_detectados": [
    {
      "codigo": "4.4",
      "fuente": "El campo informacion_adicional del CR 2.1 indica que implica validación del CR 4.4",
      "justificacion": "..."
    }
  ]
}

REGLAS:
- Solo incluye CRs que estén claramente justificados por la descripción de la reforma.
- Revisa SIEMPRE el campo informacion_adicional de cada ficha CR para detectar CRs adicionales implícitos.
- Si la reforma no corresponde a ningún CR recuperado, indica crs_identificados vacío.
- No inventes CRs. Solo usa los que aparezcan en los documentos proporcionados.
- No añadas texto fuera del JSON."""


async def identificar_crs(
    descripcion: str,
    crs_indicados: list[str],
    categoria: str,
) -> tuple[list[FichaCR], list[ARFiltrado]]:
    """
    Punto de entrada del Agente 1.
    Devuelve (crs_identificados, ars_filtrados).
    """

    # ── 1. Recuperar fichas del RAG ────────────────────────────────────────────
    resultado = recuperar(query=descripcion, categoria=categoria, historial=None)
    docs_por_descripcion = (
        resultado.get("fichas", []) +
        resultado.get("preambulo", []) +
        resultado.get("reglamento", [])
    )

    # Si el ingeniero ya indicó CRs, recuperarlos por código exacto (metadato)
    docs_por_cr: list = []
    for cr in crs_indicados:
        doc = _recuperar_ficha_por_codigo(cr)
        if doc:
            docs_por_cr.append(doc)

    # Combinar y deduplicar por contenido
    todos_docs = _deduplicar_docs(docs_por_descripcion + docs_por_cr)
    contexto_rag = "\n\n---\n\n".join([d.page_content for d in todos_docs])

    # ── 2. Llamar al LLM para identificar CRs ─────────────────────────────────
    prompt_usuario = f"""DESCRIPCIÓN DE LA REFORMA:
{descripcion}

CRs INDICADOS POR EL INGENIERO (pueden estar incompletos o vacíos): {crs_indicados}

FICHAS CR RECUPERADAS DEL SISTEMA RAG:
{contexto_rag}

Analiza la descripción y los documentos. Identifica todos los CRs aplicables."""

    respuesta = await _llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt_usuario),
    ])

    # ── 3. Parsear la respuesta JSON ───────────────────────────────────────────
    try:
        datos = json.loads(respuesta.content)
    except json.JSONDecodeError:
        # Intentar extraer JSON si el modelo añadió texto extra
        match = re.search(r'\{.*\}', respuesta.content, re.DOTALL)
        datos = json.loads(match.group()) if match else {"crs_identificados": [], "crs_adicionales_detectados": []}

    codigos_finales = set()
    for item in datos.get("crs_identificados", []):
        codigos_finales.add(item["codigo"])
    for item in datos.get("crs_adicionales_detectados", []):
        codigos_finales.add(item["codigo"])
    # Añadir siempre los indicados por el ingeniero
    for cr in crs_indicados:
        codigos_finales.add(cr)

    # ── 4. Construir objetos FichaCR a partir de los docs recuperados ──────────
    fichas = _construir_fichas_cr(codigos_finales, todos_docs)

    # ── 5. Filtrar ARs por categoría ──────────────────────────────────────────
    ars = _filtrar_ars(fichas, categoria)

    return fichas, ars


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _recuperar_ficha_por_codigo(cr: str) -> Document | None:
    """Recupera una ficha CR por código exacto usando metadatos (sin búsqueda semántica)."""
    col = Chroma(
        collection_name="fichas_cr",
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
        persist_directory=str(_CHROMA_DIR),
    )
    resultado = col.get(where={"cr": cr}, include=["documents", "metadatas"])
    if resultado["documents"]:
        return Document(
            page_content=resultado["documents"][0],
            metadata=resultado["metadatas"][0],
        )
    return None


def _deduplicar_docs(docs: list) -> list:
    vistos = set()
    resultado = []
    for doc in docs:
        clave = doc.page_content[:100]
        if clave not in vistos:
            vistos.add(clave)
            resultado.append(doc)
    return resultado


def _construir_fichas_cr(codigos: set[str], docs: list) -> list[FichaCR]:
    fichas = []
    for codigo in sorted(codigos):
        doc_cr = None
        for doc in docs:
            meta = doc.metadata or {}
            # La clave correcta es "cr", no "codigo_cr"
            if str(meta.get("cr", "")) == codigo:
                doc_cr = doc
                break

        if doc_cr:
            meta = doc_cr.metadata or {}
            ficha = FichaCR(
                codigo=codigo,
                denominacion=_extraer_denominacion(doc_cr.page_content, codigo),
                via=meta.get("via_tramitacion", _extraer_via(doc_cr.page_content)),
                documentacion=_extraer_documentacion(doc_cr.page_content),
                informacion_adicional=meta.get("informacion_adicional", ""),
                ars=_extraer_ars_raw(doc_cr.page_content),
                texto_completo=doc_cr.page_content,
            )
        else:
            ficha = FichaCR(
                codigo=codigo,
                denominacion=f"Reforma {codigo} (pendiente de verificar en manual)",
                via="A",
                texto_completo="",
            )
        fichas.append(ficha)

    return fichas


def _filtrar_ars(fichas: list[FichaCR], categoria: str) -> list[ARFiltrado]:
    """Filtra los ARs de todas las fichas para la categoría dada."""
    ars_filtrados = []
    patron = re.compile(rf"{re.escape(categoria)}:\s*([^,\n]+)", re.IGNORECASE)

    for ficha in fichas:
        if not ficha.texto_completo:
            continue
        lineas = ficha.texto_completo.split("\n")
        en_ars = False
        for linea in lineas:
            if "Actos Reglamentarios aplicables:" in linea:
                en_ars = True
                continue
            if en_ars and linea.strip().startswith("---"):
                en_ars = False
                continue
            if en_ars and linea.strip().startswith("- "):
                match = patron.search(linea)
                if match:
                    valor = match.group(1).strip()
                    if valor not in ("-", "x"):
                        # Extraer sistema y referencia
                        base = re.sub(r":\s*M\d.*", "", linea).strip().lstrip("- ").strip()
                        partes = base.split("(")
                        sistema = partes[0].strip()
                        referencia = f"({partes[1]}" if len(partes) > 1 else ""
                        ars_filtrados.append(ARFiltrado(
                            sistema=sistema,
                            referencia=referencia.rstrip(")") + ")" if referencia else "",
                            nivel_exigencia=valor,
                            descripcion_nivel=DESCRIPCIONES_NIVEL.get(valor, valor),
                            codigo_cr=ficha.codigo,
                        ))

    return ars_filtrados


def _extraer_denominacion(texto: str, codigo: str) -> str:
    match = re.search(r"Denominación:\s*(.+)", texto)
    return match.group(1).strip() if match else f"Reforma {codigo}"


def _extraer_via(texto: str) -> str:
    match = re.search(r"Vía[s]?[:\s]+([A-C/,\s]+)", texto)
    return match.group(1).strip() if match else "A"


def _extraer_documentacion(texto: str) -> list[str]:
    docs = []
    en_docs = False
    for linea in texto.split("\n"):
        if "Documentación exigible:" in linea or "Documentación:" in linea:
            en_docs = True
            continue
        if en_docs:
            if linea.strip().startswith("- "):
                docs.append(linea.strip().lstrip("- ").strip())
            elif linea.strip().startswith("---") or (linea.strip() and not linea.strip().startswith("-")):
                break
    return docs


def _extraer_ars_raw(texto: str) -> list[dict]:
    """Extrae los ARs en formato raw (sin filtrar por categoría)."""
    ars = []
    en_ars = False
    for linea in texto.split("\n"):
        if "Actos Reglamentarios aplicables:" in linea:
            en_ars = True
            continue
        if en_ars and linea.strip().startswith("---"):
            break
        if en_ars and linea.strip().startswith("- "):
            ars.append({"texto": linea.strip()})
    return ars

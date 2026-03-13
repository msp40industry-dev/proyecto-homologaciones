"""
Retriever — recupera chunks relevantes de Chroma para una query dada.

Estrategia de retrieval:
  1. Busca siempre en fichas_cr (colección principal)
  2. Busca en preambulo solo si la query o la vía recuperada lo requiere
  3. Busca en reglamento_ue si la query menciona categorías de vehículo
  4. Aplica filtros de metadatos opcionales (categoría, vía)
"""

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from . import config

# ─── Keywords que activan retrieval en colecciones secundarias ────────────────

KEYWORDS_PREAMBULO = [
    "proyecto técnico", "informe de conformidad", "certificado de taller",
    "certificación final", "documentación", "cfo", "ic", "pt", "ct",
    "qué necesito", "qué documentos", "cómo se tramita"
]

KEYWORDS_REGLAMENTO = [
    "m1", "m2", "m3", "n1", "n2", "n3", "o1", "o2", "o3", "o4",
    "categoría", "categoria", "tipo de vehículo", "turismo", "furgoneta",
    "camión", "remolque", "todoterreno", "4x4"
]

# Añadir palabras aquí si vemos que las preguntas no recuperan el preámbulo o el reglamento.

# ─── Inicialización de colecciones ───────────────────────────────────────────

def _get_embeddings():
    return OpenAIEmbeddings(
        api_key=config.OPENAI_API_KEY,
        model=config.EMBEDDING_MODEL,
    )

def _get_coleccion(nombre: str) -> Chroma:
    return Chroma(
        collection_name=nombre,
        embedding_function=_get_embeddings(),
        persist_directory=str(config.CHROMA_DIR),
    )

# ─── Lógica de retrieval ─────────────────────────────────────────────────────

def _necesita_preambulo(query: str, fichas_recuperadas: list) -> bool:
    """Activa retrieval en preámbulo si la query o las fichas lo sugieren."""
    query_lower = query.lower()
    if any(kw in query_lower for kw in KEYWORDS_PREAMBULO):
        return True
    # Si alguna ficha recuperada tiene vía A, añadir chunk de proyecto_tecnico
    for doc in fichas_recuperadas:
        if doc.metadata.get("via_tramitacion") in ("A", "B"):
            return True
    return False


def _necesita_reglamento(query: str) -> bool:
    """Activa retrieval en reglamento si la query menciona categorías."""
    query_lower = query.lower()
    return any(kw in query_lower for kw in KEYWORDS_REGLAMENTO)


def _filtro_fichas(categoria: str | None, via: str | None) -> dict | None:
    if via:
        return {"via_tramitacion": via.upper()}
    return None


def recuperar(
    query: str,
    categoria: str | None = None,
    via: str | None = None,
    historial: list[dict] | None = None,
) -> dict[str, list]:
    """
    Punto de entrada principal del retriever.

    Args:
        query:     Pregunta del usuario
        categoria: Filtro opcional de categoría (ej. 'M1', 'N1')
        via:       Filtro opcional de vía (ej. 'A', 'B')

    Returns:
        dict con listas de documentos por fuente:
        {
            "fichas":    [Document, ...],
            "preambulo": [Document, ...],
            "reglamento": [Document, ...]
        }
    """

    # Si query corta, enriquecer con el último mensaje del usuario
    if len(query.split()) < 6 and historial:
        ultimos = [m["content"] for m in historial if m["role"] == "user"]
        if len(ultimos) >= 2:
            query = f"{ultimos[-2]} {query}"

    resultados = {"fichas": [], "preambulo": [], "reglamento": []}

    # 1. Fichas CR — siempre
    col_fichas = _get_coleccion(config.COLECCION_FICHAS)
    filtro = _filtro_fichas(categoria, via)

    kwargs = {"k": config.N_RESULTS_FICHAS}
    if filtro:
        kwargs["filter"] = filtro

    resultados["fichas"] = col_fichas.similarity_search(query, **kwargs)

    # 2. Preámbulo — condicional
    if _necesita_preambulo(query, resultados["fichas"]):
        col_preamb = _get_coleccion(config.COLECCION_PREAMBULO)

        # Filtrar chunks que NO son el de interpretacion_ars
        # (ya está inyectado en las fichas, no queremos duplicarlo)
        resultados["preambulo"] = col_preamb.similarity_search(
            query,
            k=config.N_RESULTS_PREAMBULO,
            filter={"apartado": {"$ne": "interpretacion_ars"}},
        )

    # 3. Reglamento UE — condicional
    if _necesita_reglamento(query):
        col_reg = _get_coleccion(config.COLECCION_REGLAMENTO)
        resultados["reglamento"] = col_reg.similarity_search(
            query,
            k=config.N_RESULTS_REGLAMENTO,
        )

    return resultados

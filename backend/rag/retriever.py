"""
Retriever — recupera chunks relevantes de Chroma para una query dada.

Estrategia de retrieval:
  1. Busca siempre en fichas_cr (colección principal)
  2. Busca en preambulo solo si la query o la vía recuperada lo requiere
  3. Busca en reglamento_ue si la query menciona categorías de vehículo
  4. Aplica filtros de metadatos opcionales (categoría, vía)
"""

import re

from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

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

KEYWORDS_DIRECTIVAS = [
    "directiva", "qué establece", "qué dice", "qué regula",
    "contenido del ar", "normativa de", "/cee", "/ce ",
    "reglamento ce ", "reglamento ue ", "texto del reglamento",
    "cumplimiento de", "requisitos del", "está en vigor", "derogad",
]

# Palabras que indican que el usuario pregunta sobre ARs ya listados en el historial
KEYWORDS_REFERENCIAL_AR = [
    "en qué consisten", "qué consiste", "qué son", "para qué sirven",
    "explícame", "cuéntame", "describe", "detalla",
    "cada una", "cada uno", "esas", "esos", "los ar", "las ar",
    "qué regulan", "qué cubren", "qué implican",
]

# Detecta referencias normativas EU en el texto de la query
_PAT_REF_AR = re.compile(
    r'\b\d{2,4}/\d+/C(?:EE|E)\b'
    r'|R\s*\(UE\)\s*\d+/\d{4}'
    r'|Reglamento\s+\(C[EE]\)\s+N[oº°]?\s*\d+/\d{4}',
    re.IGNORECASE,
)

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

# ─── Expansión de query ───────────────────────────────────────────────────────

_PROMPT_EXPANSION = (
    "Eres un experto en el Manual de Reformas de Vehículos DGT (España).\n"
    "Reformula la consulta usando exclusivamente terminología técnica oficial del Manual: "
    "nombres de sistemas (suspensión, frenado, motor, carrocería, alumbrado...), "
    "componentes (amortiguadores, actos reglamentarios, elementos elásticos...) "
    "y denominaciones de grupos de reforma.\n"
    "Devuelve SOLO los términos técnicos relevantes, sin explicaciones ni puntuación extra.\n\n"
    "Consulta: {query}"
)


def _expandir_query(query: str) -> str:
    """
    Reformula la query del usuario con terminología DGT oficial para cerrar la brecha
    semántica entre lenguaje coloquial y nombres técnicos del Manual.
    Concatena la expansión a la query original para preservar ambas señales.
    Fallback silencioso si el LLM falla.
    """
    try:
        llm = ChatOpenAI(
            api_key=config.OPENAI_API_KEY,
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=100,
        )
        expansion = llm.invoke(_PROMPT_EXPANSION.format(query=query)).content.strip()
        return f"{query} {expansion}" if expansion else query
    except Exception:
        return query


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


def _necesita_directivas(query: str) -> bool:
    """Activa retrieval en directivas_ar si la query menciona normativa específica."""
    if _PAT_REF_AR.search(query):
        return True
    q = query.lower()
    return any(kw in q for kw in KEYWORDS_DIRECTIVAS)


def _refs_ar_en_query(query: str) -> list[str]:
    """Extrae referencias normativas EU detectadas en el texto de la query."""
    return [m.group().strip() for m in _PAT_REF_AR.finditer(query)]


def _refs_ar_en_historial(historial: list[dict] | None) -> list[str]:
    """
    Busca el mensaje del asistente más reciente que contenga una tabla de ARs (≥ 3 refs).
    Eso corresponde a la respuesta de una ficha CR con su lista de ARs.
    Si no hay ninguno con ≥ 3, devuelve las refs del último mensaje del asistente con alguna.
    """
    if not historial:
        return []

    def _extraer_unicas(texto: str) -> list[str]:
        vistas: set[str] = set()
        resultado: list[str] = []
        for m in _PAT_REF_AR.finditer(texto):
            r = m.group().strip()
            if r not in vistas:
                vistas.add(r)
                resultado.append(r)
        return resultado

    fallback: list[str] = []
    for msg in reversed(historial):
        if msg["role"] != "assistant":
            continue
        refs = _extraer_unicas(msg["content"])
        if len(refs) >= 3:
            return refs          # tabla CR encontrada
        if refs and not fallback:
            fallback = refs      # guardar por si no hay tabla
    return fallback


def _pregunta_sobre_ars_del_historial(query: str, historial: list[dict] | None) -> bool:
    """True si el usuario pregunta sobre los ARs ya listados en el turno anterior."""
    if not historial:
        return False
    q = query.lower()
    return (
        any(kw in q for kw in KEYWORDS_REFERENCIAL_AR)
        and bool(_refs_ar_en_historial(historial))
    )


def _filtro_fichas(via: str | None, seccion: str | None) -> dict | None:
    condiciones = []
    if via:
        condiciones.append({"via_tramitacion": via.upper()})
    if seccion:
        condiciones.append({"seccion": seccion.upper()})
    if len(condiciones) == 1:
        return condiciones[0]
    if len(condiciones) > 1:
        return {"$and": condiciones}
    return None


def recuperar(
    query: str,
    categoria: str | None = None,
    via: str | None = None,
    historial: list[dict] | None = None,
    seccion: str | None = None,
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

    # Guardar query original para checks referenciales (antes de cualquier transformación)
    query_original = query

    # Si query corta, enriquecer con el último mensaje del usuario
    if len(query.split()) < 6 and historial:
        ultimos = [m["content"] for m in historial if m["role"] == "user"]
        if len(ultimos) >= 2:
            query = f"{ultimos[-2]} {query}"

    # Expansión semántica: reformular con terminología DGT antes del embedding
    query = _expandir_query(query)

    resultados = {"fichas": [], "preambulo": [], "reglamento": [], "directivas": []}

    # Si la pregunta es sobre las directivas AR del historial, reducimos fichas para no
    # ahogar el contexto — las fichas no son el foco en ese caso.
    _foco_directivas = _pregunta_sobre_ars_del_historial(query_original, historial)

    # 1. Fichas CR — siempre
    col_fichas = _get_coleccion(config.COLECCION_FICHAS)
    filtro = _filtro_fichas(via, seccion)

    k_fichas = 1 if _foco_directivas else config.N_RESULTS_FICHAS
    kwargs = {"k": k_fichas}
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

    # 4. Directivas AR — cuando la query menciona una normativa específica
    if _necesita_directivas(query):
        col_dir = _get_coleccion(config.COLECCION_DIRECTIVAS)
        refs = _refs_ar_en_query(query)
        if refs:
            docs = col_dir.similarity_search(
                query,
                k=config.N_RESULTS_DIRECTIVAS,
                filter={"referencia": refs[0]},
            )
            if not docs:
                docs = col_dir.similarity_search(query, k=config.N_RESULTS_DIRECTIVAS)
            resultados["directivas"] = docs
        else:
            resultados["directivas"] = col_dir.similarity_search(
                query, k=config.N_RESULTS_DIRECTIVAS
            )

    # 4b. Fallback: el usuario pregunta sobre los ARs listados en la respuesta anterior
    #     ("en qué consisten esas ARs", "explícame cada una", etc.) sin citar referencias.
    #     Se usa query_original para no perder las palabras clave tras la expansión semántica.
    if not resultados["directivas"] and _pregunta_sobre_ars_del_historial(query_original, historial):
        col_dir = _get_coleccion(config.COLECCION_DIRECTIVAS)
        refs_hist = _refs_ar_en_historial(historial)
        docs: list = []
        seen: set = set()
        for ref in refs_hist[:12]:
            if ref in seen:
                continue
            seen.add(ref)
            # Query orientada al articulado técnico para evitar recuperar la cabecera EUR-Lex.
            # chunk_num > 0 descarta el chunk de título/cabecera.
            query_tecnica = f"prescripciones técnicas requisitos instalación {ref}"
            encontrados = col_dir.similarity_search(
                query_tecnica, k=3,
                filter={"$and": [{"referencia": ref}, {"chunk_num": {"$gt": 0}}]},
            )
            if not encontrados:
                encontrados = col_dir.similarity_search(
                    query_tecnica, k=3, filter={"referencia": ref}
                )
            docs.extend(encontrados)
        resultados["directivas"] = docs

    return resultados

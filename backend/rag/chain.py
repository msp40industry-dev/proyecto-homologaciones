"""
Chain — cadena RAG: contexto recuperado + prompt + GPT-4o mini.

El prompt instruye al modelo para:
  - Responder SOLO en base a los documentos proporcionados
  - Citar explícitamente el CR o apartado fuente
  - Decir "no tengo información" si la respuesta no está en el contexto
  - Usar lenguaje técnico pero claro
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.documents import Document

from . import config
from .retriever import recuperar

# ─── Prompt de sistema ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un asistente técnico especializado en reformas de vehículos en España.
Respondes preguntas sobre el Manual de Reformas de la DGT (Sección I) y el Reglamento (UE) 2018/858.

REGLAS:
1. ANTES DE RESPONDER, revisa siempre el campo "Información adicional" de cada ficha CR recuperada. Si contiene casos donde la reforma NO aplica a lo que describe el usuario, indícalo como primer punto de la respuesta y no continúes con documentación ni ARs. Ejemplos de exclusiones típicas:
   - "No se considera reforma cuando..."
   - "Esta reforma no aplica a..."
   - Instalaciones que están expresamente excluidas del CR
   Si hay duda sobre si la exclusión aplica al caso del usuario, pregúntale antes de continuar.
2. Responde ÚNICAMENTE en base a los documentos de contexto proporcionados.
3. Si la información no está en el contexto, responde exactamente: "No tengo información suficiente en los documentos disponibles para responder esta pregunta."
4. Cita siempre la fuente: indica el CR (ej. "según CR 2.1") o el apartado (ej. "según el apartado 5.1 del preámbulo").
5. Sé conciso y directo. Usa listas cuando enumeres requisitos o pasos.
6. Si la reforma requiere proyecto técnico (Vía A), indícalo claramente al inicio de la respuesta.
7. No añadas información que no esté en el contexto, aunque la conozcas.
8. Si el usuario describe una reforma sin mencionar el CR, identifica cuál o cuáles son los CRs más probables basándote en el contexto recuperado y explica brevemente por qué.
9. Tienes memoria de los últimos mensajes de la conversación. Si el usuario hace referencia a algo mencionado antes (ej. "¿y si es un N1?", "¿qué pasa con esa reforma?"), usa el historial para entender a qué se refiere.
10. Antes de listar los ARs, SIEMPRE pregunta al usuario la categoría de su vehículo si no la has confirmado aún en la conversación. Presenta las opciones en lenguaje natural:
    "¿Qué tipo de vehículo tienes?
    - Turismo o vehículo de hasta 8 plazas (M1)
    - Furgoneta o vehículo de carga hasta 3,5t (N1)
    - Camión entre 3,5t y 12t (N2)
    - Camión de más de 12t (N3)
    - Autobús o minibús (M2/M3)"
    No listes los ARs hasta que el usuario confirme la categoría.
11. Lista TODOS los ARs del contexto donde el valor para la categoría confirmada sea (1), (2) o (3), sin excepción. Cuenta los ARs antes de responder para asegurarte de no omitir ninguno. Excluye solo los que tengan - o x.

FORMATO DE RESPUESTA:
- Respuesta directa a la pregunta
- CRs aplicables (si la pregunta describe una reforma)
- Documentación exigible (si aplica)
- Categoría utilizada para filtrar ARs: [indicar explícitamente, ej. "M1"]
- Lista de Actos Reglamentarios aplicables a [categoría] según CR [X]:
  · Sistema (Referencia): nivel de exigencia
- Fuente(s) consultada(s)"""


# ─── Construcción del contexto ────────────────────────────────────────────────
def _filtrar_ars_por_categoria(texto: str, categoria: str) -> str:
    """
    Filtra los ARs del texto para mostrar solo los de la categoría indicada.
    Excluye los que tengan - o x. Devuelve una sección ya formateada.
    """
    import re

    DESCRIPCIONES_AR = {
        "(1)": "Se aplica en su última actualización en vigor a fecha de tramitación",
        "(2)": "Se aplica en la actualización en vigor a fecha de primera matriculación del vehículo",
        "(3)": "Se aplica en la actualización previa a la entrada en vigor de los Reglamentos Delegados UE 167/2013 o 168/2013",
    }

    lineas = texto.split("\n")
    ars_filtrados = []
    en_ars = False

    for linea in lineas:
        if linea.strip().startswith("Actos Reglamentarios aplicables:"):
            en_ars = True
            continue
        if en_ars and linea.strip().startswith("---"):
            en_ars = False
            continue
        if en_ars and linea.strip().startswith("- "):
            match = re.search(
                rf"{re.escape(categoria)}:\s*([^,\n]+)", linea
            )
            if match:
                valor = match.group(1).strip()
                if valor not in ("-", "x"):
                    # Extraer solo sistema y referencia (antes del primer ":")
                    base = re.sub(r":\s*M\d.*", "", linea).strip().lstrip("- ").strip()
                    descripcion = DESCRIPCIONES_AR.get(valor, valor)
                    ars_filtrados.append(f"  - {base}: {descripcion}")

    if ars_filtrados:
        return f"Actos Reglamentarios aplicables a {categoria}:\n" + "\n".join(ars_filtrados)
    return ""


def _formatear_ficha(doc: Document, categoria: str | None = None) -> str:
    md = doc.metadata
    texto = doc.page_content

    if categoria:
        # Extraer ARs filtrados y reemplazar la sección completa
        ars_filtrados = _filtrar_ars_por_categoria(texto, categoria)
        # Eliminar la sección de ARs original del texto
        import re
        texto = re.sub(
            r"Actos Reglamentarios aplicables:.*?---",
            ars_filtrados + "\n---",
            texto,
            flags=re.DOTALL
        )

    return (
        f"[CR {md.get('cr', '?')} | Vía {md.get('via_tramitacion', '?')}]\n"
        f"{texto}"
    )


def _formatear_chunk(doc: Document, fuente: str) -> str:
    md = doc.metadata
    titulo = md.get("titulo") or md.get("apartado") or fuente
    return f"[{titulo}]\n{doc.page_content}"


def _construir_contexto(docs: dict[str, list], categoria: str | None = None) -> str:
    partes = []

    if docs["fichas"]:
        partes.append("=== FICHAS DE REFORMA ===")
        for doc in docs["fichas"]:
            partes.append(_formatear_ficha(doc, categoria=categoria))

    if docs["preambulo"]:
        partes.append("=== PREÁMBULO DEL MANUAL ===")
        for doc in docs["preambulo"]:
            partes.append(_formatear_chunk(doc, "preambulo"))

    if docs["reglamento"]:
        partes.append("=== REGLAMENTO (UE) 2018/858 ===")
        for doc in docs["reglamento"]:
            partes.append(_formatear_chunk(doc, "reglamento"))

    if not partes:
        return "No se han encontrado documentos relevantes."

    return "\n\n".join(partes)


def _extraer_fuentes(docs: dict[str, list]) -> list[dict]:
    """Devuelve lista de fuentes para incluir en la respuesta de la API."""
    fuentes = []

    for doc in docs["fichas"]:
        md = doc.metadata
        fuentes.append({
            "tipo":    "ficha_cr",
            "cr":      md.get("cr"),
            "via":     md.get("via_tramitacion"),
            "paginas": md.get("pagina_inicio"),
        })

    for doc in docs["preambulo"]:
        md = doc.metadata
        fuentes.append({
            "tipo":     "preambulo",
            "apartado": md.get("apartado"),
            "titulo":   md.get("titulo"),
        })

    for doc in docs["reglamento"]:
        md = doc.metadata
        fuentes.append({
            "tipo":     "reglamento_ue",
            "apartado": md.get("apartado"),
            "titulo":   md.get("titulo"),
        })

    return fuentes


# ─── LLM ──────────────────────────────────────────────────────────────────────

def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=config.OPENAI_API_KEY,
        model=config.GENERATION_MODEL,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS_RESPUESTA,
    )


# ─── Punto de entrada ─────────────────────────────────────────────────────────

# Número de turnos del historial a incluir (1 turno = 1 pregunta + 1 respuesta)
VENTANA_HISTORIAL = 4


def consultar(
    pregunta: str,
    categoria: str | None = None,
    via: str | None = None,
    historial: list[dict] | None = None,
) -> dict:
    """
    Ejecuta el pipeline RAG completo.

    Args:
        pregunta:  Pregunta del usuario
        categoria: Filtro opcional (ej. 'M1')
        via:       Filtro opcional (ej. 'A')
        historial: Lista de turnos anteriores en formato
                   [{"role": "user"|"assistant", "content": "..."}, ...]

    Returns:
        {
            "respuesta": str,
            "fuentes":   list[dict],
            "n_docs":    int,
        }
    """
    # 1. Retrieval
    docs = recuperar(pregunta, categoria=categoria, via=via, historial=historial)
    n_docs = sum(len(v) for v in docs.values())

    # Extraer categoría del historial si no viene explícita del sidebar
    categoria_efectiva = categoria
    if not categoria_efectiva and historial:
        import re
        # Mapeo de términos naturales a categorías
        TERMINOS = {
            "turismo": "M1", 
            "coche": "M1", 
            "todoterreno": "M1",
            "automóvil": "M1",
            "furgoneta": "N1", 
            "furgón": "N1",
            "camión": "N2", 
            "camion": "N2",
            "autobús": "M2", 
            "autobus": "M2", 
            "minibús": "M2",
        }
        todos = [m["content"] for m in historial] + [pregunta]
        for msg in reversed(todos):
            # Primero buscar código explícito
            match = re.search(r"\b(M1|M2|M3|N1|N2|N3|O1|O2|O3|O4)\b", msg, re.IGNORECASE)
            if match:
                categoria_efectiva = match.group(1).upper()
                break
            # Luego buscar término natural
            for termino, cat in TERMINOS.items():
                if termino in msg.lower():
                    categoria_efectiva = cat
                    break
            if categoria_efectiva:
                break

    # 2. Construir contexto con categoría efectiva
    contexto = _construir_contexto(docs, categoria=categoria_efectiva)

    # 3. Construir mensajes con ventana de historial
    #    Orden: system → historial (últimos N turnos) → pregunta actual con contexto
    mensajes = [SystemMessage(content=SYSTEM_PROMPT)]

    if historial:
        # Cada turno son 2 mensajes (user + assistant), tomamos los últimos VENTANA_HISTORIAL turnos
        turno_inicio = max(0, len(historial) - VENTANA_HISTORIAL * 2)
        for msg in historial[turno_inicio:]:
            if msg["role"] == "user":
                mensajes.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                mensajes.append(AIMessage(content=msg["content"]))

    # Pregunta actual con el contexto recuperado pegado delante
    mensajes.append(HumanMessage(content=(
        f"CONTEXTO:\n{contexto}\n\n"
        f"PREGUNTA: {pregunta}"
    )))

    # 4. Llamada al LLM
    llm = _get_llm()
    respuesta = llm.invoke(mensajes)

    return {
        "respuesta": respuesta.content,
        "fuentes":   _extraer_fuentes(docs),
        "n_docs":    n_docs,
    }

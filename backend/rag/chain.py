"""
Chain — cadena RAG: contexto recuperado + prompt + GPT-4o mini.

El prompt instruye al modelo para:
  - Responder SOLO en base a los documentos proporcionados
  - Citar explícitamente el CR o apartado fuente
  - Decir "no tengo información" si la respuesta no está en el contexto
  - Usar lenguaje técnico pero claro
"""

import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.documents import Document

from . import config
from .retriever import recuperar

# ─── Prompt de sistema ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un asistente técnico especializado en reformas de vehículos en España.
Respondes preguntas sobre el Manual de Reformas de la DGT (Secciones I, II, III y IV) y el Reglamento (UE) 2018/858.
La Sección I cubre vehículos M, N y O. La Sección II cubre vehículos L (motos, quads, UTVs). Las Secciones III y IV cubren vehículos agrícolas y de obras/servicios respectivamente.

REGLAS:
1. ANTES DE RESPONDER, revisa siempre el campo "Información adicional" de cada ficha CR recuperada:
   a. Menciona primero la ficha CR más relevante para la pregunta del usuario (ej. "La reforma que podría aplicar es CR 2.1...") aunque el caso concreto del usuario quizás no sea reforma.
   b. Si la exclusión es ABSOLUTA (aplica sin condición a lo que describe el usuario, ej. "No se considera reforma la simple sustitución de bujías con las mismas especificaciones"), explícala a continuación y no continúes con documentación ni ARs.
   c. Si la exclusión es CONDICIONAL (solo aplica si no hay cambio de características, potencia, homologación, etc.), expón ambos escenarios:
      - Caso 1 (sin modificación de características): no se considera reforma → no hay trámite.
      - Caso 2 (con modificación de características): sí es reforma. Para este caso, revisa TODOS los documentos del contexto y cita EXPLÍCITAMENTE los CRs concretos que aplican a ese escenario (no uses expresiones vagas como "podría aplicar un CR" o "sería una reforma"). Por ejemplo, si el cambio implica aumento de potencia máxima, cita CR 2.9; si implica modificación del sistema de admisión, cita CR 2.1; si implica ambas cosas, cita ambas. Indica también la vía de tramitación y los requisitos mínimos de cada CR citado.
      Al final, formula una pregunta concreta al usuario para que confirme qué escenario describe su situación. La pregunta debe referenciar explícitamente los casos que has descrito (ej. "¿Sustituyes por bujías de las mismas especificaciones, o buscas unas que aumenten la potencia del motor?"), no dejarla abierta.
   Si hay duda sobre si la exclusión aplica al caso del usuario, pregúntale siempre antes de continuar.
2. Responde ÚNICAMENTE en base a los documentos de contexto proporcionados.
3. Si la información no está en el contexto, responde exactamente: "No tengo información suficiente en los documentos disponibles para responder esta pregunta."
4. Cita siempre la fuente: indica el CR (ej. "según CR 2.1") o el apartado (ej. "según el apartado 5.1 del preámbulo").
5. Sé conciso y directo. Usa listas cuando enumeres requisitos o pasos.
6. Si la reforma requiere proyecto técnico (Vía A), indícalo claramente al inicio de la respuesta.
7. No añadas información que no esté en el contexto, aunque la conozcas.
8. Si el usuario describe una reforma sin mencionar el CR, identifica cuál o cuáles son los CRs más probables basándote en el contexto recuperado y explica brevemente por qué.
9. Tienes memoria de los últimos mensajes de la conversación. Si el usuario hace referencia a algo mencionado antes (ej. "¿y si es un N1?", "¿qué pasa con esa reforma?"), usa el historial para entender a qué se refiere.
10. Antes de listar los ARs, SIEMPRE pregunta al usuario la categoría exacta de su vehículo si no la has confirmado aún en la conversación. Infiere primero el tipo de vehículo del contexto y presenta las opciones correspondientes:
    - Si el contexto sugiere un turismo, furgoneta, camión o remolque (Sección I — M, N, O):
      "¿Cuál es la categoría de tu vehículo?
       · M1 — Turismo o monovolumen (hasta 8 plazas)
       · M2/M3 — Minibús o autobús
       · N1 — Furgoneta o pick-up (hasta 3,5t)
       · N2/N3 — Camión (entre 3,5t y 12t / más de 12t)
       · O1–O4 — Remolque o semirremolque"
    - Si el contexto sugiere una moto, quad, ciclomotor o UTV (Sección II — L):
      "¿Cuál es la categoría de tu vehículo?
       · L1e — Ciclomotor de dos ruedas
       · L2e — Ciclomotor de tres ruedas
       · L3e — Motocicleta de dos ruedas
       · L4e — Motocicleta con sidecar
       · L5e — Triciclo a motor
       · L6e/L7e — Cuadriciclo ligero/pesado
       · Quad / UTV"
    - Si el contexto sugiere un tractor o maquinaria agrícola (Sección III) o de obras (Sección IV):
      "¿Cuál es la categoría de tu vehículo?
       · T1–T4 — Tractor agrícola (por potencia y anchura)
       · T5.1/T5.2 — Tractor forestal
       · MTC / MAA / MA2 / TCA — Maquinaria agrícola automotriz
       · RA / MAR — Remolques agrícolas"
    Si no puedes inferir el tipo de vehículo del contexto, pregunta primero: "¿Es un turismo/camión, una moto/quad, o un vehículo agrícola/de obras?" antes de mostrar las categorías.
    No listes los ARs hasta que el usuario confirme la categoría.
11. Lista TODOS los ARs del contexto donde el valor para la categoría confirmada sea (1), (2) o (3), sin excepción. Cuenta los ARs antes de responder para asegurarte de no omitir ninguno. Excluye solo los que tengan - o x.
12. Si el contexto contiene una sección "=== RELACIONES ESTRUCTURADAS (KAG) ===", úsala para responder preguntas sobre qué CRs implica una reforma, qué incorporaciones físicas exige o qué restricciones aplican a ese vehículo. Es información estructurada extraída del Manual, más fiable que el texto libre.
13. Si el contexto contiene una sección "=== NORMATIVA AR (CONTENIDO LEGISLATIVO) ===", DEBES usarla para responder cualquier pregunta sobre qué regulan, en qué consisten o para qué sirven los Actos Reglamentarios. Tanto si el usuario pregunta por uno solo como por varios, proporciona para CADA directiva presente en esa sección una descripción detallada con la misma estructura:
    - **Referencia y título** de la directiva
    - **Objetivo**: qué sistemas o aspectos del vehículo regula
    - **Requisitos principales**: prescripciones técnicas, límites, condiciones de instalación, pruebas exigidas, etc., extraídas directamente del articulado y los anexos del contexto
    Responde una directiva tras otra, sin comprimir en tabla. No apliques la regla 3 cuando esta sección esté presente: aunque el contenido disponible sea parcial, úsalo para describir lo que regula.
14. Cuando una normativa esté marcada como "⚠ NORMATIVA DEROGADA", indícalo siempre de forma explícita al inicio de la respuesta: "Esta directiva/reglamento ha sido derogado y ya no está en vigor. La información que sigue es histórica." Nunca cites normativa derogada sin advertir al usuario.

FORMATO DE RESPUESTA:
- CR(s) más relevante(s) para la pregunta (siempre al inicio, incluso si el caso concreto quizás no sea reforma)
- Respuesta directa a la pregunta (puede incluir escenarios condicionales según la regla 1c)
- Documentación exigible y requisitos (solo si el caso es definitivamente una reforma)
- Documentación exigible (si aplica)
- Categoría utilizada para filtrar ARs: [indicar explícitamente, ej. "M1"]
- Lista de Actos Reglamentarios aplicables a [categoría] según CR [X], en formato tabla markdown:
  | Sistema | Referencia | Nivel de exigencia |
  |---------|------------|-------------------|
  | ...     | ...        | ...               |
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

    if docs.get("directivas"):
        partes.append("=== NORMATIVA AR (CONTENIDO LEGISLATIVO) ===")
        for doc in docs["directivas"]:
            md = doc.metadata
            ref    = md.get("referencia", "?")
            titulo = md.get("titulo", "")
            aviso  = " ⚠ NORMATIVA DEROGADA" if md.get("derogada") else ""
            partes.append(f"[{ref}{aviso}]\n{titulo}\n{doc.page_content}")

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


# ─── KAG: enriquecimiento estructurado para preguntas sobre CRs concretos ─────

_PATRON_CR = re.compile(r"(?:CR\s*)?(\d+\.\d+)", re.IGNORECASE)


def _detectar_crs(pregunta: str, historial: list[dict] | None) -> list[str]:
    """Extrae códigos CR mencionados en la pregunta y en los últimos mensajes del usuario."""
    textos = [pregunta]
    if historial:
        textos.extend(m["content"] for m in historial[-4:] if m["role"] == "user")
    candidatos = set()
    for texto in textos:
        for m in _PATRON_CR.finditer(texto):
            candidatos.add(m.group(1))
    return sorted(candidatos)


_SECCIONES_GRAFO = ("I", "II", "III", "IV")

def _contexto_kag_chatbot(crs: list[str], categoria: str | None) -> str:
    """
    Lee el grafo directamente para los CRs detectados y devuelve contexto estructurado.
    Busca en todas las secciones (I, II, III, IV) — una CR puede existir en varias.
    No llama al LLM — apropiado para el chatbot donde no hay datos de vehículo completos.
    """
    try:
        from .graph_retriever import _cargar_grafo
        grafo = _cargar_grafo()
    except (ImportError, FileNotFoundError):
        return ""

    def _strip_prefijo(clave: str) -> str:
        partes = clave.split("-", 2)
        return partes[2] if len(partes) == 3 else clave.replace("CR-", "")

    partes: list[str] = []

    for cr in crs:
        # Buscar este CR en todas las secciones del grafo
        nodos_encontrados = []
        for sec in _SECCIONES_GRAFO:
            key = f"CR-{sec}-{cr}"
            if key in grafo["nodos"]:
                nodos_encontrados.append((sec, key, grafo["nodos"][key]))

        for sec, key, nodo in nodos_encontrados:
            label = f"CR-{cr} (Sección {sec}: {nodo.get('descripcion', '')})"
            bloque: list[str] = [f"[KAG — {label}]"]

            # Categoría bloqueada
            if categoria and categoria in nodo.get("categorias_bloqueadas", []):
                bloque.append(f"  REFORMA IMPOSIBLE para categoría {categoria} (marcada con X en el Manual)")

            # ARs filtrados por categoría
            if categoria:
                ars = nodo.get("ars_por_categoria", {}).get(categoria, [])
                if ars:
                    bloque.append(f"  ARs aplicables a {categoria}:")
                    for ar in ars:
                        bloque.append(f"    · {ar['sistema']} {ar['referencia']}: nivel {ar['nivel']}")

            # Relaciones salientes (usando clave con sección)
            edges = [e for e in grafo["edges"] if e["cr_origen"] == key]

            implica = [e for e in edges if e["tipo"] == "implica_cr" and e.get("cr_destino")]
            if implica:
                bloque.append("  Implica también tramitar:")
                for e in implica:
                    dest = _strip_prefijo(e["cr_destino"])
                    cond = f" (condición: {e['condicion']})" if e.get("condicion") else ""
                    bloque.append(f"    · CR {dest}{cond}")

            incorporar = [e for e in edges if e["tipo"] == "obliga_incorporar"]
            if incorporar:
                bloque.append("  Incorporaciones físicas requeridas (sin tramitar CR adicional):")
                for e in incorporar:
                    cond = f" (si: {e['condicion']})" if e.get("condicion") else ""
                    bloque.append(f"    · {e.get('fuente_literal', '')[:180]}{cond}")

            restricciones = [e for e in edges if e["tipo"] == "restriccion"]
            if restricciones:
                bloque.append("  Restricciones/condiciones:")
                for e in restricciones:
                    cond = f" — aplica si: {e['condicion']}" if e.get("condicion") else ""
                    bloque.append(f"    · {e.get('fuente_literal', '')[:180]}{cond}")

            if len(bloque) > 1:
                partes.append("\n".join(bloque))

    if not partes:
        return ""

    return "=== RELACIONES ESTRUCTURADAS (KAG) ===\n" + "\n\n".join(partes)


# ─── LLM ──────────────────────────────────────────────────────────────────────

def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=config.OPENAI_API_KEY,
        model=config.GENERATION_MODEL,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS_RESPUESTA,
    )


# ─── Descripciones por directiva ──────────────────────────────────────────────

_PROMPT_DIRECTIVA = (
    "Eres un experto técnico en normativa de homologación de vehículos de la UE.\n"
    "Basándote ÚNICAMENTE en el texto de la directiva que aparece a continuación, describe:\n"
    "- **Objetivo**: qué sistemas o aspectos del vehículo regula\n"
    "- **Requisitos principales**: prescripciones técnicas concretas (medidas, condiciones de "
    "instalación, pruebas, límites numéricos) tal como aparecen en el texto\n"
    "Si la directiva está marcada como DEROGADA, indícalo al inicio.\n"
    "No inventes nada que no esté en el texto proporcionado.\n\n"
    "TEXTO:\n{contexto}"
)


def _describir_directiva(ref: str, llm: ChatOpenAI) -> str:
    """
    Recupera los chunks más ricos de una directiva y genera una descripción detallada
    con una llamada independiente al LLM — misma calidad que preguntar individualmente.
    """
    try:
        from langchain_chroma import Chroma
        from langchain_openai import OpenAIEmbeddings

        col = Chroma(
            collection_name=config.COLECCION_DIRECTIVAS,
            embedding_function=OpenAIEmbeddings(
                api_key=config.OPENAI_API_KEY,
                model=config.EMBEDDING_MODEL,
            ),
            persist_directory=str(config.CHROMA_DIR),
        )

        query_tecnica = f"prescripciones técnicas requisitos instalación {ref}"

        # Primero: chunks con articulado (chunk_num > 0)
        docs = col.similarity_search(
            query_tecnica, k=4,
            filter={"$and": [{"referencia": ref}, {"chunk_num": {"$gt": 0}}]},
        )
        # Fallback: cualquier chunk de esa referencia
        if not docs:
            docs = col.similarity_search(query_tecnica, k=4, filter={"referencia": ref})
        if not docs:
            return f"### {ref}\nNo se encontró información en la base de datos."

        titulo   = docs[0].metadata.get("titulo", ref)
        derogada = docs[0].metadata.get("derogada", False)
        aviso    = " ⚠ NORMATIVA DEROGADA" if derogada else ""
        contexto = f"[{ref}{aviso}]\n{titulo}\n\n" + "\n\n".join(d.page_content for d in docs)

        respuesta = llm.invoke([HumanMessage(content=_PROMPT_DIRECTIVA.format(contexto=contexto))])
        return f"### {ref}{aviso} — {titulo[:120]}\n\n{respuesta.content}"

    except Exception as e:
        return f"### {ref}\nError al recuperar la directiva: {e}"


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
    # Atajo: si la pregunta es sobre las directivas AR del historial, describir cada una
    # con una llamada independiente al LLM (misma calidad que preguntar individualmente).
    from .retriever import _pregunta_sobre_ars_del_historial, _refs_ar_en_historial
    if _pregunta_sobre_ars_del_historial(pregunta, historial):
        refs = _refs_ar_en_historial(historial)
        if refs:
            llm = _get_llm()
            from concurrent.futures import ThreadPoolExecutor, as_completed
            resultados: dict[str, str] = {}
            with ThreadPoolExecutor(max_workers=6) as pool:
                futuros = {pool.submit(_describir_directiva, ref, llm): ref for ref in refs}
                for fut in as_completed(futuros):
                    resultados[futuros[fut]] = fut.result()
            # Mantener el orden original de las refs
            partes = [resultados[ref] for ref in refs]
            return {
                "respuesta": "\n\n---\n\n".join(partes),
                "fuentes":   [{"tipo": "directiva_ar", "cr": None, "via": None,
                                "apartado": None, "titulo": ref, "paginas": None}
                              for ref in refs],
                "n_docs":    len(refs),
            }

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

    # 2b. Enriquecer con KAG si la pregunta menciona CRs concretos
    crs_detectados = _detectar_crs(pregunta, historial)
    if crs_detectados:
        kag = _contexto_kag_chatbot(crs_detectados, categoria_efectiva)
        if kag:
            contexto = contexto + "\n\n" + kag

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

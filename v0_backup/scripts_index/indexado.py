"""
Indexado en Chroma de los documentos de reformas de vehículos.

Documentos indexados:
    - fichas_cr_seccion1_v3.json          → colección 'fichas_cr' (Sección I)
    - fichas_cr_secciones_ii_iii_iv.json  → colección 'fichas_cr' (Secciones II, III, IV)
    - preambulo_seccion1.json             → colección 'preambulo'
    - reglamento_ue_2018_858.json         → colección 'reglamento_ue'
    - directivas_ar.json                  → colección 'directivas_ar' (103 normativas EU)

Uso:
    python indexado.py                    # indexa todo desde cero
    python indexado.py --reset            # borra colecciones y reindexea
    python indexado.py --solo fichas      # solo una colección
    python indexado.py --solo directivas  # solo directivas AR
    python indexado.py --test             # verifica con queries de prueba tras indexar
"""

import json
import re
import argparse
from pathlib import Path

import os
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from dotenv import load_dotenv

# ─── Config ───────────────────────────────────────────────────────────────────

load_dotenv()

DIR         = Path(__file__).parent.parent  # raíz del proyecto
SCRIPTS_DIR = Path(__file__).parent        # scripts_index/

FICHAS_PATH       = DIR / "json/fichas_cr_seccion1_v3.json"
FICHAS_EXTRA_PATH = DIR / "json/fichas_cr_secciones_ii_iii_iv.json"
PREAMBULO_PATH    = DIR / "json/preambulo_seccion1.json"
REGLAMENTO_PATH   = DIR / "json/reglamento_ue_2018_858.json"
DIRECTIVAS_PATH   = DIR / "json/directivas_ar.json"
CHROMA_DIR        = SCRIPTS_DIR / "chroma_db"

COLECCION_FICHAS      = "fichas_cr"
COLECCION_PREAMBULO   = "preambulo"
COLECCION_REGLAMENTO  = "reglamento_ue"
COLECCION_DIRECTIVAS  = "directivas_ar"

# Tamaño máximo de chunk en caracteres antes de partir el documento
CHUNK_MAX_CHARS  = 2000
CHUNK_OVERLAP    = 150

# Patrón para detectar inicio de artículo en el texto legal
_PAT_ARTICULO = re.compile(
    r'\n((?:Art[íi]culo|ARTÍCULO|Article|ARTICLE)\s+\d+\b)',
    re.IGNORECASE,
)

BATCH_SIZE = 50

# ─── Embedding function ───────────────────────────────────────────────────────

def get_ef():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Variable OPENAI_API_KEY no encontrada.\n"
            "Crea un fichero .env en este directorio con:\n"
            "  OPENAI_API_KEY=sk-..."
        )
    return OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name="text-embedding-3-small",
    )

EF = get_ef()

# ─── Construcción del texto para embedding ────────────────────────────────────

def texto_ficha(ficha, texto_ars):
    """
    Construye el texto enriquecido que se embeddea para cada ficha CR.
    Incluye: descripción + categorías + documentación + vía + keywords + interpretación ARs.
    """
    partes = []

    # Identificación
    partes.append(f"CR {ficha['cr']}: {ficha['descripcion_cr']}")
    partes.append(f"Grupo {ficha['grupo_numero']}: {ficha['descripcion_grupo']}")

    # Categorías aplicables
    cats = ", ".join(ficha["categorias_aplicables"]) or "ninguna"
    partes.append(f"Categorías de vehículos aplicables: {cats}")

    # Vía de tramitación
    partes.append(f"Vía de tramitación: {ficha['via_tramitacion']} — {ficha['via_tramitacion_desc']}")

    # Documentación
    doc = ficha.get("documentacion_necesaria", {})
    if doc:
        doc_str = ", ".join(f"{k}: {v}" for k, v in doc.items())
        partes.append(f"Documentación exigible: {doc_str}")

    # Inspección específica
    if ficha.get("inspeccion_especifica"):
        partes.append(f"Inspección ITV: {ficha['inspeccion_especifica']}")

    # Información adicional
    if ficha.get("informacion_adicional"):
        partes.append(f"Información adicional: {ficha['informacion_adicional']}")

    # Keywords del cliente (enriquecimiento)
    if ficha.get("keywords_reformas"):
        kws = ", ".join(ficha["keywords_reformas"])
        partes.append(f"Términos relacionados: {kws}")
    
    # Actos Reglamentarios de la ficha
    ars = ficha.get("actos_reglamentarios", [])
    if ars:
        partes.append("Actos Reglamentarios aplicables:")
        for ar in ars:
            sistema    = ar.get("sistema", "")
            referencia = ar.get("referencia", "")
            aplic      = ar.get("aplicabilidad", {})
            # Construir línea con aplicabilidad por categoría
            aplic_str  = ", ".join(f"{cat}: {val}" for cat, val in aplic.items() if val != "x")
            partes.append(f"  - {sistema} ({referencia}): {aplic_str}")
            
    # Inyección de la interpretación de ARs (siempre)
    partes.append("---")
    partes.append(texto_ars)

    return "\n".join(partes)


def metadatos_ficha(ficha):
    """
    Metadatos de una ficha CR para filtrado en Chroma.
    Solo tipos primitivos: str, int, float, bool.
    """
    seccion = ficha.get("seccion", "I")
    return {
        "tipo":               "ficha_cr",
        "cr":                 ficha["cr"],
        "seccion":            seccion,
        "grupo_numero":       ficha["grupo_numero"],
        "categorias":         ",".join(ficha["categorias_aplicables"]),
        "via_tramitacion":    ficha["via_tramitacion"],
        "requiere_proyecto":  ficha["via_tramitacion"] == "A",
        "pagina_inicio":      ficha["paginas"][0],
        "fuente":             f"Manual de Reformas — Sección {seccion}",
        "revision_manual":    ficha.get("revision") or "",
    }


# ─── Indexado de fichas CR ────────────────────────────────────────────────────

def indexar_fichas(client, reset=False):
    print("\n── Fichas CR ──────────────────────────────────────────")

    # Texto de interpretación de ARs para inyectar en cada ficha
    with open(PREAMBULO_PATH, encoding="utf-8") as f:
        preamb = json.load(f)
    texto_ars = preamb["interpretacion_ars_texto"]

    # Cargar fichas de Sección I
    with open(FICHAS_PATH, encoding="utf-8") as f:
        data_i = json.load(f)
    fichas = data_i["fichas"]

    # Cargar fichas de Secciones II, III, IV (si el fichero existe)
    if FICHAS_EXTRA_PATH.exists():
        with open(FICHAS_EXTRA_PATH, encoding="utf-8") as f:
            data_extra = json.load(f)
        fichas = fichas + data_extra["fichas"]
        print(f"  Sección I: {len(data_i['fichas'])} fichas | "
              f"Secciones II-IV: {len(data_extra['fichas'])} fichas")
    else:
        print(f"  Sección I: {len(fichas)} fichas (secciones II-IV no disponibles)")

    if reset:
        try:
            client.delete_collection(COLECCION_FICHAS)
            print(f"  Colección '{COLECCION_FICHAS}' eliminada")
        except Exception:
            pass

    col = client.get_or_create_collection(
        name=COLECCION_FICHAS,
        embedding_function=EF,
        metadata={"hnsw:space": "cosine"},
    )

    total    = len(fichas)
    añadidos = 0

    for i in range(0, total, BATCH_SIZE):
        lote = fichas[i:i + BATCH_SIZE]

        # IDs únicos por sección para evitar colisiones (CR 1.1 existe en las 4 secciones)
        ids = [
            f"cr_{f.get('seccion','I')}_{f['cr'].replace('.', '_')}"
            for f in lote
        ]
        textos    = [texto_ficha(f, texto_ars) for f in lote]
        metadatas = [metadatos_ficha(f) for f in lote]

        col.upsert(ids=ids, documents=textos, metadatas=metadatas)
        añadidos += len(lote)
        print(f"  Upsert lote {i // BATCH_SIZE + 1}: {añadidos}/{total} fichas")

    print(f"  Total en colección: {col.count()}")


# ─── Indexado del preámbulo ───────────────────────────────────────────────────

def indexar_preambulo(client, reset=False):
    print("\n── Preámbulo ──────────────────────────────────────────")

    with open(PREAMBULO_PATH, encoding="utf-8") as f:
        data = json.load(f)

    if reset:
        try:
            client.delete_collection(COLECCION_PREAMBULO)
            print(f"  Colección '{COLECCION_PREAMBULO}' eliminada")
        except Exception:
            pass

    col = client.get_or_create_collection(
        name=COLECCION_PREAMBULO,
        embedding_function=EF,
        metadata={"hnsw:space": "cosine"},
    )

    chunks = data["chunks"]
    ids       = [f"preamb_{c['apartado']}" for c in chunks]
    textos    = [c["texto"] for c in chunks]
    metadatas = []

    for c in chunks:
        md = {k: v for k, v in c["metadata"].items()
              if isinstance(v, (str, int, float, bool))}
        # keywords_activacion como string para Chroma
        if "keywords_activacion" in c["metadata"]:
            md["keywords_activacion"] = ",".join(c["metadata"]["keywords_activacion"])
        metadatas.append(md)

    col.upsert(ids=ids, documents=textos, metadatas=metadatas)
    print(f"  {len(chunks)} chunks indexados")
    print(f"  Total en colección: {col.count()}")


# ─── Indexado del reglamento UE ──────────────────────────────────────────────

def indexar_reglamento(client, reset=False):
    print("\n── Reglamento (UE) 2018/858 ───────────────────────────")

    with open(REGLAMENTO_PATH, encoding="utf-8") as f:
        data = json.load(f)

    if reset:
        try:
            client.delete_collection(COLECCION_REGLAMENTO)
            print(f"  Colección '{COLECCION_REGLAMENTO}' eliminada")
        except Exception:
            pass

    col = client.get_or_create_collection(
        name=COLECCION_REGLAMENTO,
        embedding_function=EF,
        metadata={"hnsw:space": "cosine"},
    )

    chunks = data["chunks"]
    ids       = [f"reg_{c['apartado']}" for c in chunks]
    textos    = [c["texto"] for c in chunks]
    metadatas = []

    for c in chunks:
        md = {k: v for k, v in c["metadata"].items()
              if isinstance(v, (str, int, float, bool))}
        if "keywords_activacion" in c["metadata"]:
            md["keywords_activacion"] = ",".join(c["metadata"]["keywords_activacion"])
        # paginas como string
        if "paginas" in c["metadata"] and isinstance(c["metadata"]["paginas"], list):
            md["pagina_inicio"] = c["metadata"]["paginas"][0]
        metadatas.append(md)

    col.upsert(ids=ids, documents=textos, metadatas=metadatas)
    print(f"  {len(chunks)} chunks indexados")
    print(f"  Total en colección: {col.count()}")


# ─── Test de queries ──────────────────────────────────────────────────────────

def test_queries(client):
    print("\n── Test de queries ────────────────────────────────────")

    queries = [
        ("fichas_cr",      "¿Qué documentación necesito para poner un turbo?",          {"via_tramitacion": "B"}),
        ("fichas_cr",      "reforma que necesita proyecto técnico en un M1",             None),
        ("preambulo",      "¿Qué es un informe de conformidad?",                         None),
        ("reglamento_ue",  "¿Qué es una categoría N1?",                                  None),
    ]

    for coleccion, query, filtro in queries:
        col = client.get_collection(coleccion, embedding_function=EF)
        kwargs = {"query_texts": [query], "n_results": 2}
        if filtro:
            kwargs["where"] = filtro
        resultados = col.query(**kwargs)

        print(f"\n  Query: '{query}'")
        if filtro:
            print(f"  Filtro: {filtro}")
        for j, (doc, meta) in enumerate(zip(
            resultados["documents"][0],
            resultados["metadatas"][0]
        )):
            id_resultado = resultados["ids"][0][j]
            distancia    = resultados["distances"][0][j]
            print(f"  [{j+1}] {id_resultado} (dist={distancia:.3f})")
            print(f"       {doc[:120].replace(chr(10), ' ')}...")


# ─── Indexado de directivas AR ───────────────────────────────────────────────

def _split_por_tamano(texto: str, titulo: str) -> list[str]:
    """Parte un texto por tamaño fijo con solapamiento. Usado como fallback."""
    chunks = []
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + CHUNK_MAX_CHARS, len(texto))
        chunks.append(f"{titulo}\n\n{texto[inicio:fin]}")
        if fin == len(texto):
            break
        inicio = fin - CHUNK_OVERLAP
    return chunks


def _chunkar_texto(texto: str, titulo: str) -> list[str]:
    """
    Parte el texto de una directiva en chunks para ChromaDB.

    Estrategia:
    1. Si el texto es corto (<= CHUNK_MAX_CHARS): un solo chunk.
    2. Si contiene artículos: partir por artículo, agrupando los pequeños.
    3. Si no tiene artículos: tamaño fijo con solapamiento.

    Paso final: cualquier chunk que siga superando CHUNK_MAX_CHARS se subdivide
    por tamaño (un artículo largo puede superar el límite de tokens del embedding).
    """
    if len(texto) <= CHUNK_MAX_CHARS:
        return [f"{titulo}\n\n{texto}"]

    candidatos: list[str] = []

    # Intentar split por artículos
    partes = _PAT_ARTICULO.split(texto)
    # split() con grupo capturador: [preámbulo, 'Artículo 1', cuerpo1, 'Artículo 2', ...]
    if len(partes) > 3:
        buffer = partes[0].strip()

        i = 1
        while i < len(partes) - 1:
            header  = partes[i].strip()
            content = partes[i + 1].strip()
            bloque  = f"{header}\n{content}"

            if len(buffer) + len(bloque) <= CHUNK_MAX_CHARS:
                buffer = f"{buffer}\n\n{bloque}" if buffer else bloque
            else:
                if buffer:
                    candidatos.append(buffer)
                buffer = bloque
            i += 2

        if buffer:
            candidatos.append(buffer)
    else:
        # Sin artículos: dividir directamente por tamaño
        return _split_por_tamano(texto, titulo)

    # Segundo paso: subdividir cualquier candidato que siga siendo demasiado largo
    chunks: list[str] = []
    for c in candidatos:
        if len(c) <= CHUNK_MAX_CHARS:
            chunks.append(f"{titulo}\n\n{c}")
        else:
            chunks.extend(_split_por_tamano(c, titulo))

    return chunks if chunks else [f"{titulo}\n\n{texto}"]


def indexar_directivas(client, reset=False):
    print("\n── Directivas AR ──────────────────────────────────────")

    if not DIRECTIVAS_PATH.exists():
        print(f"  ⚠ {DIRECTIVAS_PATH} no encontrado — omitiendo.")
        print("  Ejecuta: python scripts_parser/parser_directivas_ar.py")
        return

    with open(DIRECTIVAS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    if reset:
        try:
            client.delete_collection(COLECCION_DIRECTIVAS)
            print(f"  Colección '{COLECCION_DIRECTIVAS}' eliminada")
        except Exception:
            pass

    col = client.get_or_create_collection(
        name=COLECCION_DIRECTIVAS,
        embedding_function=EF,
        metadata={"hnsw:space": "cosine"},
    )

    directivas = data["directivas"]
    total_chunks = 0

    ids_lote: list[str]  = []
    textos_lote: list[str] = []
    metas_lote: list[dict] = []

    def _flush():
        nonlocal total_chunks
        if ids_lote:
            col.upsert(ids=ids_lote, documents=textos_lote, metadatas=metas_lote)
            total_chunks += len(ids_lote)
            ids_lote.clear(); textos_lote.clear(); metas_lote.clear()

    for doc in directivas:
        celex    = doc["celex"]
        titulo   = doc.get("titulo") or doc["referencia"]
        texto    = doc.get("texto", "")
        derogada = doc.get("derogada", False)

        chunks = _chunkar_texto(texto, titulo)
        n_chunks = len(chunks)

        metadato_base = {
            "tipo":            "directiva_ar",
            "referencia":      doc["referencia"],
            "celex":           celex,
            "titulo":          titulo[:200],
            "derogada":        derogada,
            "secciones":       ",".join(doc.get("secciones", [])),
            "fuentes":         ",".join(doc.get("fuentes", [])),
            "total_chunks":    n_chunks,
            "sustituida_por":  doc.get("sustituida_por") or "",
        }

        for i, chunk in enumerate(chunks):
            ids_lote.append(f"directiva_{celex}_{i:04d}")
            textos_lote.append(chunk)
            metas_lote.append({**metadato_base, "chunk_num": i})

            if len(ids_lote) >= BATCH_SIZE:
                _flush()

        aviso = " ⚠DEROGADA" if derogada else ""
        print(f"  {doc['referencia']:30s} {celex} | {n_chunks} chunk(s){aviso}")

    _flush()

    print(f"\n  Directivas indexadas : {len(directivas)}")
    print(f"  Total chunks         : {total_chunks}")
    print(f"  Total en colección   : {col.count()}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Indexa documentos de reformas en Chroma")
    parser.add_argument("--reset", action="store_true",
                        help="Borra y recrea las colecciones")
    parser.add_argument("--solo", choices=["fichas", "preambulo", "reglamento", "directivas"],
                        help="Indexa solo una colección")
    parser.add_argument("--test", action="store_true",
                        help="Lanza queries de prueba tras indexar")
    parser.add_argument("--db",   default=str(CHROMA_DIR),
                        help="Directorio de la base de datos Chroma")
    args = parser.parse_args()

    print(f"Chroma DB: {args.db}")
    client = chromadb.PersistentClient(path=args.db)

    if args.solo == "fichas" or args.solo is None:
        indexar_fichas(client, reset=args.reset)

    if args.solo == "preambulo" or args.solo is None:
        indexar_preambulo(client, reset=args.reset)

    if args.solo == "reglamento" or args.solo is None:
        indexar_reglamento(client, reset=args.reset)

    if args.solo == "directivas" or args.solo is None:
        indexar_directivas(client, reset=args.reset)

    if args.test:
        test_queries(client)

    print("\nIndexado completado.")


if __name__ == "__main__":
    main()

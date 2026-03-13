"""
Indexado en Chroma de los tres documentos de la POC de reformas de vehículos.

Documentos indexados:
    - fichas_cr_seccion1.json     → colección 'fichas_cr'
    - preambulo_seccion1.json     → colección 'preambulo'
    - reglamento_ue_2018_858.json → colección 'reglamento_ue'

Requisitos:
    pip install chromadb openai python-dotenv

    Crear fichero .env en el mismo directorio:
        OPENAI_API_KEY=sk-...

Uso:
    python indexado.py                  # indexa todo desde cero
    python indexado.py --reset          # borra colecciones y reindexea
    python indexado.py --solo fichas    # solo una colección (fichas|preambulo|reglamento)
    python indexado.py --test           # verifica con queries de prueba tras indexar

Embeddings:
    Modelo: text-embedding-3-small (OpenAI)
    Dimensiones: 1536
    Coste estimado indexado inicial (~93 docs): < 0.01 USD
"""

import json
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

FICHAS_PATH     = DIR / "json/fichas_cr_seccion1_v3.json"
PREAMBULO_PATH  = DIR / "json/preambulo_seccion1.json"
REGLAMENTO_PATH = DIR / "json/reglamento_ue_2018_858.json"
CHROMA_DIR      = SCRIPTS_DIR / "chroma_db"

COLECCION_FICHAS     = "fichas_cr"
COLECCION_PREAMBULO  = "preambulo"
COLECCION_REGLAMENTO = "reglamento_ue"

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
    return {
        "tipo":               "ficha_cr",
        "cr":                 ficha["cr"],
        "grupo_numero":       ficha["grupo_numero"],
        "categorias":         ",".join(ficha["categorias_aplicables"]),  # str para Chroma
        "via_tramitacion":    ficha["via_tramitacion"],
        "requiere_proyecto":  ficha["via_tramitacion"] == "A",
        "pagina_inicio":      ficha["paginas"][0],
        "fuente":             "Manual de Reformas — Sección I",
        "revision_manual":    ficha["revision"],
    }


# ─── Indexado de fichas CR ────────────────────────────────────────────────────

def indexar_fichas(client, reset=False):
    print("\n── Fichas CR ──────────────────────────────────────────")

    with open(FICHAS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    # Texto de interpretación de ARs para inyectar en cada ficha
    with open(PREAMBULO_PATH, encoding="utf-8") as f:
        preamb = json.load(f)
    texto_ars = preamb["interpretacion_ars_texto"]

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

    fichas = data["fichas"]
    total  = len(fichas)
    añadidos = 0

    for i in range(0, total, BATCH_SIZE):
        lote = fichas[i:i + BATCH_SIZE]

        ids       = [f"cr_{f['cr'].replace('.', '_')}" for f in lote]
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


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Indexa documentos de reformas en Chroma")
    parser.add_argument("--reset", action="store_true",
                        help="Borra y recrea las colecciones")
    parser.add_argument("--solo", choices=["fichas", "preambulo", "reglamento"],
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

    if args.test:
        test_queries(client)

    print("\nIndexado completado.")


if __name__ == "__main__":
    main()

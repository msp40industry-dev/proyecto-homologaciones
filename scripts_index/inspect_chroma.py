"""
Inspección de la base de datos Chroma.

Uso:
    python inspect_chroma.py                        # resumen de todas las colecciones
    python inspect_chroma.py --col fichas_cr        # detalle de una colección
    python inspect_chroma.py --col fichas_cr --id cr_2_1   # documento concreto
    python inspect_chroma.py --col fichas_cr --n 5  # primeros N documentos
"""

import json
import argparse
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
import os
from dotenv import load_dotenv

load_dotenv()

CHROMA_DIR = Path(__file__).parent / "chroma_db"

COLECCIONES = ["fichas_cr", "preambulo", "reglamento_ue"]


def get_client():
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_ef():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY no encontrada en .env")
    return OpenAIEmbeddingFunction(api_key=api_key, model_name="text-embedding-3-small")


# ─── Resumen general ──────────────────────────────────────────────────────────

def resumen(client):
    print("\n══ Colecciones en Chroma ══════════════════════════════")
    cols = client.list_collections()
    if not cols:
        print("  (vacío — ejecuta indexado.py primero)")
        return

    for col_info in cols:
        col = client.get_collection(col_info.name)
        n   = col.count()
        print(f"\n  {col_info.name}  ({n} documentos)")

        # Muestra los IDs indexados
        resultados = col.get(limit=n)
        ids       = resultados["ids"]
        metadatas = resultados["metadatas"]

        for id_, md in zip(ids, metadatas):
            # Línea de resumen según tipo
            tipo = md.get("tipo", "?")
            if tipo == "ficha_cr":
                extra = f"CR {md.get('cr')} | vía {md.get('via_tramitacion')} | cats: {md.get('categorias')}"
            elif tipo == "preambulo":
                extra = md.get("titulo", "")[:70]
            elif tipo == "reglamento_ue":
                extra = md.get("titulo", "")[:70]
            else:
                extra = str(md)[:70]
            print(f"    {id_:40s}  {extra}")


# ─── Detalle de colección ─────────────────────────────────────────────────────

def detalle_coleccion(client, nombre_col, n=10):
    print(f"\n══ Colección: {nombre_col} ══════════════════════════════")
    try:
        col = client.get_collection(nombre_col)
    except Exception:
        print(f"  Colección '{nombre_col}' no encontrada.")
        return

    total = col.count()
    print(f"  Total documentos: {total}")
    print(f"  Mostrando primeros {min(n, total)}:\n")

    resultados = col.get(limit=n)
    for id_, md, doc in zip(
        resultados["ids"],
        resultados["metadatas"],
        resultados["documents"],
    ):
        print(f"  ID: {id_}")
        print(f"  Metadatos: {json.dumps(md, ensure_ascii=False)}")
        print(f"  Texto ({len(doc)} chars): {doc[:200].replace(chr(10), ' ')}...")
        print()


# ─── Documento concreto por ID ────────────────────────────────────────────────

def ver_documento(client, nombre_col, doc_id):
    print(f"\n══ Documento: {doc_id} (colección: {nombre_col}) ══════")
    try:
        col = client.get_collection(nombre_col)
    except Exception:
        print(f"  Colección '{nombre_col}' no encontrada.")
        return

    resultado = col.get(ids=[doc_id])
    if not resultado["ids"]:
        print(f"  ID '{doc_id}' no encontrado.")
        return

    md  = resultado["metadatas"][0]
    doc = resultado["documents"][0]

    print(f"\n  Metadatos:")
    for k, v in md.items():
        print(f"    {k:30s} {v}")
    print(f"\n  Texto completo ({len(doc)} chars):")
    print(f"  {'-'*60}")
    print(doc)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Inspecciona la base de datos Chroma")
    parser.add_argument("--col", help="Nombre de colección a inspeccionar")
    parser.add_argument("--id",  help="ID de documento concreto (requiere --col)")
    parser.add_argument("--n",   type=int, default=10,
                        help="Número de documentos a mostrar (default: 10)")
    args = parser.parse_args()

    client = get_client()

    if args.id and args.col:
        ver_documento(client, args.col, args.id)
    elif args.col:
        detalle_coleccion(client, args.col, n=args.n)
    else:
        resumen(client)


if __name__ == "__main__":
    main()

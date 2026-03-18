"""
Enriquecimiento de fichas CR con keywords del cliente.

Lee keywords_reformas.csv y las inyecta en el campo keywords_reformas
de cada ficha en fichas_cr_seccion1.json.

Uso:
    python enriquecimiento.py
    python enriquecimiento.py --csv ruta/otro.csv --fichas ruta/fichas.json
"""

import csv
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Paths por defecto ─────────────────────────────────────────────────────────

DIR = Path(__file__).parent
CSV_PATH    = DIR / "keywords_reformas.csv"
FICHAS_PATH = DIR.parent / "json" / "fichas_cr_seccion1_v3.json"
OUTPUT_PATH = FICHAS_PATH  # sobreescribe in-place

# ── Carga y validación del CSV ────────────────────────────────────────────────

def cargar_csv(csv_path):
    """
    Lee el CSV y devuelve un dict {cr: [keyword, ...]} con valores únicos
    y normalizados (strip + lowercase para deduplicar).
    """
    keywords_por_cr = defaultdict(list)
    errores = []
    seen = defaultdict(set)  # para deduplicar por CR

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validar cabeceras mínimas
        campos = reader.fieldnames or []
        for campo in ("cr", "keyword"):
            if campo not in campos:
                raise ValueError(f"El CSV no tiene la columna obligatoria: '{campo}'")

        for i, row in enumerate(reader, start=2):  # fila 1 = cabecera
            cr      = row.get("cr", "").strip()
            keyword = row.get("keyword", "").strip()

            if not cr:
                errores.append(f"Fila {i}: campo 'cr' vacío — ignorada")
                continue
            if not keyword:
                errores.append(f"Fila {i}: CR {cr} — keyword vacía — ignorada")
                continue

            # Deduplicar (case-insensitive)
            key = keyword.lower()
            if key not in seen[cr]:
                seen[cr].add(key)
                keywords_por_cr[cr].append(keyword)

    return dict(keywords_por_cr), errores


# ── Merge con fichas ──────────────────────────────────────────────────────────

def enriquecer(fichas_path, keywords_por_cr, csv_path=CSV_PATH):
    with open(fichas_path, encoding="utf-8") as f:
        data = json.load(f)

    crs_en_json    = {f["cr"] for f in data["fichas"]}
    crs_en_csv     = set(keywords_por_cr.keys())
    crs_no_existen = crs_en_csv - crs_en_json

    stats = {
        "fichas_actualizadas": 0,
        "keywords_añadidas":   0,
        "crs_no_encontrados":  list(crs_no_existen),
    }

    if crs_no_existen:
        print(f"  ⚠  CRs en el CSV que no existen en el JSON: {sorted(crs_no_existen)}")

    for ficha in data["fichas"]:
        cr = ficha["cr"]
        if cr not in keywords_por_cr:
            continue

        nuevas = keywords_por_cr[cr]

        # Merge sin duplicar las que ya pudiera haber
        existentes_lower = {k.lower() for k in ficha.get("keywords_reformas", [])}
        a_añadir = [k for k in nuevas if k.lower() not in existentes_lower]

        ficha["keywords_reformas"] = ficha.get("keywords_reformas", []) + a_añadir

        stats["fichas_actualizadas"] += 1
        stats["keywords_añadidas"]   += len(a_añadir)

    # Registrar fecha de último enriquecimiento en metadata
    data["metadata"]["ultimo_enriquecimiento"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    data["metadata"]["keywords_csv"]           = str(Path(csv_path).name)

    return data, stats


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Enriquece fichas CR con keywords del cliente")
    parser.add_argument("--csv",    default=str(CSV_PATH),    help="Ruta al CSV de keywords")
    parser.add_argument("--fichas", default=str(FICHAS_PATH), help="Ruta al JSON de fichas CR")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Ruta del JSON de salida")
    args = parser.parse_args()

    print(f"Leyendo CSV:    {args.csv}")
    print(f"Leyendo fichas: {args.fichas}")

    # 1. Cargar CSV
    keywords_por_cr, errores_csv = cargar_csv(args.csv)
    print(f"\nCSV cargado: {sum(len(v) for v in keywords_por_cr.values())} keywords "
          f"para {len(keywords_por_cr)} CRs")
    for e in errores_csv:
        print(f"  ⚠  {e}")

    # 2. Merge
    data, stats = enriquecer(args.fichas, keywords_por_cr)

    # 3. Guardar
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 4. Resumen
    print(f"\nResultado:")
    print(f"  Fichas actualizadas : {stats['fichas_actualizadas']}")
    print(f"  Keywords añadidas   : {stats['keywords_añadidas']}")
    if stats["crs_no_encontrados"]:
        print(f"  CRs no encontrados  : {stats['crs_no_encontrados']}")
    print(f"\nJSON guardado: {args.output}")


if __name__ == "__main__":
    main()

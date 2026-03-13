"""
Parser del Reglamento (UE) 2018/858 — Artículos 3, 4 y Anexo I
Genera chunks semánticos listos para indexar en base vectorial.
"""

import pdfplumber
import re
import json
from pathlib import Path

DIR = Path(__file__).parent.parent  # raíz del proyecto
PDF_PATH    = DIR / "docs/homologacion_vehiculos_UE.pdf"
OUTPUT_PATH = DIR / "json/reglamento_ue_2018_858.json"

# ─── Limpieza de cabeceras del DOUE ──────────────────────────────────────────

PAT_EXCLUIR = re.compile(
    r'^L 151/\d+|^14\.6\.2018|^ES\s+Diario Oficial|^Diario Oficial',
    re.I
)

def limpiar(lineas):
    return [l for l in lineas if l.strip() and not PAT_EXCLUIR.search(l.strip())]

# ─── Definición de chunks ─────────────────────────────────────────────────────

CHUNKS_DEF = [
    {
        "apartado": "art3_definiciones",
        "titulo": "Artículo 3 — Definiciones (homologación, fabricante, servicio técnico, vehículo...)",
        "pag_inicio": 11,
        "pag_fin": 14,
        "marcador_inicio": None,
        "marcador_fin": "Artículo 4",
        "metadata_extra": {
            "articulo": "3",
            "retrieval_condicional": False,
            "keywords_activacion": [],
        }
    },
    {
        "apartado": "art4_categorias_vehiculos",
        "titulo": "Artículo 4 — Categorías de vehículos M, N y O con sus subcategorías",
        "pag_inicio": 14,
        "pag_fin": 14,
        "marcador_inicio": "Artículo 4",
        "marcador_fin": None,
        "metadata_extra": {
            "articulo": "4",
            "retrieval_condicional": False,
            "keywords_activacion": ["M1", "M2", "M3", "N1", "N2", "N3", "O1", "O2", "O3", "O4",
                                     "categoría", "categorias", "tipo vehículo"],
        }
    },
    {
        "apartado": "anexo1_intro_definiciones",
        "titulo": "Anexo I — Parte introductoria: definiciones generales y disposiciones (plazas, masa máxima, mercancías)",
        "pag_inicio": 66,
        "pag_fin": 67,
        "marcador_inicio": "ANEXO I",
        "marcador_fin": "PARTE A",
        "metadata_extra": {
            "anexo": "I",
            "parte": "Introductoria",
            "retrieval_condicional": False,
            "keywords_activacion": [],
        }
    },
    {
        "apartado": "anexo1_criterios_categorizacion",
        "titulo": "Anexo I — Parte A: Criterios de categorización de vehículos M, N, O y subcategorías G (todoterreno)",
        "pag_inicio": 67,
        "pag_fin": 72,
        "marcador_inicio": "PARTE A",
        "marcador_fin": "PARTE B",
        "metadata_extra": {
            "anexo": "I",
            "parte": "A",
            "retrieval_condicional": False,
            "keywords_activacion": ["todoterreno", "4x4", "categoría N1", "categoría M1",
                                     "masa máxima", "plazas de asiento"],
        }
    },
    {
        "apartado": "anexo1_tipos_carroceria_M1",
        "titulo": "Anexo I — Parte B: Tipos de vehículo y carrocería para categoría M1",
        "pag_inicio": 73,
        "pag_fin": 75,
        "marcador_inicio": "PARTE B",
        "marcador_fin": "Categorías M",
        "metadata_extra": {
            "anexo": "I",
            "parte": "B",
            "categorias": ["M1"],
            "retrieval_condicional": True,
            "keywords_activacion": ["tipo carrocería", "berlina", "monovolumen", "SUV",
                                     "todoterreno", "furgoneta", "carrocería M1"],
        }
    },
    {
        "apartado": "anexo1_tipos_carroceria_M2_M3",
        "titulo": "Anexo I — Parte B: Tipos de vehículo y carrocería para categorías M2 y M3 (autobuses)",
        "pag_inicio": 75,
        "pag_fin": 76,
        "marcador_inicio": "Categorías M",
        "marcador_fin": "Categoría N",
        "metadata_extra": {
            "anexo": "I",
            "parte": "B",
            "categorias": ["M2", "M3"],
            "retrieval_condicional": True,
            "keywords_activacion": ["autobús", "autocar", "minibús", "carrocería M2", "carrocería M3"],
        }
    },
    {
        "apartado": "anexo1_tipos_carroceria_N_O",
        "titulo": "Anexo I — Parte B y C: Tipos de vehículo y carrocería para categorías N (camiones/furgonetas) y O (remolques)",
        "pag_inicio": 76,
        "pag_fin": 83,
        "marcador_inicio": "Categoría N",
        "marcador_fin": "Apéndice 1",
        "metadata_extra": {
            "anexo": "I",
            "parte": "B-C",
            "categorias": ["N1", "N2", "N3", "O1", "O2", "O3", "O4"],
            "retrieval_condicional": True,
            "keywords_activacion": ["camión", "furgoneta", "remolque", "semirremolque",
                                     "carrocería N", "carrocería O", "volquete", "cisterna"],
        }
    },
    {
        "apartado": "anexo1_apendice_todoterreno",
        "titulo": "Anexo I — Apéndice 1: Procedimiento para verificar si un vehículo es todoterreno (ángulos, altura libre)",
        "pag_inicio": 84,
        "pag_fin": 86,
        "marcador_inicio": "Apéndice 1",
        "marcador_fin": None,
        "metadata_extra": {
            "anexo": "I",
            "parte": "Apéndice 1",
            "retrieval_condicional": True,
            "keywords_activacion": ["todoterreno", "4x4", "ángulo rampa", "altura libre suelo",
                                     "subcategoría G"],
        }
    },
]

# ─── Extracción ───────────────────────────────────────────────────────────────

def extraer_lineas(paginas_texto, pag_inicio, pag_fin):
    todas = []
    for p in range(pag_inicio, pag_fin + 1):
        texto = paginas_texto.get(p, "")
        lineas = [l.strip() for l in texto.splitlines() if l.strip()]
        todas.extend(limpiar(lineas))
    return todas

def recortar(lineas, marcador_inicio, marcador_fin):
    inicio = 0
    fin    = len(lineas)

    if marcador_inicio:
        for i, l in enumerate(lineas):
            if marcador_inicio.lower() in l.lower():
                inicio = i
                break

    if marcador_fin:
        for i, l in enumerate(lineas[inicio:], start=inicio):
            if marcador_fin.lower() in l.lower():
                fin = i
                break

    return lineas[inicio:fin]


def normalizar_subindices(texto):
    """Corrige subíndices del PDF que aparecen en línea aparte: 'M :' + '1' -> 'M1:'"""
    lineas = texto.splitlines()
    resultado = []
    i = 0
    while i < len(lineas):
        l = lineas[i]
        if re.search(r'categoría [MNO] :', l) and i + 1 < len(lineas):
            siguiente = lineas[i + 1].strip()
            if re.match(r'^\d$', siguiente):
                l = re.sub(r'(categoría [MNO]) :', rf'\g<1>{siguiente}:', l)
                i += 2
                resultado.append(l)
                continue
        resultado.append(l)
        i += 1
    return "\n".join(resultado)

def construir_chunk(defn, paginas_texto):
    lineas = extraer_lineas(paginas_texto, defn["pag_inicio"], defn["pag_fin"])
    lineas = recortar(lineas, defn["marcador_inicio"], defn["marcador_fin"])
    texto  = "\n".join(lineas).strip()

    metadata = {
        "tipo":            "reglamento_ue",
        "documento":       "Reglamento (UE) 2018/858",
        "apartado":        defn["apartado"],
        "titulo":          defn["titulo"],
        "paginas":         [defn["pag_inicio"], defn["pag_fin"]],
        "fuente":          "Reglamento (UE) 2018/858 del Parlamento Europeo y del Consejo, de 30 de mayo de 2018",
        **defn["metadata_extra"],
    }

    return {
        "apartado": defn["apartado"],
        "titulo":   defn["titulo"],
        "paginas":  [defn["pag_inicio"], defn["pag_fin"]],
        "texto":    texto,
        "metadata": metadata,
    }

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Leyendo: {PDF_PATH}")
    paginas_texto = {}

    with pdfplumber.open(PDF_PATH) as pdf:
        print(f"Total páginas: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages):
            paginas_texto[i + 1] = page.extract_text(layout=False) or ""

    chunks = []
    for defn in CHUNKS_DEF:
        chunk = construir_chunk(defn, paginas_texto)
        n_chars  = len(chunk["texto"])
        n_lineas = chunk["texto"].count("\n") + 1
        print(f"  [{chunk['apartado']:40s}] págs {chunk['paginas']} | {n_lineas:3d} líneas | {n_chars:5d} chars")
        chunks.append(chunk)

    output = {
        "metadata": {
            "fuente":        "Reglamento (UE) 2018/858 del Parlamento Europeo y del Consejo",
            "fecha":         "30 de mayo de 2018",
            "doue":          "L 151, 14.6.2018",
            "scope_parser":  "Artículos 3 y 4 + Anexo I",
            "total_chunks":  len(chunks),
            "nota":          "Deroga la Directiva 2007/46/CE. Define categorías M, N, O de vehículos.",
        },
        "chunks": chunks,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nJSON guardado: {OUTPUT_PATH}")
    print(f"Total chunks: {len(chunks)}")

if __name__ == "__main__":
    main()

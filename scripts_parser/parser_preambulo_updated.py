"""
Parser del Preámbulo del Manual de Reformas de Vehículos — Sección I
Genera chunks semánticos listos para indexar en base vectorial.
"""

import pdfplumber
import re
import json
from pathlib import Path

DIR = Path(__file__).parent.parent  # raíz del proyecto
PDF_PATH    = DIR / "docs/Manual-seccion1.pdf"
OUTPUT_PATH = DIR / "json/preambulo_seccion1.json"

# ─── Patrones de limpieza (mismos que en parser fichas CR) ────────────────────

PAT_EXCLUIR = re.compile(
    r'^MANUAL DE REFORMAS|^PREÁMBULO|^MINISTERIO|^DE INDUSTRIA|'
    r'^Y TURISMO|^REVISIÓN:|^SECCIÓN:|Página \d+ de \d+|^Fecha:',
    re.I
)

def limpiar(lineas):
    return [l for l in lineas if l.strip() and not PAT_EXCLUIR.search(l.strip())]

# ─── Definición de chunks por página y marcador ───────────────────────────────
#
# Cada chunk se define por:
#   - apartado:   identificador semántico (usado como metadato)
#   - titulo:     texto legible
#   - pag_inicio: primera página del PDF (base 1)
#   - pag_fin:    última página (inclusivo)
#   - marcador_inicio: texto que marca el comienzo dentro de la página (None = desde el inicio)
#   - marcador_fin:    texto que marca el final (None = hasta el fin de pag_fin)

CHUNKS_DEF = [
    {
        "apartado": "marco_legal",
        "titulo": "Marco legal y definición de reforma",
        "pag_inicio": 3,
        "pag_fin": 3,
        "marcador_inicio": None,
        "marcador_fin": None,
    },
    {
        "apartado": "estructura_manual",
        "titulo": "Estructura del manual y grupos de reforma",
        "pag_inicio": 4,
        "pag_fin": 4,
        "marcador_inicio": "ESTRUCTURA DEL MANUAL",
        "marcador_fin": None,
    },
    {
        "apartado": "estructura_ficha",
        "titulo": "Estructura de las fichas CR — apartados 1 a 3",
        "pag_inicio": 5,
        "pag_fin": 5,
        "marcador_inicio": "Cada función o grupo",
        "marcador_fin": "4. Actos reglamentarios",
    },
    {
        "apartado": "interpretacion_ars",
        "titulo": "Interpretación de los Actos Reglamentarios — valores (1), (2), (3), -, x",
        "pag_inicio": 5,
        "pag_fin": 5,
        "marcador_inicio": "4. Actos reglamentarios",
        "marcador_fin": None,
    },
    {
        "apartado": "proyecto_tecnico",
        "titulo": "Documentación exigible — Proyecto Técnico (apartado 5.1)",
        "pag_inicio": 6,
        "pag_fin": 8,
        "marcador_inicio": "5. Documentación exigible",
        "marcador_fin": "5.2 Certificado de dirección final de obra",
    },
    {
        "apartado": "informe_conformidad",
        "titulo": "Documentación exigible — Informe de Conformidad y Cert. Final de Obra (5.2 y 5.3)",
        "pag_inicio": 8,
        "pag_fin": 10,
        "marcador_inicio": "5.2 Certificado de dirección final de obra",
        "marcador_fin": "5.4 Certificado de Taller",
    },
    {
        "apartado": "certificado_taller",
        "titulo": "Documentación exigible — Certificado de Taller (apartado 5.4)",
        "pag_inicio": 10,
        "pag_fin": 11,
        "marcador_inicio": "5.4 Certificado de Taller",
        "marcador_fin": "6. Documentación adicional",
    },
    {
        "apartado": "apartados_6_al_10",
        "titulo": "Apartados 6-10: Documentación adicional, Conjunto funcional, Inspección, Normalización, Información adicional",
        "pag_inicio": 11,
        "pag_fin": 12,
        "marcador_inicio": "6. Documentación adicional",
        "marcador_fin": None,
    },
]


# ─── Chunk de glosario (estático, no se extrae del PDF) ──────────────────────

GLOSARIO_SIGLAS = {
    "apartado": "glosario_siglas",
    "titulo":   "Glosario de siglas y acrónimos del Manual de Reformas",
    "paginas":  None,
    "texto": (
        "Glosario de siglas y acrónimos utilizados en el Manual de Reformas de Vehículos:\n\n"
        "AR — Acto Reglamentario: directiva, reglamento europeo o norma nacional que regula un sistema "
        "o componente específico del vehículo. Cada ficha CR incluye una tabla con los ARs aplicables "
        "y su nivel de exigencia según la categoría del vehículo.\n\n"
        "CR — Código de Reforma: identificador numérico (ej. CR 4.1, CR 8.52) que tipifica una "
        "modificación concreta del vehículo. Cada CR tiene asociada una ficha con su campo de "
        "aplicación, documentación exigible e inspección específica.\n\n"
        "IC — Informe de Conformidad: documento emitido por un servicio técnico o fabricante que "
        "justifica el cumplimiento de los actos reglamentarios afectados por la reforma.\n\n"
        "ITV — Inspección Técnica de Vehículos: estación oficial donde se tramita y legaliza la "
        "reforma tras aportar la documentación exigible.\n\n"
        "DGT — Dirección General de Tráfico: organismo competente en materia de circulación y "
        "matriculación de vehículos en España.\n\n"
        "PT — Proyecto Técnico: documento técnico elaborado por un técnico competente que describe "
        "y justifica la reforma. Obligatorio en reformas de Vía A.\n\n"
        "CFO — Certificación Final de Obra: documento emitido por el técnico competente que certifica "
        "que la reforma se ha ejecutado conforme al proyecto técnico.\n\n"
        "CT — Certificado de Taller: documento emitido por el taller ejecutor que acredita la "
        "realización de la reforma.\n\n"
        "MMTA — Masa Máxima Técnicamente Admisible: masa máxima del vehículo según su construcción. "
        "Determina la categoría técnica del vehículo (N1, N2, N3...), independientemente de la MMA.\n\n"
        "MMA — Masa Máxima Autorizada: masa máxima permitida administrativamente para circular. "
        "Puede ser inferior a la MMTA sin cambiar la categoría técnica del vehículo.\n\n"
        "CEPE/ONU — Comisión Económica para Europa de Naciones Unidas: organismo que emite los "
        "Reglamentos técnicos internacionales (ej. Reglamento CEPE/ONU nº 13, nº 48...) "
        "referenciados en las tablas de ARs.\n\n"
        "RD — Real Decreto: norma de rango reglamentario. Los más relevantes para reformas son el "
        "RD 866/2010 (tramitación de reformas) y el RD 2028/1986 (actos reglamentarios aplicables).\n\n"
        "DOUE — Diario Oficial de la Unión Europea: publicación oficial donde se promulgan las "
        "directivas y reglamentos europeos referenciados como ARs."
    ),
    "metadata": {
        "tipo":                  "glosario",
        "apartado":              "glosario_siglas",
        "titulo":                "Glosario de siglas y acrónimos del Manual de Reformas",
        "paginas":               None,
        "fuente":                "Manual de Reformas de Vehículos — Sección I",
        "revision_manual":       "7ª",
        "inyectar_en_fichas":    False,
        "retrieval_condicional": False,
        "keywords_activacion":   ["AR", "CR", "IC", "ITV", "DGT", "PT", "CFO", "CT",
                                  "MMTA", "MMA", "CEPE", "ONU", "RD", "DOUE",
                                  "siglas", "acrónimos", "qué significa", "qué es"],
    }
}

# ─── Extracción de texto por rango de páginas ─────────────────────────────────

def extraer_lineas_paginas(paginas_texto, pag_inicio, pag_fin):
    """Extrae y limpia todas las líneas de un rango de páginas."""
    todas = []
    for p in range(pag_inicio, pag_fin + 1):
        texto = paginas_texto.get(p, "")
        lineas = [l.strip() for l in texto.splitlines() if l.strip()]
        todas.extend(limpiar(lineas))
    return todas

def recortar_por_marcadores(lineas, marcador_inicio, marcador_fin):
    """
    Recorta la lista de líneas entre marcador_inicio y marcador_fin.
    Si marcador_inicio es None, empieza desde el principio.
    Si marcador_fin es None, llega hasta el final.
    """
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

# ─── Construcción de chunks ───────────────────────────────────────────────────

def construir_chunk(defn, paginas_texto):
    lineas = extraer_lineas_paginas(
        paginas_texto,
        defn["pag_inicio"],
        defn["pag_fin"]
    )

    lineas = recortar_por_marcadores(
        lineas,
        defn["marcador_inicio"],
        defn["marcador_fin"]
    )

    texto = "\n".join(lineas).strip()

    return {
        "apartado":  defn["apartado"],
        "titulo":    defn["titulo"],
        "paginas":   [defn["pag_inicio"], defn["pag_fin"]],
        "texto":     texto,
        # Metadatos para el retriever
        "metadata": {
            "tipo":              "preambulo",
            "apartado":          defn["apartado"],
            "titulo":            defn["titulo"],
            "paginas":           [defn["pag_inicio"], defn["pag_fin"]],
            "fuente":            "Manual de Reformas de Vehículos — Sección I",
            "revision_manual":   "7ª",
            # Indica si este chunk debe inyectarse siempre en los chunks de fichas CR
            "inyectar_en_fichas": defn["apartado"] == "interpretacion_ars",
            # Indica si este chunk se añade condicionalmente según la query
            "retrieval_condicional": defn["apartado"] in (
                "proyecto_tecnico",
                "informe_conformidad",
                "certificado_taller"
            ),
            # Keywords que activan el retrieval condicional
            "keywords_activacion": {
                "proyecto_tecnico":    ["proyecto técnico", "certificación final", "memoria", "cálculos"],
                "informe_conformidad": ["informe de conformidad", "servicio técnico", "actos reglamentarios"],
                "certificado_taller":  ["certificado del taller", "taller"],
            }.get(defn["apartado"], []),
        }
    }

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Leyendo: {PDF_PATH}")
    paginas_texto = {}

    with pdfplumber.open(PDF_PATH) as pdf:
        for i, page in enumerate(pdf.pages):
            paginas_texto[i + 1] = page.extract_text(layout=False) or ""

    chunks = []
    for defn in CHUNKS_DEF:
        chunk = construir_chunk(defn, paginas_texto)
        n_chars = len(chunk["texto"])
        n_lineas = chunk["texto"].count("\n") + 1
        print(f"  [{chunk['apartado']:30s}] págs {chunk['paginas']} | {n_lineas} líneas | {n_chars} chars")
        chunks.append(chunk)

    # Añadir chunk de glosario (estático)
    n_chars = len(GLOSARIO_SIGLAS["texto"])
    n_lineas = GLOSARIO_SIGLAS["texto"].count("\n") + 1
    print(f"  [{GLOSARIO_SIGLAS['apartado']:30s}] págs {GLOSARIO_SIGLAS['paginas']} | {n_lineas} líneas | {n_chars} chars")
    chunks.append(GLOSARIO_SIGLAS)

    # Extraer el texto de interpretación de ARs para referencia rápida
    chunk_ars = next(c for c in chunks if c["apartado"] == "interpretacion_ars")

    output = {
        "metadata": {
            "fuente":          "Manual de Reformas de Vehículos — Sección I",
            "seccion":         "Preámbulo",
            "paginas":         [3, 12],
            "revision_manual": "7ª",
            "total_chunks":    len(chunks),  # incluye glosario_siglas
        },
        # Texto de interpretación de ARs listo para inyectar en fichas CR
        "interpretacion_ars_texto": chunk_ars["texto"],
        "chunks": chunks,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nJSON guardado: {OUTPUT_PATH}")
    print(f"Total chunks: {len(chunks)}")

if __name__ == "__main__":
    main()

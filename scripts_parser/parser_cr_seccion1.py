"""
Parser final del Manual de Reformas de Vehículos — Sección I  v3
Usa pdfplumber.extract_tables() para las tablas de ARs y documentación,
y extract_text() para los bloques de texto libre.
"""

import pdfplumber
import re
import json
from pathlib import Path

DIR = Path(__file__).parent.parent  # raíz del proyecto
PDF_PATH    = DIR / "docs/Manual-seccion1.pdf"
OUTPUT_PATH = DIR / "json/fichas_cr_seccion1_v3.json"

CATEGORIAS = ["M1", "M2", "M3", "N1", "N2", "N3", "O1", "O2", "O3", "O4"]

# ─── Patrones ─────────────────────────────────────────────────────────────────

PAT_GRUPO_CR = re.compile(r'GRUPO:\s*(\d+)\s*\((\d+\.\d+)\)', re.I)
PAT_REVISION = re.compile(r'REVISI[OÓ]N:\s*(\S+)', re.I)
PAT_FECHA    = re.compile(r'Fecha:\s*(.+)', re.I)

PAT_CABECERA_L1 = re.compile(r'^MANUAL DE REFORMAS DE VEH[IÍ]CULOS\s*$', re.I)
PAT_CABECERA_L2 = re.compile(r'^I\.-\s+VEH[IÍ]CULOS DE CATEGOR[IÍ]AS M, N y O\s*$', re.I)
PAT_CABECERA_L3 = re.compile(r'^Grupo N[oº°]\s*\d+', re.I)
PAT_CABECERA_L4 = re.compile(r'^\(\d+\.\d+\)\s*$')

PAT_PIE_MINISTERIO = re.compile(r'^MINISTERIO\s*$', re.I)
PAT_PIE_INDUSTRIA  = re.compile(r'DE INDUSTRIA', re.I)
PAT_PIE_TURISMO    = re.compile(r'Y TURISMO', re.I)
PAT_PIE_REVISION   = re.compile(r'REVISI[OÓ]N:\s*\S+', re.I)
PAT_PIE_SECCION    = re.compile(r'SECCI[OÓ]N:\s*I', re.I)
PAT_PIE_GRUPO      = re.compile(r'GRUPO:\s*\d+\s*\(\d+\.\d+\)', re.I)
PAT_PIE_PAGINA     = re.compile(r'P[aá]gina\s+\d+\s+de\s+\d+', re.I)
PAT_PIE_FECHA      = re.compile(r'Fecha:', re.I)
PAT_PIE_NOMBRE     = re.compile(
    r'^(Identificaci[oó]n|Unidad Motriz|Transmisi[oó]n|Ejes y ruedas|'
    r'Suspensi[oó]n|Direcci[oó]n|Frenos|Carrocer[ií]a|Alumbrado|'
    r'Uniones|Modificaciones)\s*$', re.I)

MARCADORES = {
    "campo_aplicacion":     re.compile(r'^CAMPO DE APLICACI[OÓ]N\s*$', re.I),
    "actos_reglamentarios": re.compile(r'^ACTOS REGLAMENTARIOS\s*$', re.I),
    "documentacion":        re.compile(r'^DOCUMENTACI[OÓ]N NECESARIA\s*$', re.I),
    "conjunto_funcional":   re.compile(r'^CONJUNTO FUNCIONAL\s*$', re.I),
    "inspeccion":           re.compile(r'^INSPECCI[OÓ]N ESPEC[IÍ]FICA\.?\s*$', re.I),
    "normalizacion":        re.compile(r'^NORMALIZACI[OÓ]N DE LA ANOTACI[OÓ]N', re.I),
    "info_adicional":       re.compile(r'^INFORMACI[OÓ]N ADICIONAL\s*$', re.I),
}

PAT_DESC_CR   = re.compile(r'^(\d+\.\d+)\.?[-–]\s+(.+)', re.DOTALL)
PAT_SINO_FILA = re.compile(r'^(S[IÍ]|NO)(\s+(S[IÍ]|NO))+', re.I)

CAMPOS_DOC = [
    "Proyecto Técnico",
    "Certificación final de obra",
    "Informe de Conformidad",
    "Certificado del Taller",
    "Documentación adicional",
]
# ─── Vías de tramitación ──────────────────────────────────────────────────────

VIA_DESC = {
    "A": "Reforma mayor — Proyecto Técnico + Certificación Final de Obra + Informe de Conformidad + Certificado de Taller",
    "B": "Reforma intermedia — Informe de Conformidad + Certificado de Taller",
    "C": "Reforma menor — solo Certificado de Taller",
    "D": "Caso especial — solo Documentación adicional",
}

def determinar_via(doc):
    if not doc:
        return None
    if doc.get("Proyecto Técnico") == "SI":
        return "A"
    elif doc.get("Informe de Conformidad") == "SI":
        return "B"
    elif doc.get("Certificado del Taller") == "SI":
        return "C"
    elif doc.get("Documentación adicional") == "SI":
        return "D"
    return None



# ─── Limpieza ─────────────────────────────────────────────────────────────────

def es_pie(l):
    return bool(
        PAT_PIE_MINISTERIO.match(l) or PAT_PIE_INDUSTRIA.search(l) or
        PAT_PIE_TURISMO.search(l)   or PAT_PIE_REVISION.search(l) or
        PAT_PIE_SECCION.search(l)   or PAT_PIE_GRUPO.search(l) or
        PAT_PIE_PAGINA.search(l)    or PAT_PIE_FECHA.search(l) or
        PAT_PIE_NOMBRE.match(l)
    )

def es_cabecera(l):
    return bool(
        PAT_CABECERA_L1.match(l) or PAT_CABECERA_L2.match(l) or
        PAT_CABECERA_L3.match(l) or PAT_CABECERA_L4.match(l)
    )

def limpiar(lineas):
    return [l for l in lineas if not es_cabecera(l) and not es_pie(l)]

# ─── Extracción tablas por página ─────────────────────────────────────────────

def extraer_tabla_ar_de_pagina(page):
    """
    Extrae la tabla de ARs de una página (12 columnas: sistema, ref, M1..O4).
    Devuelve lista de filas de datos (sin cabeceras).
    """
    for tabla in page.extract_tables():
        if not tabla or len(tabla[0]) != 12:
            continue
        # Verificar que es la tabla de ARs buscando la fila de cabecera
        es_ar = any(
            fila and fila[0] and "ACTOS REGLAMENTARIOS" in str(fila[0])
            for fila in tabla[:5]
        )
        if not es_ar:
            continue

        filas_datos = []
        cabecera_vista = False
        for fila in tabla:
            # Saltar filas de cabecera (vacías, título, "Sistema afectado", categorías)
            if not fila[0]:
                continue
            txt = str(fila[0]).strip()
            if any(kw in txt for kw in ("ACTOS REGLAMENTARIOS", "Sistema afectado",
                                        "Ver Apartado", "Aplicable")):
                cabecera_vista = True
                continue
            if fila[2] in ("M1", None) and fila[3] == "M2":
                continue  # fila de categorías
            if not cabecera_vista:
                continue

            # Fila de datos
            sistema    = (fila[0] or "").replace("\n", " ").strip()
            referencia = (fila[1] or "").replace("\n", " ").strip()
            valores    = [(fila[i] or "").strip() for i in range(2, 12)]

            # Normalizar valores
            def norm(v):
                v = v.strip()
                if v in ("(1)", "(2)", "(3)"): return v
                if v in ("-", "–"):            return "-"
                if v.lower() == "x":           return "x"
                return "-" if not v else v

            aplicabilidad = {cat: norm(v) for cat, v in zip(CATEGORIAS, valores)}

            if sistema or referencia:
                filas_datos.append({
                    "sistema": sistema,
                    "referencia": referencia,
                    "aplicabilidad": aplicabilidad,
                })
        return filas_datos
    return []

def _extraer_sino_de_fila(fila):
    """
    Extrae 5 valores SI/NO de una fila de tabla.
    Devuelve dict o None.
    """
    if not fila:
        return None
    celdas = [str(c or "").strip() for c in fila if c is not None]
    si_no = [v for v in celdas if re.match(r'^S[IÍ]$|^NO$|^S[IÍ]\s|^NO\s', v.strip(), re.I)]
    # Limpiar valores (quitar asteriscos)
    si_no_clean = [re.sub(r'[\(\)\*∗\s].*', '', v).strip() for v in si_no]
    si_no_clean = [v for v in si_no_clean if re.match(r'^S[IÍ]$|^NO$', v, re.I)]
    if len(si_no_clean) >= 5:
        return {campo: ("SI" if re.match(r'^S[IÍ]$', v, re.I) else "NO")
                for campo, v in zip(CAMPOS_DOC, si_no_clean[:5])}
    return None

def extraer_tabla_doc_de_pagina(page, pagina_siguiente=None):
    """
    Extrae la tabla de documentación necesaria.
    Caso normal: tabla de 7 cols con DOCUMENTACIÓN NECESARIA + fila SI/NO en misma página.
    Caso especial (ej. CR 11.3): cabecera en pág N, valores en pág N+1.
    """
    tiene_doc_header = False

    for tabla in page.extract_tables():
        if not tabla:
            continue
        texto_tabla = str(tabla)

        if "DOCUMENTACI" in texto_tabla.upper():
            tiene_doc_header = True
            # Buscar fila de valores en esta misma tabla
            for fila in reversed(tabla):
                resultado = _extraer_sino_de_fila(fila)
                if resultado:
                    return resultado

    # Si hay cabecera pero no valores, buscar en la página siguiente
    if tiene_doc_header and pagina_siguiente is not None:
        for tabla in pagina_siguiente.extract_tables():
            if not tabla:
                continue
            # Buscar una tabla pequeña con solo valores SI/NO (1-2 filas, 5 cols)
            for fila in tabla:
                resultado = _extraer_sino_de_fila(fila)
                if resultado:
                    return resultado

    return None

# ─── Segmentación de texto libre ─────────────────────────────────────────────

def segmentar_bloques(lineas):
    """
    Segmenta las líneas en bloques según marcadores.
    El marcador ACTOS REGLAMENTARIOS repetido (cabecera de tabla en pag 2)
    NO crea un nuevo bloque — se detecta y se ignora.
    """
    bloques = {}
    bloque_actual = "descripcion"
    buffer = []

    for linea in lineas:
        marcador = None
        for nombre, patron in MARCADORES.items():
            if patron.match(linea):
                marcador = nombre
                break

        if marcador:
            if marcador == bloque_actual:
                continue  # marcador repetido (tabla continúa en pág siguiente)
            bloques[bloque_actual] = buffer
            bloque_actual = marcador
            buffer = []
        else:
            buffer.append(linea)

    bloques[bloque_actual] = buffer
    return bloques

def parsear_descripcion(lineas):
    desc_grupo = ""
    desc_cr_partes = []
    en_desc_cr = False

    for l in lineas:
        if re.match(r'^DESCRIPCI[OÓ]N:', l, re.I):
            desc_grupo = l.split(":", 1)[1].strip() if ":" in l else ""
        m = PAT_DESC_CR.match(l)
        if m:
            desc_cr_partes = [m.group(2).strip()]
            en_desc_cr = True
        elif en_desc_cr:
            if l and not any(MARCADORES[k].match(l) for k in MARCADORES):
                desc_cr_partes.append(l.strip())
            else:
                en_desc_cr = False

    return desc_grupo, " ".join(desc_cr_partes).strip()

def parsear_campo_aplicacion(lineas):
    cats = []
    for i, l in enumerate(lineas):
        tokens = l.split()
        candidatos = [t for t in tokens if t in CATEGORIAS]
        if len(candidatos) >= 5:
            cats = candidatos
            continue
        if cats and PAT_SINO_FILA.match(l):
            vals = [t for t in tokens if re.match(r'^S[IÍ]$|^NO$', t, re.I)]
            if len(vals) >= len(cats):
                return {cat: ("SI" if v.upper() in ("SI","SÍ") else "NO")
                        for cat, v in zip(cats, vals)}
    return {}

def parsear_detalles_doc(lineas):
    detalles = {}
    campo_actual = None
    buffer = []

    for l in lineas:
        if l.startswith("•"):
            if campo_actual is not None:
                detalles[campo_actual] = " ".join(buffer).strip()
            campo_actual = l.lstrip("• ").strip()
            buffer = []
        elif campo_actual is not None:
            buffer.append(l.strip())

    if campo_actual is not None:
        detalles[campo_actual] = " ".join(buffer).strip()

    return detalles

# ─── Parser de ficha ─────────────────────────────────────────────────────────

def parsear_ficha(cr, grupo, paginas_texto, paginas_obj, pag_inicio, pag_fin):
    """
    Parsea una ficha CR. Usa extract_tables() para ARs y documentación,
    y extract_text() para los bloques de texto libre.
    """
    todas_lineas = []
    revision = None
    fecha    = None

    # Acumular ARs y tabla doc de todas las páginas
    ars_acumulados   = []
    doc_tabla        = None

    for p in range(pag_inicio, pag_fin + 1):
        texto    = paginas_texto.get(p, "")
        page_obj = paginas_obj.get(p)

        lineas_raw = [l.strip() for l in texto.splitlines() if l.strip()]

        # Capturar metadatos del pie
        for l in lineas_raw:
            if not revision:
                m = PAT_REVISION.search(l)
                if m: revision = m.group(1)
            if not fecha:
                mf = PAT_FECHA.search(l)
                if mf and PAT_PIE_FECHA.search(l):
                    fecha = mf.group(1).strip()

        todas_lineas.extend(limpiar(lineas_raw))

        # Extraer tabla de ARs con coordenadas
        if page_obj:
            ars_pagina = extraer_tabla_ar_de_pagina(page_obj)
            ars_acumulados.extend(ars_pagina)

            # Tabla de documentación (solo la primera página donde aparece)
            if doc_tabla is None:
                pag_siguiente_obj = paginas_obj.get(p + 1)
                doc_tabla = extraer_tabla_doc_de_pagina(page_obj, pag_siguiente_obj)

    # Segmentar bloques de texto libre
    bloques = segmentar_bloques(todas_lineas)

    desc_grupo, desc_cr = parsear_descripcion(bloques.get("descripcion", []))

    campo_aplicacion = parsear_campo_aplicacion(bloques.get("campo_aplicacion", []))
    cats_aplicables  = [c for c, v in campo_aplicacion.items() if v == "SI"]

    # Detalles de documentación (bullets de texto)
    doc_detalles = parsear_detalles_doc(bloques.get("documentacion", []))

    conjunto_funcional = " ".join(bloques.get("conjunto_funcional", [])).strip() or None
    if conjunto_funcional in ("---", "—", "–", ""): conjunto_funcional = None

    insp_lines = [l for l in bloques.get("inspeccion", [])
                  if "MANUAL DE PROCEDIMIENTO" not in l.upper()]
    inspeccion  = " ".join(insp_lines).strip() or None

    normalizacion = " ".join(bloques.get("normalizacion", [])).strip() or None
    info_adicional = " ".join(bloques.get("info_adicional", [])).strip() or None

    return {
        "seccion": "I",
        "grupo_numero": int(grupo),
        "cr": cr,
        "revision": revision,
        "fecha_revision": fecha,
        "paginas": [pag_inicio, pag_fin],
        "descripcion_grupo": desc_grupo,
        "descripcion_cr": desc_cr,
        "campo_aplicacion": campo_aplicacion,
        "categorias_aplicables": cats_aplicables,
        "actos_reglamentarios": ars_acumulados,
        "documentacion_necesaria": doc_tabla or {},
        "documentacion_detalle": doc_detalles,
        "conjunto_funcional": conjunto_funcional,
        "inspeccion_especifica": inspeccion,
        "normalizacion_tarjeta_itv": normalizacion,
        "informacion_adicional": info_adicional,
        "via_tramitacion": determinar_via(doc_tabla or {}),
        "via_tramitacion_desc": VIA_DESC.get(determinar_via(doc_tabla or {}), ""),
        "keywords_reformas": [],  # campo para enriquecimiento posterior (CSV cliente)
    }

# ─── Orquestador ─────────────────────────────────────────────────────────────

def main():
    print(f"Leyendo: {PDF_PATH}")
    paginas_texto = {}
    paginas_obj   = {}

    with pdfplumber.open(PDF_PATH) as pdf:
        for i, page in enumerate(pdf.pages):
            pag = i + 1
            paginas_texto[pag] = page.extract_text(layout=False) or ""
            paginas_obj[pag]   = page

        # Detectar fichas
        fichas_raw = []
        cr_actual = grupo_actual = pag_inicio_actual = None

        for pag in range(1, len(paginas_texto) + 1):
            m = PAT_GRUPO_CR.search(paginas_texto[pag])
            if m:
                cr = m.group(2); grupo = m.group(1)
                if cr != cr_actual:
                    if cr_actual is not None:
                        fichas_raw.append((cr_actual, grupo_actual, pag_inicio_actual, pag - 1))
                    cr_actual, grupo_actual, pag_inicio_actual = cr, grupo, pag
        if cr_actual:
            fichas_raw.append((cr_actual, grupo_actual, pag_inicio_actual, len(paginas_texto)))

        print(f"Fichas detectadas: {len(fichas_raw)}\n")

        fichas = []
        errores = []

        for cr, grupo, pag_ini, pag_fin in fichas_raw:
            try:
                f = parsear_ficha(cr, grupo, paginas_texto, paginas_obj, pag_ini, pag_fin)
                fichas.append(f)
                n_ars  = len(f["actos_reglamentarios"])
                cats   = ", ".join(f["categorias_aplicables"]) or "ninguna"
                n_doc  = len(f["documentacion_necesaria"])
                doc_ok = "✓doc" if n_doc == 5 else f"⚠doc({n_doc})"
                via   = f['via_tramitacion'] or '?'
                print(f"  CR {cr:6s} | Rev {f['revision'] or '?':5s} | "
                      f"{n_ars:2d} ARs | {doc_ok} | Vía {via} | {cats}")
            except Exception as e:
                import traceback
                errores.append({"cr": cr, "error": str(e),
                                "trace": traceback.format_exc()})
                print(f"  CR {cr:6s} | ERROR: {e}")

    output = {
        "metadata": {
            "fuente": "Manual de Reformas de Vehículos — Sección I",
            "revision_manual": "7ª Revisión (Corrección 2ª)",
            "total_fichas": len(fichas),
            "errores_parser": len(errores),
            "vias_tramitacion": {
                via: {
                    "count": sum(1 for f in fichas if f["via_tramitacion"] == via),
                    "descripcion": desc
                }
                for via, desc in VIA_DESC.items()
            },
        },
        "fichas": fichas,
        "errores": errores,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nJSON: {OUTPUT_PATH}")
    print(f"Fichas: {len(fichas)} | Errores: {len(errores)}")

if __name__ == "__main__":
    main()

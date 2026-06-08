"""
Parser del Manual de Reformas de Vehículos — Secciones II, III y IV
Usa el PDF completo (Revisión 7.2) con rangos de página por sección.

Sección II  (págs. 218–438): Vehículos de categorías L, Quads y UTV
Sección III (págs. 445–631): Vehículos agrícolas
Sección IV  (págs. 638–828): Vehículos de obras y/o servicios
"""

import pdfplumber
import re
import json
from pathlib import Path

DIR      = Path(__file__).parent.parent
PDF_PATH = DIR / "docs/Manual de Reformas de Vehículos Revisión 7.2.pdf"

# ─── Configuración por sección ────────────────────────────────────────────────

SECCIONES = {
    "II": {
        "pag_ini":    218,
        "pag_fin":    438,
        "titulo":     "Vehículos de categorías L, Quads y UTV",
        "categorias": ["Quad", "UTV", "L1e", "L2e", "L3e", "L4e", "L5e", "L6e", "L7e"],
        "n_cols_ar":  11,   # 2 fijas (sistema + ref) + 9 categorías
    },
    "III": {
        "pag_ini":    445,
        "pag_fin":    631,
        "titulo":     "Vehículos agrícolas",
        "categorias": ["T1", "T2", "T3", "T4", "T5.1", "T5.2", "MTC", "MAA", "MA2", "MA3", "TCA", "RA", "MAR"],
        "n_cols_ar":  15,   # 2 + 13 categorías
    },
    "IV": {
        "pag_ini":    638,
        "pag_fin":    828,
        "titulo":     "Vehículos de obras y/o servicios",
        "categorias": ["T1", "T2", "T3", "T4", "T5.1", "T5.2", "MTC", "MAA", "MA2", "MA3", "TCA", "RA", "MAR"],
        "n_cols_ar":  15,
    },
}

VIA_DESC = {
    "A": "Reforma mayor — Proyecto Técnico + Certificación Final de Obra + Informe de Conformidad + Certificado de Taller",
    "B": "Reforma intermedia — Informe de Conformidad + Certificado de Taller",
    "C": "Reforma menor — solo Certificado de Taller",
    "D": "Caso especial — solo Documentación adicional",
}

CAMPOS_DOC = [
    "Proyecto Técnico",
    "Certificación final de obra",
    "Informe de Conformidad",
    "Certificado del Taller",
    "Documentación adicional",
]

# ─── Patrones ─────────────────────────────────────────────────────────────────

PAT_GRUPO_CR = re.compile(r'GRUPO:\s*(\d+)\s*\((\d+\.\d+)\)', re.I)
PAT_REVISION = re.compile(r'REVISI[OÓ]N:\s*(\S+)', re.I)
PAT_FECHA    = re.compile(r'Fecha:\s*(.+)', re.I)

PAT_CABECERA_L1  = re.compile(r'^MANUAL DE REFORMAS DE VEH[IÍ]CULOS\s*$', re.I)
PAT_CABECERA_SEC = re.compile(r'^(II|III|IV)\.-\s+', re.I)
PAT_CABECERA_L3  = re.compile(r'^Grupo N[oº°]\s*\d+', re.I)
PAT_CABECERA_L4  = re.compile(r'^\(\d+\.\d+\)\s*$')

PAT_PIE_MINISTERIO = re.compile(r'^MINISTERIO\s*$', re.I)
PAT_PIE_INDUSTRIA  = re.compile(r'DE INDUSTRIA', re.I)
PAT_PIE_TURISMO    = re.compile(r'Y TURISMO', re.I)
PAT_PIE_REVISION   = re.compile(r'REVISI[OÓ]N:\s*\S+', re.I)
PAT_PIE_SECCION    = re.compile(r'SECCI[OÓ]N:\s*(II|III|IV)', re.I)
PAT_PIE_GRUPO      = re.compile(r'GRUPO:\s*\d+\s*\(\d+\.\d+\)', re.I)
PAT_PIE_PAGINA     = re.compile(r'P[aá]gina\s+\d+\s+de\s+\d+', re.I)
PAT_PIE_FECHA      = re.compile(r'Fecha:', re.I)
PAT_PIE_NOMBRE     = re.compile(
    r'^(Identificaci[oó]n|Unidad Motriz|Transmisi[oó]n|Ejes y ruedas|'
    r'Suspensi[oó]n|Direcci[oó]n|Frenos|Carrocer[ií]a|Alumbrado|'
    r'Uniones|Modificaciones|Combustible|Motor|Otros|Accesorios)\s*$', re.I
)

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
        PAT_CABECERA_L1.match(l)  or PAT_CABECERA_SEC.match(l) or
        PAT_CABECERA_L3.match(l)  or PAT_CABECERA_L4.match(l)
    )

def limpiar(lineas):
    return [l for l in lineas if not es_cabecera(l) and not es_pie(l)]

# ─── Extracción de tabla de ARs (flexible por sección) ───────────────────────

def _norm_valor(v):
    v = (v or "").strip()
    if v in ("(1)", "(2)", "(3)"): return v
    if v in ("-", "–"):            return "-"
    if v.lower() == "x":          return "x"
    return "-" if not v else v


def extraer_tabla_ar_de_pagina(page, categorias, n_cols_ar):
    """
    Extrae la tabla de ARs de una página.
    Busca la tabla con 'ACTOS REGLAMENTARIOS' y el número esperado de columnas.
    Las tablas más complejas (subcategorías) se ignoran en favor de la tabla primaria.
    """
    for tabla in page.extract_tables():
        if not tabla or len(tabla[0]) != n_cols_ar:
            continue

        # Verificar que es tabla de ARs
        es_ar = any(
            fila and fila[0] and "ACTOS REGLAMENTARIOS" in str(fila[0])
            for fila in tabla[:5]
        )
        if not es_ar:
            continue

        # Detectar la fila de categorías (contiene los nombres de las categorías primarias)
        fila_cats_idx = None
        cats_detectadas = None
        for i, fila in enumerate(tabla):
            if not fila:
                continue
            celdas = [str(c or "").replace("\n", " ").strip() for c in fila]
            # Buscar al menos 3 categorías esperadas en esta fila
            match_cats = [c for c in celdas if c in categorias]
            if len(match_cats) >= min(3, len(categorias)):
                fila_cats_idx = i
                cats_detectadas = [str(c or "").replace("\n", " ").strip() for c in fila[2:]]
                break

        if fila_cats_idx is None:
            continue

        filas_datos = []
        for fila in tabla[fila_cats_idx + 1:]:
            if not fila or not fila[0]:
                continue
            txt = str(fila[0]).strip()
            if any(kw in txt for kw in ("ACTOS REGLAMENTARIOS", "Sistema afectado",
                                        "Ver Apartado", "Aplicable")):
                continue
            if not txt and not fila[1]:
                continue

            sistema    = (fila[0] or "").replace("\n", " ").strip()
            referencia = (fila[1] or "").replace("\n", " ").strip()
            valores    = [_norm_valor(fila[i]) for i in range(2, len(fila))]

            # Mapear solo las categorías primarias detectadas
            aplicabilidad = {}
            for cat, val in zip(cats_detectadas, valores):
                if cat in categorias:
                    aplicabilidad[cat] = val

            if sistema or referencia:
                filas_datos.append({
                    "sistema":        sistema,
                    "referencia":     referencia,
                    "aplicabilidad":  aplicabilidad,
                })

        return filas_datos
    return []


# ─── Extracción de tabla de documentación ────────────────────────────────────

def _extraer_sino_de_fila(fila):
    if not fila:
        return None
    celdas = [str(c or "").strip() for c in fila if c is not None]
    si_no = [v for v in celdas if re.match(r'^S[IÍ]$|^NO$|^S[IÍ]\s|^NO\s', v.strip(), re.I)]
    si_no_clean = [re.sub(r'[\(\)\*∗\s].*', '', v).strip() for v in si_no]
    si_no_clean = [v for v in si_no_clean if re.match(r'^S[IÍ]$|^NO$', v, re.I)]
    if len(si_no_clean) >= 5:
        return {campo: ("SI" if re.match(r'^S[IÍ]$', v, re.I) else "NO")
                for campo, v in zip(CAMPOS_DOC, si_no_clean[:5])}
    return None


def extraer_tabla_doc_de_pagina(page, pagina_siguiente=None):
    tiene_doc_header = False

    for tabla in page.extract_tables():
        if not tabla:
            continue
        texto_tabla = str(tabla)

        if "DOCUMENTACI" in texto_tabla.upper():
            tiene_doc_header = True
            for fila in reversed(tabla):
                resultado = _extraer_sino_de_fila(fila)
                if resultado:
                    return resultado

    if tiene_doc_header and pagina_siguiente is not None:
        for tabla in pagina_siguiente.extract_tables():
            if not tabla:
                continue
            for fila in tabla:
                resultado = _extraer_sino_de_fila(fila)
                if resultado:
                    return resultado

    return None


# ─── Segmentación de texto libre ─────────────────────────────────────────────

def segmentar_bloques(lineas):
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
                continue
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


def parsear_campo_aplicacion(lineas, categorias):
    cats = []
    for l in lineas:
        tokens = l.split()
        candidatos = [t for t in tokens if t in categorias]
        if len(candidatos) >= min(3, len(categorias)):
            cats = candidatos
            continue
        if cats and PAT_SINO_FILA.match(l):
            vals = [t for t in tokens if re.match(r'^S[IÍ]$|^NO$', t, re.I)]
            if len(vals) >= len(cats):
                return {cat: ("SI" if v.upper() in ("SI", "SÍ") else "NO")
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


# ─── Parser de una ficha ─────────────────────────────────────────────────────

def parsear_ficha(cr, grupo, seccion, categorias, n_cols_ar,
                  paginas_texto, paginas_obj, pag_inicio, pag_fin):
    todas_lineas = []
    revision = None
    fecha    = None
    ars_acumulados = []
    doc_tabla = None

    for p in range(pag_inicio, pag_fin + 1):
        texto    = paginas_texto.get(p, "")
        page_obj = paginas_obj.get(p)

        lineas_raw = [l.strip() for l in texto.splitlines() if l.strip()]

        for l in lineas_raw:
            if not revision:
                m = PAT_REVISION.search(l)
                if m: revision = m.group(1)
            if not fecha:
                mf = PAT_FECHA.search(l)
                if mf and PAT_PIE_FECHA.search(l):
                    fecha = mf.group(1).strip()

        todas_lineas.extend(limpiar(lineas_raw))

        if page_obj:
            ars_pagina = extraer_tabla_ar_de_pagina(page_obj, categorias, n_cols_ar)
            ars_acumulados.extend(ars_pagina)

            if doc_tabla is None:
                pag_siguiente_obj = paginas_obj.get(p + 1)
                doc_tabla = extraer_tabla_doc_de_pagina(page_obj, pag_siguiente_obj)

    bloques = segmentar_bloques(todas_lineas)

    desc_grupo, desc_cr = parsear_descripcion(bloques.get("descripcion", []))

    campo_aplicacion = parsear_campo_aplicacion(
        bloques.get("campo_aplicacion", []), categorias
    )
    cats_aplicables = [c for c, v in campo_aplicacion.items() if v == "SI"]

    doc_detalles = parsear_detalles_doc(bloques.get("documentacion", []))

    conjunto_funcional = " ".join(bloques.get("conjunto_funcional", [])).strip() or None
    if conjunto_funcional in ("---", "—", "–", ""): conjunto_funcional = None

    insp_lines = [l for l in bloques.get("inspeccion", [])
                  if "MANUAL DE PROCEDIMIENTO" not in l.upper()]
    inspeccion = " ".join(insp_lines).strip() or None

    normalizacion   = " ".join(bloques.get("normalizacion", [])).strip() or None
    info_adicional  = " ".join(bloques.get("info_adicional", [])).strip() or None

    via = determinar_via(doc_tabla or {})

    return {
        "seccion":              seccion,
        "grupo_numero":         int(grupo),
        "cr":                   cr,
        "revision":             revision,
        "fecha_revision":       fecha,
        "paginas":              [pag_inicio, pag_fin],
        "descripcion_grupo":    desc_grupo,
        "descripcion_cr":       desc_cr,
        "campo_aplicacion":     campo_aplicacion,
        "categorias_aplicables": cats_aplicables,
        "actos_reglamentarios": ars_acumulados,
        "documentacion_necesaria": doc_tabla or {},
        "documentacion_detalle": doc_detalles,
        "conjunto_funcional":   conjunto_funcional,
        "inspeccion_especifica": inspeccion,
        "normalizacion_tarjeta_itv": normalizacion,
        "informacion_adicional": info_adicional,
        "via_tramitacion":      via,
        "via_tramitacion_desc": VIA_DESC.get(via, ""),
        "keywords_reformas":    [],
    }


# ─── Orquestador ─────────────────────────────────────────────────────────────

def parsear_seccion(seccion, cfg, paginas_texto, paginas_obj):
    print(f"\n{'='*60}")
    print(f"  Sección {seccion}: {cfg['titulo']}")
    print(f"  Páginas {cfg['pag_ini']}–{cfg['pag_fin']}")
    print(f"{'='*60}")

    categorias = cfg["categorias"]
    n_cols_ar  = cfg["n_cols_ar"]
    pag_ini    = cfg["pag_ini"]
    pag_fin    = cfg["pag_fin"]

    # Detectar fichas en el rango de páginas
    fichas_raw = []
    cr_actual = grupo_actual = pag_inicio_actual = None

    for pag in range(pag_ini, pag_fin + 1):
        m = PAT_GRUPO_CR.search(paginas_texto.get(pag, ""))
        if m:
            cr = m.group(2)
            grupo = m.group(1)
            if cr != cr_actual:
                if cr_actual is not None:
                    fichas_raw.append((cr_actual, grupo_actual, pag_inicio_actual, pag - 1))
                cr_actual, grupo_actual, pag_inicio_actual = cr, grupo, pag

    if cr_actual:
        fichas_raw.append((cr_actual, grupo_actual, pag_inicio_actual, pag_fin))

    print(f"  Fichas detectadas: {len(fichas_raw)}")

    fichas = []
    errores = []

    for cr, grupo, pag_ini_ficha, pag_fin_ficha in fichas_raw:
        try:
            f = parsear_ficha(
                cr, grupo, seccion, categorias, n_cols_ar,
                paginas_texto, paginas_obj, pag_ini_ficha, pag_fin_ficha
            )
            fichas.append(f)
            n_ars  = len(f["actos_reglamentarios"])
            cats   = ", ".join(f["categorias_aplicables"]) or "ninguna"
            n_doc  = len(f["documentacion_necesaria"])
            doc_ok = "✓doc" if n_doc == 5 else f"⚠doc({n_doc})"
            via    = f["via_tramitacion"] or "?"
            print(f"  CR {cr:6s} | Rev {f['revision'] or '?':5s} | "
                  f"{n_ars:2d} ARs | {doc_ok} | Vía {via} | {cats[:60]}")
        except Exception as e:
            import traceback
            errores.append({"cr": cr, "seccion": seccion, "error": str(e),
                            "trace": traceback.format_exc()})
            print(f"  CR {cr:6s} | ERROR: {e}")

    return fichas, errores


def main():
    print(f"Leyendo: {PDF_PATH}")
    paginas_texto = {}
    paginas_obj   = {}

    with pdfplumber.open(PDF_PATH) as pdf:
        total_pags = len(pdf.pages)
        print(f"Total páginas: {total_pags}")

        # Cargar solo las páginas de las secciones II, III y IV
        pag_min = min(cfg["pag_ini"] for cfg in SECCIONES.values())
        pag_max = min(max(cfg["pag_fin"] for cfg in SECCIONES.values()), total_pags)

        for i in range(pag_min - 1, pag_max):
            pag = i + 1
            paginas_texto[pag] = pdf.pages[i].extract_text(layout=False) or ""
            paginas_obj[pag]   = pdf.pages[i]

        todas_fichas = []
        todos_errores = []

        for seccion, cfg in SECCIONES.items():
            fichas, errores = parsear_seccion(seccion, cfg, paginas_texto, paginas_obj)
            todas_fichas.extend(fichas)
            todos_errores.extend(errores)

    # Estadísticas por sección
    stats = {}
    for sec in SECCIONES:
        fichas_sec = [f for f in todas_fichas if f["seccion"] == sec]
        stats[sec] = {
            "total":           len(fichas_sec),
            "titulo":          SECCIONES[sec]["titulo"],
            "vias": {
                via: sum(1 for f in fichas_sec if f["via_tramitacion"] == via)
                for via in ("A", "B", "C", "D")
            }
        }

    output = {
        "metadata": {
            "fuente":          "Manual de Reformas de Vehículos — Secciones II, III y IV",
            "revision_manual": "7ª (Revisión 7.2)",
            "pdf":             "Manual de Reformas de Vehículos Revisión 7.2.pdf",
            "total_fichas":    len(todas_fichas),
            "errores_parser":  len(todos_errores),
            "por_seccion":     stats,
        },
        "fichas":   todas_fichas,
        "errores":  todos_errores,
    }

    output_path = DIR / "json/fichas_cr_secciones_ii_iii_iv.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"JSON guardado: {output_path}")
    print(f"Total fichas: {len(todas_fichas)} | Errores: {len(todos_errores)}")
    for sec, s in stats.items():
        print(f"  Sección {sec}: {s['total']} fichas — {s['titulo']}")
    if todos_errores:
        print(f"\n⚠ Errores ({len(todos_errores)}):")
        for e in todos_errores:
            print(f"  CR {e['cr']} (Sección {e['seccion']}): {e['error']}")


if __name__ == "__main__":
    main()

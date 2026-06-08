"""
parser_directivas_ar.py — Descarga directivas y reglamentos EU desde EUR-Lex (CELLAR).

Lee json/normativas_ar.json (generado por build_graph.py), construye el código CELEX
para cada referencia, descarga el texto desde EUR-Lex y consulta CELLAR para metadatos
de vigencia. Guarda json/directivas_ar.json listo para indexar en ChromaDB.

Patrón CELEX:
  3 + año(4) + tipo(L=directiva, R=reglamento) + número(4 dígitos con ceros)
  Ejemplo: 70/222/CEE → 31970L0222 · R(UE) 168/2013 → 32013R0168

Uso:
    python scripts_parser/parser_directivas_ar.py           # descarga todas (con caché)
    python scripts_parser/parser_directivas_ar.py --ref 70/222/CEE 97/27/CE
    python scripts_parser/parser_directivas_ar.py --reset   # ignora caché y re-descarga
    python scripts_parser/parser_directivas_ar.py --dry-run # muestra CELEXs sin descargar
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── Paths ────────────────────────────────────────────────────────────────────

ROOT            = Path(__file__).resolve().parents[1]
NORMATIVAS_PATH = ROOT / "json" / "normativas_ar.json"
OUTPUT_PATH     = ROOT / "json" / "directivas_ar.json"

# ─── EUR-Lex ──────────────────────────────────────────────────────────────────

# Endpoint CELLAR oficial — no tiene la protección WAF de eur-lex.europa.eu
# Redirige internamente a publications.europa.eu/resource/cellar/{uuid}
CELLAR_DOC     = "https://publications.europa.eu/resource/celex/{celex}"
CELLAR_SPARQL  = "https://publications.europa.eu/webapi/rdf/sparql"

HEADERS = {
    "User-Agent":      "HomologacionesBot/1.0 (research; contact: msp40industry@gmail.com)",
    "Accept-Language": "es,en;q=0.8",
    "Accept":          "text/html",
}

DELAY_S = 1.5   # segundos entre peticiones — respetar rate limits de EUR-Lex


# ─── Construcción de CELEX ───────────────────────────────────────────────────

def construir_celex(referencia: str) -> str | None:
    """
    Construye el código CELEX desde una referencia (posiblemente con ruido).

    Limpieza previa aplicada antes de parsear:
      - Prefijo de anexo:    "Anexo VII 94/20/CE"      → "94/20/CE"
      - Múltiples refs (;):  "77/536/CEE; 79/622/CEE"  → toma la primera
      - Sufijo en paréntesis: "89/173/CEE (II)"         → "89/173/CEE"
      - Sufijo Capítulo:     "97/24/CE Capítulo 3"      → "97/24/CE"
      - Sufijo Anexo:        "R(UE) 1322/2014 Anexo XIX"→ "R(UE) 1322/2014"
      - Numeral romano final: "89/173/CEE III"           → "89/173/CEE"
      - Espacio antes de CE:  "89/297 CEE"               → "89/297/CEE"

    Patrones CELEX generados:
      Directiva CEE/CE/UE : 3{año4d}L{num:04d}
      Reglamento (UE)/(CE): 3{año4d}R{num:04d}
      Reglamento sin prefij: 3{año4d}R{num:04d}

    Devuelve None si la referencia no encaja en ningún patrón conocido.
    """
    ref = referencia.strip()

    # Limpiar prefijos de tipo "Anexo VII 94/20/CE" → "94/20/CE"
    ref = re.sub(r'^Anexo[^/\d]*\s+', '', ref, flags=re.I).strip()

    # Tomar solo la primera ref si hay varias separadas por ";" o ","
    ref = re.split(r'\s*[;,]\s*', ref)[0].strip()

    # Eliminar sufijos: "(II)", "(Anexo VII)", "Capítulo 3", "III", "Anexo XIX"
    ref = re.sub(r'\s*\([^)]*\)\s*$', '', ref).strip()                      # (texto)
    ref = re.sub(r'\s+Cap[íi]?tulo\s+\S+\s*$', '', ref, flags=re.I).strip() # Capítulo N
    ref = re.sub(r'\s+Anexo\s+\S+\s*$', '', ref, flags=re.I).strip()        # Anexo XX
    ref = re.sub(r'\s+[IVX]+\s*$', '', ref).strip()                         # numerales romanos

    # Normalizar espacio → barra antes de CE/CEE: "89/297 CEE" → "89/297/CEE"
    ref = re.sub(r'(\d)\s+(C(?:EE|E))\b', r'\1/\2', ref, flags=re.I)

    # ── Patrones ──────────────────────────────────────────────────────────────

    def _year(y_raw: int) -> int:
        if y_raw >= 100:
            return y_raw
        return 1900 + y_raw if y_raw > 57 else 2000 + y_raw

    # 1. Directiva CEE / CE / UE: año/num/C(EE|E|UE)
    m = re.match(r'^(\d{2,4})/(\d+)/(?:C(?:EE|E)|UE)$', ref, re.I)
    if m:
        return f"3{_year(int(m.group(1)))}L{int(m.group(2)):04d}"

    # 2. Reglamento (UE): "R(UE) 168/2013" o "Reglamento (UE) 2019/2144"
    m = re.match(
        r'^R(?:eglamento)?\s*\(UE\)\s*(?:N[oº°]\s*)?(\d+)/(\d{4})$', ref, re.I,
    )
    if m:
        return f"3{int(m.group(2))}R{int(m.group(1)):04d}"

    # 3. Reglamento (CE): "Reglamento (CE) Nº 595/2009"
    m = re.match(r'^Reglamento\s+\(CE\)\s+N[oº°]\s*(\d+)/(\d{4})$', ref, re.I)
    if m:
        return f"3{int(m.group(2))}R{int(m.group(1)):04d}"

    # 4. Reglamento sin prefijo explícito: num/año4d (ej. 2822/1998)
    m = re.match(r'^(\d+)/(\d{4})$', ref)
    if m:
        return f"3{int(m.group(2))}R{int(m.group(1)):04d}"

    # 5. Fallback — extraer la última directiva CEE/CE/UE válida dentro del string
    #    Cubre casos como "89/173/CEE (IV) 94/20/CE" → toma "94/20/CE"
    matches = re.findall(r'\d{2,4}/\d+/(?:C(?:EE|E)|UE)\b', ref, re.I)
    if matches:
        return construir_celex(matches[-1])

    return None


# ─── Descarga y extracción ───────────────────────────────────────────────────

def _descargar_html(celex: str) -> str | None:
    """
    Descarga el contenido desde el endpoint CELLAR oficial (sin WAF de EUR-Lex).

    Directivas (L): disponibles como text/html.
    Reglamentos (R) y otros: pueden requerir application/xhtml+xml.
    Prueba ambos formatos antes de rendirse.
    """
    url = CELLAR_DOC.format(celex=celex)
    for accept in ("text/html", "application/xhtml+xml"):
        try:
            headers = {**HEADERS, "Accept": accept}
            resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            continue
    return None


def _extraer_contenido(html: str) -> tuple[str, str, bool]:
    """
    Extrae (título, texto_limpio, derogada) del HTML de EUR-Lex.

    Elimina navegación, scripts y elementos UI. Detecta si la norma
    está derogada buscando marcadores textuales estándar de EUR-Lex.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Eliminar elementos de interfaz
    for tag in soup.find_all(["script", "style", "nav", "header", "footer",
                               "button", "form", "aside", "noscript"]):
        tag.decompose()

    texto_raw = soup.get_text(separator="\n", strip=True)

    # Limpiar líneas repetidas y vacías
    lineas = [l.strip() for l in texto_raw.splitlines() if l.strip()]
    lineas_unicas: list[str] = []
    prev = None
    for l in lineas:
        if l != prev:
            lineas_unicas.append(l)
        prev = l
    texto = "\n".join(lineas_unicas)

    # Título: primera línea que empieza por "Directiva", "Reglamento", etc.
    # Para documentos del Diario Oficial (XHTML), el título puede estar fragmentado
    # en varias líneas cortas por superíndices (ej. "N" + "o" + "1322/2014").
    # Se unen las siguientes líneas hasta obtener al menos 60 chars de título.
    _PAT_TITULO = re.compile(
        r'^(?:Directiva|Reglamento|Decisión|Decision|Directive|Regulation)\b',
        re.IGNORECASE,
    )
    titulo = ""
    for i, linea in enumerate(lineas_unicas[:40]):
        if _PAT_TITULO.match(linea):
            partes = [linea]
            j = i + 1
            while len(" ".join(partes)) < 80 and j < min(i + 8, len(lineas_unicas)):
                siguiente = lineas_unicas[j]
                # Parar si llegamos a una línea claramente nueva (fecha, artículo, etc.)
                if re.match(r'^(?:LA COMISI|Visto|Considerando|Artículo|\(Texto)', siguiente, re.I):
                    break
                partes.append(siguiente)
                j += 1
            titulo = " ".join(partes).strip()
            # Limpiar artefacto "N o 1322" → "N.º 1322"
            titulo = re.sub(r'\bN\s+o\s+', 'N.º ', titulo)
            break

    # Detectar derogación — EUR-Lex incluye estas frases en los documentos no vigentes
    texto_lower = texto.lower()
    derogada = any(
        w in texto_lower
        for w in [
            "derogado", "derogada", "abrogado", "abrogada",
            "no está en vigor", "dejó de estar en vigor",
            "this act has been repealed", "no longer in force",
        ]
    )

    return titulo, texto, derogada


def _consultar_cellar(celex: str) -> dict:
    """
    Consulta CELLAR SPARQL para metadatos de vigencia y sustitución.
    Devuelve dict vacío si falla o si no hay datos.
    """
    query = f"""
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?date_end ?replacement WHERE {{
  ?work cdm:resource_legal_id_celex "{celex}" .
  OPTIONAL {{ ?work cdm:work_date_end_of_validity ?date_end }}
  OPTIONAL {{
    ?work cdm:resource_legal_is_replaced_by ?rep .
    ?rep  cdm:resource_legal_id_celex ?replacement .
  }}
}} LIMIT 1
"""
    try:
        resp = requests.post(
            CELLAR_SPARQL,
            data={"query": query, "format": "application/sparql-results+json"},
            headers={**HEADERS, "Accept": "application/sparql-results+json"},
            timeout=15,
        )
        if resp.status_code == 200:
            bindings = resp.json().get("results", {}).get("bindings", [])
            if bindings:
                b = bindings[0]
                return {
                    "fecha_fin_validez": b.get("date_end", {}).get("value"),
                    "sustituida_por":    b.get("replacement", {}).get("value"),
                }
    except Exception:
        pass
    return {}


# ─── Procesamiento ───────────────────────────────────────────────────────────

def _agrupar_por_celex(referencias: list[dict]) -> list[dict]:
    """
    Agrupa las entradas de normativas_ar.json por CELEX único.
    Múltiples referencias que apuntan al mismo documento (alias) se fusionan:
    - `referencias`: lista de todas las variantes de nombre
    - `secciones`, `fuentes`, `anexos`: unión de todos los alias

    Ejemplo: '89/173/CEE', '89/173/CEE (II)', '89/173/CEE III'
             → un solo grupo con CELEX 31989L0173
    """
    celex_map: dict[str, dict] = {}
    sin_celex: list[str] = []

    for entry in referencias:
        celex = construir_celex(entry["referencia"])
        if not celex:
            sin_celex.append(entry["referencia"])
            continue

        if celex not in celex_map:
            celex_map[celex] = {
                "celex":       celex,
                "referencias": [],
                "secciones":   set(),
                "fuentes":     set(),
                "anexos":      set(),
            }

        grupo = celex_map[celex]
        grupo["referencias"].append(entry["referencia"])
        grupo["secciones"].update(entry.get("secciones", []))
        grupo["fuentes"].update(entry.get("fuentes", []))
        grupo["anexos"].update(entry.get("anexos", []))

    if sin_celex:
        print(f"⚠ {len(sin_celex)} referencia(s) sin CELEX ignoradas: {sin_celex}")

    # Convertir sets a listas ordenadas
    grupos = []
    for g in celex_map.values():
        g["secciones"] = sorted(g["secciones"])
        g["fuentes"]   = sorted(g["fuentes"])
        g["anexos"]    = sorted(g["anexos"])
        grupos.append(g)

    return grupos


def procesar_grupo(grupo: dict, verbose: bool = True) -> dict | None:
    """
    Descarga y procesa un grupo de referencias que comparten el mismo CELEX.
    La referencia canónica es la primera de la lista (la más simple).
    """
    celex       = grupo["celex"]
    ref_canon   = grupo["referencias"][0]
    n_alias     = len(grupo["referencias"])
    alias_label = f" (+{n_alias-1} alias)" if n_alias > 1 else ""

    if verbose:
        print(f"  {ref_canon:35s} → {celex}{alias_label} ", end="", flush=True)

    html = _descargar_html(celex)
    if not html:
        if verbose:
            print("✗ (no descargado)")
        return None

    titulo, texto, derogada = _extraer_contenido(html)
    time.sleep(DELAY_S / 2)
    vigencia = _consultar_cellar(celex)

    if verbose:
        estado = "⚠ DEROGADA" if derogada else "✓"
        print(f"{estado} | {titulo[:50]}")

    return {
        "referencia":        ref_canon,
        "referencias_alias": grupo["referencias"],
        "celex":             celex,
        "titulo":            titulo,
        "fuentes":           grupo["fuentes"],
        "secciones":         grupo["secciones"],
        "anexos_citados":    grupo["anexos"],
        "derogada":          derogada,
        "fecha_fin_validez": vigencia.get("fecha_fin_validez"),
        "sustituida_por":    vigencia.get("sustituida_por"),
        "texto":             texto,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga directivas/reglamentos EU desde EUR-Lex"
    )
    parser.add_argument(
        "--ref", nargs="+", metavar="REF",
        help="Procesar solo estas referencias (ej. 70/222/CEE 2001/85/CE)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Ignora la caché y re-descarga todo",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Muestra CELEXs únicos sin hacer peticiones",
    )
    args = parser.parse_args()

    if not NORMATIVAS_PATH.exists():
        print(f"ERROR: {NORMATIVAS_PATH} no encontrado.")
        print("Ejecuta primero: python scripts_graph/build_graph.py --dry-run")
        return

    with open(NORMATIVAS_PATH, encoding="utf-8") as f:
        normativas = json.load(f)

    referencias = normativas["referencias"]

    if args.ref:
        refs_filtro = set(args.ref)
        referencias = [r for r in referencias if r["referencia"] in refs_filtro]
        if not referencias:
            print(f"No se encontraron las referencias: {args.ref}")
            return

    # Agrupar por CELEX único antes de cualquier descarga
    grupos = _agrupar_por_celex(referencias)

    # ── Dry-run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"{'Referencia canónica':35s} {'CELEX':15s} {'Alias'}")
        print("─" * 75)
        for g in grupos:
            alias = ", ".join(g["referencias"][1:]) if len(g["referencias"]) > 1 else "—"
            print(f"  {g['referencias'][0]:35s} {g['celex']:15s} {alias}")
        print(f"\nReferencias totales: {len(referencias)} → CELEXs únicos: {len(grupos)}")
        return

    # ── Caché por CELEX ───────────────────────────────────────────────────────
    existentes: dict[str, dict] = {}
    if not args.reset and OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            data_prev = json.load(f)
        existentes = {d["celex"]: d for d in data_prev.get("directivas", [])}
        if existentes:
            print(f"Caché: {len(existentes)} documentos ya descargados.")

    nuevos = [g for g in grupos if g["celex"] not in existentes]
    print(f"Referencias: {len(referencias)} → CELEXs únicos: {len(grupos)} → A descargar: {len(nuevos)}\n")

    directivas = list(existentes.values())
    errores: list[str] = []

    for i, grupo in enumerate(nuevos, 1):
        print(f"[{i:3d}/{len(nuevos)}] ", end="")
        doc = procesar_grupo(grupo)
        if doc:
            directivas.append(doc)
        else:
            errores.append(grupo["celex"])
        time.sleep(DELAY_S)

    # ── Guardar ───────────────────────────────────────────────────────────────
    output = {
        "generado":   datetime.now().isoformat(timespec="seconds"),
        "total":      len(directivas),
        "errores":    len(errores),
        "directivas": directivas,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*55}")
    print(f"Guardado : {OUTPUT_PATH}")
    print(f"Total    : {len(directivas)} documentos")
    print(f"Derogadas: {sum(1 for d in directivas if d.get('derogada'))}")
    print(f"Errores  : {len(errores)}")
    if errores:
        print(f"  Sin descarga: {errores}")


if __name__ == "__main__":
    main()

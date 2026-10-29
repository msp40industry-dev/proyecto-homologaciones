"""
ensamblador.py — Agente 5 (sin LLM)

Monta el documento Word final usando node + docx-js.
Ensambla todas las secciones aprobadas, inserta los adjuntos
y genera el .docx maquetado con portada, índice y paginación.
"""

from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

from proyecto_tecnico.models import (
    EntradaProyecto, FichaCR, ARFiltrado, SeccionGenerada
)

# Directorio donde se guardan los documentos generados
ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs" / "proyectos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def ensamblar_documento(
    proyecto_id: str,
    entrada: EntradaProyecto,
    secciones: dict[str, SeccionGenerada],
    crs: list[FichaCR],
    ars: list[ARFiltrado],
    adjuntos: dict | None = None,
    textos_manuales: dict | None = None,
    borrador: bool = True,
) -> str:
    """
    Genera el .docx y devuelve la ruta del fichero.
    Si `borrador` es True, añade la marca de agua diagonal «BORRADOR» en todas las páginas.
    """
    adjuntos = adjuntos or {}
    textos_manuales = textos_manuales or {}

    # Guardar bytes de adjuntos en ficheros temporales para que el JS pueda leerlos
    adjuntos_info: dict[str, dict] = {}
    temp_adjunto_files: list[str] = []
    _FORMATOS_IMAGEN = {".jpg", ".jpeg", ".png"}

    for k, v in adjuntos.items():
        if not (v.get("bytes") and v.get("nombre")):
            continue
        normalized = k.lstrip("_")
        suffix = Path(v["nombre"]).suffix.lower() or ".bin"
        with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as f:
            f.write(v["bytes"])
            temp_adjunto_files.append(f.name)
        adjuntos_info[normalized] = {
            "nombre": v["nombre"],
            "path": f.name,
            "es_imagen": suffix in _FORMATOS_IMAGEN,
        }

    # Construir el payload de datos para el script JS
    payload = _construir_payload(proyecto_id, entrada, secciones, crs, ars, adjuntos_info, textos_manuales)

    # Guardar payload en fichero temporal
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        payload_path = f.name

    output_path = str(OUTPUT_DIR / f"proyecto_{proyecto_id}.docx")

    script_path = None
    try:
        # Escribir y ejecutar el script JS generador
        script_path = _escribir_script_js()
        node_env = os.environ.copy()
        module_paths = [str(ROOT / "node_modules")]
        if node_env.get("NODE_PATH"):
            module_paths.append(node_env["NODE_PATH"])
        node_env["NODE_PATH"] = os.pathsep.join(module_paths)
        result = subprocess.run(
            ["node", script_path, payload_path, output_path],
            capture_output=True,
            text=True,
            timeout=60,
            env=node_env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Error en generación docx: {result.stderr}")
        if borrador:
            _aplicar_marca_agua(output_path, "BORRADOR")
    finally:
        os.unlink(payload_path)
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass
        for tmp in temp_adjunto_files:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    return output_path


# ── Marca de agua ─────────────────────────────────────────
# docx-js no soporta marcas de agua, así que se inyecta en cada cabecera el mismo
# objeto VML (WordArt rotado 315°) que crea Word en Diseño › Marca de agua.
# Al ser nativa, el ingeniero puede quitarla desde Word cuando el proyecto sea definitivo.

_SHAPETYPE_TEXTO_VML = (
    '<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" '
    'path="m@7,l@8,m@5,21600l@6,21600e">'
    '<v:formulas>'
    '<v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/>'
    '<v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/>'
    '<v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/>'
    '<v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/>'
    '<v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/>'
    '</v:formulas>'
    '<v:path textpathok="t" o:connecttype="custom" '
    'o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" o:connectangles="270,180,90,0"/>'
    '<v:textpath on="t" fitshape="t"/>'
    '<v:handles><v:h position="#0,bottomRight" xrange="6629,14971"/></v:handles>'
    '<o:lock v:ext="edit" text="t" shapetype="t"/>'
    '</v:shapetype>'
)


def _run_marca_agua(texto: str, indice: int) -> str:
    """Run WordprocessingML con la marca de agua diagonal centrada en la página."""
    return (
        '<w:r><w:rPr><w:noProof/></w:rPr><w:pict>'
        + _SHAPETYPE_TEXTO_VML
        + f'<v:shape id="PowerPlusWaterMarkObject{indice}" o:spid="_x0000_s{2048 + indice}" '
        'type="#_x0000_t136" '
        'style="position:absolute;margin-left:0;margin-top:0;width:468pt;height:117pt;'
        'rotation:315;z-index:-251654144;'
        'mso-position-horizontal:center;mso-position-horizontal-relative:margin;'
        'mso-position-vertical:center;mso-position-vertical-relative:margin" '
        'o:allowincell="f" fillcolor="#bfbfbf" stroked="f">'
        '<v:fill opacity=".5"/>'
        f'<v:textpath style="font-family:&quot;Arial&quot;;font-size:1pt" string={quoteattr(texto)}/>'
        '<w10:wrap anchorx="margin" anchory="margin"/>'
        '</v:shape></w:pict></w:r>'
    )


def _aplicar_marca_agua(docx_path: str, texto: str) -> None:
    """Inserta la marca de agua en todas las cabeceras (word/headerN.xml) del .docx."""
    patron_cabecera = re.compile(r"word/header\d+\.xml")
    with zipfile.ZipFile(docx_path) as zin:
        entradas = [(info, zin.read(info)) for info in zin.infolist()]

    tmp_path = docx_path + ".tmp"
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
        indice = 0
        for info, contenido in entradas:
            if patron_cabecera.fullmatch(info.filename):
                indice += 1
                xml = contenido.decode("utf-8")
                # El run se añade al final del primer párrafo de la cabecera
                # (un párrafo vacío se serializa como <w:p/>)
                run = _run_marca_agua(texto, indice)
                xml = re.sub(
                    r"<w:p/>|</w:p>",
                    lambda m: f"<w:p>{run}</w:p>" if m.group() == "<w:p/>" else run + "</w:p>",
                    xml, count=1,
                )
                contenido = xml.encode("utf-8")
            zout.writestr(info, contenido)
    os.replace(tmp_path, docx_path)


def _construir_payload(
    proyecto_id: str,
    entrada: EntradaProyecto,
    secciones: dict[str, SeccionGenerada],
    crs: list[FichaCR],
    ars: list[ARFiltrado],
    adjuntos: dict,
    textos_manuales: dict,
) -> dict:
    v = entrada.vehiculo
    ing = entrada.ingeniero

    return {
        "proyecto_id": proyecto_id,
        "metadata": {
            "titulo": f"Proyecto Técnico — Reforma de Vehículo",
            "vehiculo": f"{v.marca} {v.modelo}",
            "bastidor": v.bastidor,
            "matricula": v.matricula,
            "categoria": v.categoria,
            "fecha_matriculacion": v.fecha_matriculacion,
            "color": v.color or "",
            "kilometraje": v.kilometraje or "",
            "ingeniero": f"{ing.nombre} {ing.apellidos}",
            "colegiado": ing.numero_colegiado,
            "colegio": ing.colegio_profesional,
            "fecha": entrada.fecha_proyecto or "",
            "expediente": entrada.numero_expediente or "",
        },
        "crs": [
            {"codigo": cr.codigo, "denominacion": cr.denominacion, "via": cr.via}
            for cr in crs
        ],
        "ars": [
            {
                "sistema": ar.sistema,
                "referencia": ar.referencia,
                "nivel": ar.nivel_exigencia,
                "descripcion": ar.descripcion_nivel,
                "cr": ar.codigo_cr,
            }
            for ar in ars
        ],
        # Secciones en orden de aparición en el documento
        "secciones": [
            {
                "id": sid,
                "titulo": secciones[sid].titulo,
                "contenido": secciones[sid].contenido,
                "tiene_adjunto": bool(secciones[sid].adjunto_bytes),
                "adjunto_nombre": secciones[sid].adjunto_nombre or "",
            }
            for sid in _ORDEN_SECCIONES
            if sid in secciones
        ],
        # Secciones que el ingeniero debe completar (marcadores)
        "secciones_completar": [
            {"id": sid, "titulo": titulo}
            for sid, titulo in _SECCIONES_INGENIERO.items()
        ],
        # Adjuntos subidos por el ingeniero: clave normalizada → {nombre, path, es_imagen}
        "adjuntos": adjuntos,
        # Textos escritos manualmente por el ingeniero (1.3.2 y 1.3.3)
        "textos_manuales": {
            "caracteristicas_antes":   textos_manuales.get("caracteristicas_antes", ""),
            "caracteristicas_despues": textos_manuales.get("caracteristicas_despues", ""),
        },
    }


# Orden canónico de las secciones en el documento
_ORDEN_SECCIONES = [
    "peticionario",
    "objeto",
    "antecedentes",
    "identificacion_vehiculo",
    "descripcion_reforma",
    # Sección 2 (cálculos) la pone el ingeniero
    "calidad_materiales",
    "normas_ejecucion",
    "certificados",
    "taller_ejecutor",
    # Secciones 4-7 las pone el ingeniero
    "conclusiones",
]

_SECCIONES_INGENIERO = {
    "caracteristicas_antes":  "1.3.2 Características del vehículo antes de la reforma",
    "caracteristicas_despues": "1.3.3 Características del vehículo después de la reforma",
    "calculos":               "2. Cálculos justificativos",
    "presupuesto":            "4. Presupuesto",
    "planos":                 "5. Planos",
    "fotografias":            "6. Reportaje fotográfico",
    "documentacion":          "7. Documentación del vehículo",
}


def _escribir_script_js() -> str:
    """Escribe el script Node.js generador de docx y devuelve su ruta."""
    script = r"""
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, NumberFormat, LevelFormat,
  TableOfContents,
} = require('docx');

const payloadPath = process.argv[2];
const outputPath  = process.argv[3];
const data = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

// ── Colores ───────────────────────────────────────────────
const AZUL     = "1F4E79";
const AZUL_MED = "2E75B6";
const GRIS     = "F2F2F2";
const NEGRO    = "000000";

// ── Estilos de celda de tabla ─────────────────────────────
const borderGris = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const cellBorders = {
  top: borderGris, bottom: borderGris,
  left: borderGris, right: borderGris,
};
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

// ── Helpers ───────────────────────────────────────────────

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, color: AZUL, bold: true })],
    spacing: { before: 400, after: 200 },
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, color: AZUL_MED, bold: true })],
    spacing: { before: 300, after: 160 },
  });
}

function parrafo(text, opts = {}) {
  const lineas = text.split('\n').filter(l => l.trim() !== '');
  return lineas.map(linea =>
    new Paragraph({
      children: [new TextRun({
        text: linea,
        size: 22,
        font: "Arial",
        color: NEGRO,
        ...opts,
      })],
      spacing: { after: 120 },
      alignment: AlignmentType.JUSTIFIED,
    })
  );
}

// Parsea fragmentos de texto con **negrita** inline
function parseBold(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/);
  return parts.filter(p => p !== '').map(part => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return new TextRun({ text: part.slice(2, -2), bold: true, size: 22, font: "Arial", color: NEGRO });
    }
    return new TextRun({ text: part, size: 22, font: "Arial", color: NEGRO });
  });
}

// Renderiza contenido generado por el LLM con soporte de:
//   ## Título nivel 2      → heading2
//   ### a ###### Subtítulo → negrita azul, tamaño 22, sin entrada en el índice
//   - item / * item / • item → lista con viñetas
//   1. item                → párrafo con sangría y número
//   **texto**              → negrita inline
//   resto                  → párrafo justificado normal
function renderContenido(text) {
  const lineas = text.split('\n');
  const bloques = [];

  for (const linea of lineas) {
    const t = linea.trim();
    if (!t) {
      bloques.push(new Paragraph({ spacing: { after: 60 } }));
      continue;
    }

    // ## Título (heading 2)
    if (t.startsWith('## ')) {
      bloques.push(heading2(t.slice(3).trim()));
    }
    // Subtítulos Markdown de niveles 3 a 6 (sin outline)
    else if (/^#{3,6}\s+/.test(t)) {
      bloques.push(new Paragraph({
        children: [new TextRun({ text: t.replace(/^#{3,6}\s+/, '').trim(), bold: true, size: 22, font: "Arial", color: AZUL_MED })],
        spacing: { before: 160, after: 80 },
      }));
    }
    // Línea completa en negrita como subtítulo (ej. **Documentación exigible:**)
    else if (/^\*\*[^*]+\*\*:?$/.test(t)) {
      bloques.push(new Paragraph({
        children: [new TextRun({ text: t.replace(/\*\*/g, '').replace(/:$/, ':'), bold: true, size: 22, font: "Arial", color: AZUL_MED })],
        spacing: { before: 160, after: 80 },
      }));
    }
    // Lista con viñetas (- / * / •)
    else if (/^[-*•]\s/.test(t)) {
      const contenido = t.replace(/^[-*•]\s+/, '');
      bloques.push(new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: parseBold(contenido),
        spacing: { after: 80 },
      }));
    }
    // Lista numerada (1. 2. …)
    else if (/^\d+\.\s/.test(t)) {
      const num = t.match(/^(\d+\.)/)[1];
      const contenido = t.replace(/^\d+\.\s+/, '');
      bloques.push(new Paragraph({
        children: [
          new TextRun({ text: num + ' ', bold: true, size: 22, font: "Arial", color: NEGRO }),
          ...parseBold(contenido),
        ],
        spacing: { after: 80 },
        indent: { left: 360 },
      }));
    }
    // Párrafo normal
    else {
      bloques.push(new Paragraph({
        children: parseBold(t),
        spacing: { after: 120 },
        alignment: AlignmentType.JUSTIFIED,
      }));
    }
  }

  return bloques;
}

function marcadorCompletar(titulo) {
  return new Paragraph({
    children: [
      new TextRun({
        text: `[ ${titulo.toUpperCase()} — COMPLETAR POR EL INGENIERO ]`,
        size: 22,
        font: "Arial",
        color: "C00000",
        italics: true,
        bold: true,
      })
    ],
    spacing: { before: 200, after: 200 },
    border: {
      top:    { style: BorderStyle.DASHED, size: 6, color: "C00000" },
      bottom: { style: BorderStyle.DASHED, size: 6, color: "C00000" },
      left:   { style: BorderStyle.DASHED, size: 6, color: "C00000" },
      right:  { style: BorderStyle.DASHED, size: 6, color: "C00000" },
    },
  });
}

function seccionIngenieroBloque(id, titulo, adjuntos) {
  const adj = adjuntos[id];
  if (!adj) return marcadorCompletar(titulo);

  if (adj.es_imagen) {
    const imgData = fs.readFileSync(adj.path);
    return new Paragraph({
      children: [
        new ImageRun({
          data: imgData,
          transformation: { width: 500, height: 350 },
        }),
      ],
      spacing: { before: 160, after: 200 },
    });
  }

  // Para PDF, DWG, XLSX u otros: indicador de fichero adjunto
  return new Paragraph({
    children: [
      new TextRun({ text: "📎 Adjunto: ", bold: true, size: 22, font: "Arial", color: "2E75B6" }),
      new TextRun({ text: adj.nombre, size: 22, font: "Arial", color: "2E75B6" }),
    ],
    spacing: { before: 160, after: 200 },
  });
}

function tablaARs(ars) {
  const anchoTotal = 9026;
  const cols = [1800, 2000, 800, 4426];

  const headerRow = new TableRow({
    tableHeader: true,
    children: ["Sistema", "Referencia", "Nivel", "Descripción"].map((texto, i) =>
      new TableCell({
        borders: cellBorders,
        width: { size: cols[i], type: WidthType.DXA },
        margins: cellMargins,
        shading: { fill: AZUL_MED, type: ShadingType.CLEAR },
        verticalAlign: VerticalAlign.CENTER,
        children: [new Paragraph({
          children: [new TextRun({ text: texto, bold: true, color: "FFFFFF", size: 20, font: "Arial" })],
          alignment: AlignmentType.CENTER,
        })],
      })
    ),
  });

  const dataRows = ars.map(ar =>
    new TableRow({
      children: [ar.sistema, ar.referencia, ar.nivel, ar.descripcion].map((texto, i) =>
        new TableCell({
          borders: cellBorders,
          width: { size: cols[i], type: WidthType.DXA },
          margins: cellMargins,
          shading: { fill: i % 2 === 0 ? GRIS : "FFFFFF", type: ShadingType.CLEAR },
          children: [new Paragraph({
            children: [new TextRun({ text: texto || "", size: 18, font: "Arial" })],
          })],
        })
      ),
    })
  );

  return new Table({
    width: { size: anchoTotal, type: WidthType.DXA },
    columnWidths: cols,
    rows: [headerRow, ...dataRows],
  });
}

function tablaVehiculo(m) {
  const filas = [
    ["Marca",                    m.vehiculo.split(' ')[0] || m.vehiculo],
    ["Modelo",                   m.vehiculo.split(' ').slice(1).join(' ') || "—"],
    ["Número de bastidor (VIN)", m.bastidor],
    ["Matrícula",                m.matricula],
    ["Categoría",                m.categoria],
    ["Fecha de matriculación",   m.fecha_matriculacion || "—"],
    ["Color",                    m.color || "[COMPLETAR]"],
    ["Kilometraje",              m.kilometraje || "[COMPLETAR]"],
  ];
  const anchoTotal = 9026;
  const cols = [3600, 5426];

  const headerRow = new TableRow({
    tableHeader: true,
    children: ["Campo", "Valor"].map((texto, i) =>
      new TableCell({
        borders: cellBorders,
        width: { size: cols[i], type: WidthType.DXA },
        margins: cellMargins,
        shading: { fill: AZUL, type: ShadingType.CLEAR },
        children: [new Paragraph({
          children: [new TextRun({ text: texto, bold: true, color: "FFFFFF", size: 20, font: "Arial" })],
        })],
      })
    ),
  });

  const dataRows = filas.map(([campo, valor], idx) =>
    new TableRow({
      children: [campo, valor].map((texto, i) =>
        new TableCell({
          borders: cellBorders,
          width: { size: cols[i], type: WidthType.DXA },
          margins: cellMargins,
          shading: { fill: idx % 2 === 0 ? GRIS : "FFFFFF", type: ShadingType.CLEAR },
          children: [new Paragraph({
            children: [new TextRun({ text: texto || "", size: 20, font: "Arial", bold: i === 0 })],
          })],
        })
      ),
    })
  );

  return new Table({
    width: { size: anchoTotal, type: WidthType.DXA },
    columnWidths: cols,
    rows: [headerRow, ...dataRows],
  });
}

function tablaCRs(crs) {
  const anchoTotal = 9026;
  const cols = [900, 5126, 3000];

  const headerRow = new TableRow({
    tableHeader: true,
    children: ["CR", "Denominación", "Vía"].map((texto, i) =>
      new TableCell({
        borders: cellBorders,
        width: { size: cols[i], type: WidthType.DXA },
        margins: cellMargins,
        shading: { fill: AZUL, type: ShadingType.CLEAR },
        children: [new Paragraph({
          children: [new TextRun({ text: texto, bold: true, color: "FFFFFF", size: 20, font: "Arial" })],
        })],
      })
    ),
  });

  const dataRows = crs.map(cr =>
    new TableRow({
      children: [cr.codigo, cr.denominacion, `Vía ${cr.via}`].map((texto, i) =>
        new TableCell({
          borders: cellBorders,
          width: { size: cols[i], type: WidthType.DXA },
          margins: cellMargins,
          shading: { fill: GRIS, type: ShadingType.CLEAR },
          children: [new Paragraph({
            children: [new TextRun({ text: texto || "", size: 20, font: "Arial" })],
          })],
        })
      ),
    })
  );

  return new Table({
    width: { size: anchoTotal, type: WidthType.DXA },
    columnWidths: cols,
    rows: [headerRow, ...dataRows],
  });
}

// ── Portada ───────────────────────────────────────────────

function construirPortada(data) {
  const m = data.metadata;
  return [
    new Paragraph({ spacing: { before: 1440 } }),
    new Paragraph({
      children: [new TextRun({
        text: "PROYECTO TÉCNICO",
        size: 52, bold: true, color: AZUL, font: "Arial",
      })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
    }),
    new Paragraph({
      children: [new TextRun({
        text: "REFORMA DE VEHÍCULO — VÍA A",
        size: 32, color: AZUL_MED, font: "Arial",
      })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 800 },
    }),
    new Paragraph({
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: AZUL_MED, space: 1 } },
      spacing: { after: 400 },
    }),
    ...[ 
      ["Vehículo:",    `${m.vehiculo}`],
      ["Bastidor:",    m.bastidor],
      ["Matrícula:",   m.matricula],
      ["Categoría:",   m.categoria],
      ["CRs:",         data.crs.map(cr => `CR ${cr.codigo}`).join(", ") || "—"],
      ["Ingeniero:",   m.ingeniero],
      ["Nº Colegiado:", m.colegiado],
      ["Colegio:",     m.colegio],
      ["Expediente:",  m.expediente || "—"],
      ["Fecha:",       m.fecha || "—"],
    ].map(([label, value]) =>
      new Paragraph({
        children: [
          new TextRun({ text: `${label} `, bold: true, size: 24, font: "Arial", color: AZUL }),
          new TextRun({ text: value, size: 24, font: "Arial", color: NEGRO }),
        ],
        spacing: { after: 140 },
      })
    ),
  ];
}

// ── Secciones del documento ───────────────────────────────

// El título principal ya se inserta desde sec.titulo. Quitar solo su repetición inicial.
function sinTituloInicialDuplicado(contenido, titulo) {
  const normalizar = texto => texto.trim()
    .replace(/^#{1,6}\s+/, '')
    .replace(/\*\*/g, '')
    .replace(/\s+#+\s*$/, '')
    .replace(/:\s*$/, '')
    .replace(/\s+/g, ' ')
    .trim().toLocaleLowerCase('es');
  const lineas = contenido.split('\n');
  const primero = lineas.findIndex(linea => linea.trim() !== '');
  if (primero !== -1 && normalizar(lineas[primero]) === normalizar(titulo)) {
    return lineas.slice(primero + 1).join('\n').replace(/^\s*\n/, '');
  }
  return contenido;
}

function construirSecciones(data) {
  const bloques = [];

  for (const sec of data.secciones) {
    const contenido = sinTituloInicialDuplicado(sec.contenido, sec.titulo);
    // Determinar nivel de heading
    if (/^\d+\./.test(sec.titulo) && !sec.titulo.match(/^\d+\.\d+/)) {
      bloques.push(heading1(sec.titulo));
    } else {
      bloques.push(heading2(sec.titulo));
    }

    // Para "antecedentes" insertamos también las tablas de CRs y ARs
    if (sec.id === "antecedentes") {
      bloques.push(...renderContenido(contenido));
      if (data.crs.length > 0) {
        bloques.push(
          new Paragraph({ children: [new TextRun({ text: "Códigos de Reforma aplicables:", bold: true, size: 22, font: "Arial" })], spacing: { before: 200, after: 120 } }),
          tablaCRs(data.crs),
          new Paragraph({ spacing: { after: 200 } }),
          new Paragraph({ children: [new TextRun({ text: "Actos Reglamentarios aplicables:", bold: true, size: 22, font: "Arial" })], spacing: { before: 200, after: 120 } }),
          tablaARs(data.ars),
          new Paragraph({ spacing: { after: 200 } }),
        );
      }
    } else if (sec.id === "identificacion_vehiculo") {
      // Texto introductorio + tabla de datos del vehículo
      bloques.push(...renderContenido(contenido));
      bloques.push(
        new Paragraph({ spacing: { after: 120 } }),
        tablaVehiculo(data.metadata),
        new Paragraph({ spacing: { after: 200 } }),
      );
    } else {
      bloques.push(...renderContenido(contenido));
    }

    // Indicador de adjunto
    if (sec.tiene_adjunto) {
      bloques.push(
        new Paragraph({
          children: [new TextRun({
            text: `📎 Adjunto: ${sec.adjunto_nombre}`,
            size: 20, italics: true, color: "595959", font: "Arial",
          })],
          spacing: { before: 160, after: 200 },
        })
      );
    }

    bloques.push(new Paragraph({ spacing: { after: 160 } }));

    // Insertar secciones del ingeniero en los puntos correctos
    if (sec.id === "identificacion_vehiculo") {
      const textoAntes   = (data.textos_manuales && data.textos_manuales.caracteristicas_antes   || "").trim();
      const textoDespues = (data.textos_manuales && data.textos_manuales.caracteristicas_despues || "").trim();

      bloques.push(heading2("1.3.2 Características del vehículo antes de la reforma"));
      if (textoAntes) {
        bloques.push(...renderContenido(textoAntes));
      } else {
        bloques.push(marcadorCompletar("1.3.2 Características antes de la reforma"));
      }

      bloques.push(heading2("1.3.3 Características del vehículo después de la reforma"));
      if (textoDespues) {
        bloques.push(...renderContenido(textoDespues));
      } else {
        bloques.push(marcadorCompletar("1.3.3 Características después de la reforma"));
      }
    }

    if (sec.id === "descripcion_reforma") {
      bloques.push(heading1("2. Cálculos justificativos"));
      bloques.push(seccionIngenieroBloque("calculos", "2. Cálculos justificativos", data.adjuntos));
    }

    if (sec.id === "taller_ejecutor") {
      bloques.push(heading1("4. Presupuesto"));
      bloques.push(seccionIngenieroBloque("presupuesto", "4. Presupuesto", data.adjuntos));
      bloques.push(heading1("5. Planos"));
      bloques.push(seccionIngenieroBloque("planos", "5. Planos", data.adjuntos));
      bloques.push(heading1("6. Reportaje fotográfico"));
      bloques.push(seccionIngenieroBloque("fotografias", "6. Reportaje fotográfico", data.adjuntos));
      bloques.push(heading1("7. Documentación del vehículo"));
      bloques.push(seccionIngenieroBloque("documentacion", "7. Documentación del vehículo", data.adjuntos));
    }
  }

  return bloques;
}

// ── Header y Footer ───────────────────────────────────────

function construirHeader(data) {
  return {
    default: new Header({
      children: [
        new Paragraph({
          children: [
            new TextRun({ text: "PROYECTO TÉCNICO — REFORMA DE VEHÍCULO", size: 18, font: "Arial", color: AZUL_MED, bold: true }),
            new TextRun({ text: `    ${data.metadata.vehiculo} | ${data.metadata.bastidor}`, size: 18, font: "Arial", color: "595959" }),
          ],
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: AZUL_MED, space: 1 } },
        }),
      ],
    }),
  };
}

function construirFooter(data) {
  return {
    default: new Footer({
      children: [
        new Paragraph({
          children: [
            new TextRun({ text: `${data.metadata.ingeniero} — Colegiado Nº ${data.metadata.colegiado}    `, size: 18, font: "Arial", color: "595959" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, font: "Arial", color: "595959" }),
            new TextRun({ text: " / ", size: 18, font: "Arial", color: "595959" }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, font: "Arial", color: "595959" }),
          ],
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: AZUL_MED, space: 1 } },
          alignment: AlignmentType.RIGHT,
        }),
      ],
    }),
  };
}

// ── Documento principal ───────────────────────────────────

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: "Arial", size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: AZUL },
        paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: AZUL_MED },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },
  sections: [
    // Sección 1: Portada (cabecera vacía: solo soporta la marca de agua de borrador)
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1800 },
        },
      },
      headers: { default: new Header({ children: [new Paragraph({})] }) },
      children: construirPortada(data),
    },
    // Sección 2: Índice + contenido
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1800 },
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL },
        },
      },
      headers: construirHeader(data),
      footers: construirFooter(data),
      children: [
        heading1("Índice"),
        new TableOfContents("Índice", {
          hyperlink: true,
          headingStyleRange: "1-2",
        }),
        new Paragraph({ pageBreakBefore: true }),
        ...construirSecciones(data),
      ],
    },
  ],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log(`Documento generado: ${outputPath}`);
}).catch(err => {
  console.error(err);
  process.exit(1);
});
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", prefix="generar_proyecto_tecnico_",
        delete=False, encoding="utf-8",
    ) as f:
        f.write(script)
        script_path = f.name
    return script_path

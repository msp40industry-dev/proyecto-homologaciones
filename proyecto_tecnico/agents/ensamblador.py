"""
ensamblador.py — Agente 5 (sin LLM)

Monta el documento Word final usando node + docx-js.
Ensambla todas las secciones aprobadas, inserta los adjuntos
y genera el .docx maquetado con portada, índice y paginación.
"""

from __future__ import annotations
import json
import os
import subprocess
import tempfile
from pathlib import Path

from proyecto_tecnico.models import (
    EntradaProyecto, FichaCR, ARFiltrado, SeccionGenerada
)

# Directorio donde se guardan los documentos generados
OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "proyectos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def ensamblar_documento(
    proyecto_id: str,
    entrada: EntradaProyecto,
    secciones: dict[str, SeccionGenerada],
    crs: list[FichaCR],
    ars: list[ARFiltrado],
    adjuntos: dict | None = None,
) -> str:
    """
    Genera el .docx y devuelve la ruta del fichero.
    """
    # Construir el payload de datos para el script JS
    payload = _construir_payload(proyecto_id, entrada, secciones, crs, ars, adjuntos or {})

    # Guardar payload en fichero temporal
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        payload_path = f.name

    output_path = str(OUTPUT_DIR / f"proyecto_{proyecto_id}.docx")

    try:
        # Escribir y ejecutar el script JS generador
        script_path = _escribir_script_js()
        result = subprocess.run(
            ["node", script_path, payload_path, output_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Error en generación docx: {result.stderr}")
    finally:
        os.unlink(payload_path)

    return output_path


def _construir_payload(
    proyecto_id: str,
    entrada: EntradaProyecto,
    secciones: dict[str, SeccionGenerada],
    crs: list[FichaCR],
    ars: list[ARFiltrado],
    adjuntos: dict,
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
        # Adjuntos subidos por el ingeniero: clave normalizada → nombre del fichero
        "adjuntos": {
            k.lstrip("_"): v["nombre"]
            for k, v in adjuntos.items()
            if v.get("nombre")
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
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
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
        size: 22, // 11pt
        font: "Arial",
        color: NEGRO,
        ...opts,
      })],
      spacing: { after: 120 },
      alignment: AlignmentType.JUSTIFIED,
    })
  );
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
  const nombre = adjuntos[id];
  if (nombre) {
    return new Paragraph({
      children: [
        new TextRun({ text: "📎 Adjunto: ", bold: true, size: 22, font: "Arial", color: "2E75B6" }),
        new TextRun({ text: nombre, size: 22, font: "Arial", color: "2E75B6" }),
      ],
      spacing: { before: 160, after: 200 },
    });
  }
  return marcadorCompletar(titulo);
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

function construirSecciones(data) {
  const bloques = [];

  for (const sec of data.secciones) {
    // Determinar nivel de heading
    if (/^\d+\./.test(sec.titulo) && !sec.titulo.match(/^\d+\.\d+/)) {
      bloques.push(heading1(sec.titulo));
    } else {
      bloques.push(heading2(sec.titulo));
    }

    // Para "antecedentes" insertamos también las tablas de CRs y ARs
    if (sec.id === "antecedentes") {
      bloques.push(...parrafo(sec.contenido));
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
      bloques.push(...parrafo(sec.contenido));
      bloques.push(
        new Paragraph({ spacing: { after: 120 } }),
        tablaVehiculo(data.metadata),
        new Paragraph({ spacing: { after: 200 } }),
      );
    } else {
      bloques.push(...parrafo(sec.contenido));
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
      bloques.push(heading2("1.3.2 Características del vehículo antes de la reforma"));
      bloques.push(marcadorCompletar("1.3.2 Características antes de la reforma"));
      bloques.push(heading2("1.3.3 Características del vehículo después de la reforma"));
      bloques.push(marcadorCompletar("1.3.3 Características después de la reforma"));
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
    // Sección 1: Portada (sin header/footer)
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1800 },
        },
      },
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
    script_path = "/tmp/generar_proyecto_tecnico.js"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    return script_path

"""
visualize_cr_ar.py — Grafo 3D bipartito: Fichas CR ↔ Directivas AR.

Lee los dos JSONs de fichas, extrae las relaciones CR→AR y genera un HTML
interactivo standalone usando la librería 3d-force-graph (Three.js).

Uso:
    python scripts_graph/visualize_cr_ar.py                 # todas las secciones
    python scripts_graph/visualize_cr_ar.py --seccion I     # solo sección I
    python scripts_graph/visualize_cr_ar.py --seccion II    # solo sección II
    python scripts_graph/visualize_cr_ar.py --no-browser    # no abrir automáticamente
    python scripts_graph/visualize_cr_ar.py --output path/to/out.html
"""

import argparse
import json
import webbrowser
from pathlib import Path

ROOT        = Path(__file__).resolve().parents[1]
JSON_SEC1   = ROOT / "json" / "fichas_cr_seccion1_v3.json"
JSON_SEC24  = ROOT / "json" / "fichas_cr_secciones_ii_iii_iv.json"
OUTPUT_HTML = Path(__file__).resolve().parent / "graph_cr_ar.html"

# ─── Colores sección ──────────────────────────────────────────────────────────

COLOR_SECCION = {
    "I":   "#e74c3c",   # rojo
    "II":  "#3498db",   # azul
    "III": "#27ae60",   # verde
    "IV":  "#f39c12",   # naranja
}
SEC_Y_BIAS = {"I": 300, "II": 100, "III": -100, "IV": -300}

# ─── Clasificación de normativas AR ──────────────────────────────────────────

def _ar_tipo(ref: str) -> str:
    r = ref.upper().strip().replace(" ", "")
    if not r or r.startswith("--") or r in ("", "(*)"):
        return "otro"
    if "CEPE" in r or "ONU" in r or "UNECE" in r:
        return "cepe_onu"
    if r.endswith("/CEE") or "/CEE" in r:
        return "dir_cee"
    if r.endswith("/CE") or "/CE" in r or ("DIRECTIVA" in r and "CE" in r):
        return "dir_ce"
    if "(UE)" in r or "R(UE)" in r or "/UE" in r:
        return "reg_ue"
    if "(CE)" in r or "R(CE)" in r or "REGLAMENTO" in r:
        return "reg_ce"
    return "otro"

AR_TIPO_COLOR = {
    "dir_cee":  "#9b59b6",
    "dir_ce":   "#1abc9c",
    "reg_ue":   "#e67e22",
    "reg_ce":   "#e74c3c",
    "cepe_onu": "#2ecc71",
    "otro":     "#7f8c8d",
}
AR_TIPO_LABEL = {
    "dir_cee":  "Directiva …/CEE",
    "dir_ce":   "Directiva …/CE",
    "reg_ue":   "Reglamento (UE)",
    "reg_ce":   "Reglamento (CE)",
    "cepe_onu": "Reglamento CEPE/ONU",
    "otro":     "Otras referencias",
}
AR_TIPO_Y = {
    "dir_cee":   300,
    "dir_ce":    180,
    "reg_ce":     60,
    "reg_ue":    -60,
    "cepe_onu": -180,
    "otro":     -300,
}

# ─── Carga de datos ───────────────────────────────────────────────────────────

def _cargar_fichas() -> list[dict]:
    fichas = []
    for path in (JSON_SEC1, JSON_SEC24):
        if not path.exists():
            print(f"⚠  No encontrado: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        batch = data if isinstance(data, list) else data.get("fichas", [])
        fichas.extend(batch)
    return fichas


def _construir_grafo(fichas: list[dict], seccion_filtro: str | None) -> dict:
    nodes: list[dict] = []
    links: list[dict] = []
    seen_cr: set[str] = set()
    ar_map: dict[str, dict] = {}   # ar_id → node dict
    ar_cr_count: dict[str, int] = {}

    for ficha in fichas:
        sec = (ficha.get("seccion") or "").upper()
        if seccion_filtro and sec != seccion_filtro.upper():
            continue

        codigo    = ficha.get("cr", "?")
        cr_id     = f"CR-{sec}-{codigo}"
        via       = ficha.get("via_tramitacion", "?")
        desc      = (ficha.get("descripcion_cr") or ficha.get("descripcion_grupo") or "").strip()
        categorias = ficha.get("categorias_aplicables", [])
        ars        = ficha.get("actos_reglamentarios", [])

        if cr_id not in seen_cr:
            seen_cr.add(cr_id)
            nodes.append({
                "id":        cr_id,
                "group":     "cr",
                "label":     cr_id,
                "seccion":   sec,
                "via":       via,
                "desc":      desc[:200],
                "categorias": categorias,
                "n_ars":     len(ars),
                "color":     COLOR_SECCION.get(sec, "#bdc3c7"),
                "y_bias":    SEC_Y_BIAS.get(sec, 0),
            })

        for ar in ars:
            ref     = (ar.get("referencia") or "").strip()
            sistema = (ar.get("sistema") or "").strip()
            if not ref or ref.startswith("--"):
                continue

            ar_id = f"AR-{ref}"
            tipo  = _ar_tipo(ref)

            if ar_id not in ar_map:
                ar_map[ar_id] = {
                    "id":        ar_id,
                    "group":     "ar",
                    "label":     ref,
                    "ref":       ref,
                    "sistema":   sistema,
                    "tipo":      tipo,
                    "tipo_label": AR_TIPO_LABEL[tipo],
                    "n_crs":     0,
                    "color":     AR_TIPO_COLOR[tipo],
                    "y_bias":    AR_TIPO_Y[tipo],
                }
                ar_cr_count[ar_id] = 0

            ar_cr_count[ar_id] += 1
            ar_map[ar_id]["n_crs"] = ar_cr_count[ar_id]

            # Construir resumen de aplicabilidad por categoría
            aplic = ar.get("aplicabilidad", {})
            aplic_str = ", ".join(
                f"{cat}:{v}" for cat, v in aplic.items() if v not in ("-", "")
            )

            links.append({
                "source":      cr_id,
                "target":      ar_id,
                "seccion":     sec,
                "aplic":       aplic_str,
                "color":       COLOR_SECCION.get(sec, "#bdc3c7"),
            })

    nodes.extend(ar_map.values())
    return {"nodes": nodes, "links": links}


# ─── Estadísticas para el panel ──────────────────────────────────────────────

def _stats(data: dict) -> dict:
    n_cr = sum(1 for n in data["nodes"] if n["group"] == "cr")
    n_ar = sum(1 for n in data["nodes"] if n["group"] == "ar")
    secciones = sorted({n["seccion"] for n in data["nodes"] if n["group"] == "cr"})
    return {
        "n_cr":     n_cr,
        "n_ar":     n_ar,
        "n_edges":  len(data["links"]),
        "secciones": secciones,
    }


# ─── Plantilla HTML ──────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Grafo 3D: Fichas CR ↔ Directivas AR</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; overflow: hidden; }
    #graph { width: 100vw; height: 100vh; }

    /* ── Panel lateral izquierdo ── */
    #sidebar {
      position: fixed; top: 0; left: 0; width: 260px; height: 100vh;
      background: rgba(13,17,23,0.92); border-right: 1px solid #30363d;
      display: flex; flex-direction: column; padding: 16px; gap: 12px;
      overflow-y: auto; z-index: 100; backdrop-filter: blur(6px);
    }
    #sidebar h1 { font-size: 14px; font-weight: 700; color: #58a6ff; line-height: 1.3; }
    #sidebar .subtitle { font-size: 11px; color: #8b949e; }

    .stats-row { display: flex; gap: 8px; flex-wrap: wrap; }
    .stat-chip {
      background: #161b22; border: 1px solid #30363d; border-radius: 20px;
      padding: 3px 10px; font-size: 11px; color: #c9d1d9;
    }
    .stat-chip span { font-weight: 700; color: #58a6ff; }

    .legend-section { display: flex; flex-direction: column; gap: 5px; }
    .legend-title { font-size: 11px; font-weight: 600; color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }
    .legend-item { display: flex; align-items: center; gap: 7px; font-size: 12px; color: #c9d1d9; }
    .legend-dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }
    .legend-square { width: 11px; height: 11px; border-radius: 2px; flex-shrink: 0; }

    .control-group { display: flex; flex-direction: column; gap: 6px; }
    .control-label { font-size: 11px; color: #8b949e; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    select, button {
      background: #161b22; border: 1px solid #30363d; color: #c9d1d9;
      border-radius: 6px; padding: 5px 8px; font-size: 12px; cursor: pointer; width: 100%;
    }
    select:hover, button:hover { border-color: #58a6ff; color: #58a6ff; }
    button:active { background: #1f2937; }

    hr.divider { border: none; border-top: 1px solid #21262d; }

    /* ── Panel de detalle (click) ── */
    #detail-panel {
      position: fixed; top: 16px; right: 16px; width: 300px;
      background: rgba(13,17,23,0.95); border: 1px solid #30363d; border-radius: 10px;
      padding: 16px; z-index: 200; display: none; backdrop-filter: blur(8px);
      max-height: 80vh; overflow-y: auto;
    }
    #detail-panel .close-btn {
      position: absolute; top: 10px; right: 12px;
      background: none; border: none; color: #8b949e; font-size: 16px;
      cursor: pointer; width: auto; padding: 0;
    }
    #detail-panel .close-btn:hover { color: #e6edf3; border-color: transparent; }
    #detail-title { font-size: 15px; font-weight: 700; color: #58a6ff; margin-bottom: 8px; padding-right: 20px; }
    #detail-content { font-size: 12px; line-height: 1.6; color: #c9d1d9; }
    #detail-content .badge {
      display: inline-block; border-radius: 4px; padding: 2px 7px;
      font-size: 11px; font-weight: 600; margin: 2px 2px 4px 0;
    }
    #detail-content .field { margin-bottom: 6px; }
    #detail-content .field strong { color: #e6edf3; }
    #detail-content .aplic-list { font-size: 11px; color: #8b949e; margin-top: 4px; }

    /* ── Tooltip hover ── */
    #tooltip {
      position: fixed; pointer-events: none; z-index: 300;
      background: rgba(22,27,34,0.95); border: 1px solid #30363d; border-radius: 6px;
      padding: 8px 12px; font-size: 12px; color: #c9d1d9; max-width: 220px;
      display: none; line-height: 1.5;
    }
    #tooltip strong { color: #58a6ff; }

    /* ── Hint inicial ── */
    #hint {
      position: fixed; bottom: 16px; right: 16px; font-size: 11px; color: #484f58;
      z-index: 100; text-align: right; line-height: 1.7;
    }
  </style>
</head>
<body>
<div id="graph"></div>

<!-- ── Sidebar ── -->
<div id="sidebar">
  <h1>Grafo 3D<br>Fichas CR ↔ Directivas AR</h1>
  <div class="subtitle">Manual de Reformas DGT · Rev. 7.2</div>

  <div class="stats-row" id="stats-row"></div>

  <hr class="divider">

  <div class="legend-section">
    <div class="legend-title">Fichas CR — Sección</div>
    <div class="legend-item"><div class="legend-dot" style="background:#e74c3c"></div>Sección I (M, N, O)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#3498db"></div>Sección II (L)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#27ae60"></div>Sección III (Agrícola)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f39c12"></div>Sección IV (Obras)</div>
  </div>

  <div class="legend-section">
    <div class="legend-title">Directivas AR — Tipo de norma</div>
    <div class="legend-item"><div class="legend-square" style="background:#9b59b6"></div>Directiva …/CEE</div>
    <div class="legend-item"><div class="legend-square" style="background:#1abc9c"></div>Directiva …/CE</div>
    <div class="legend-item"><div class="legend-square" style="background:#e74c3c"></div>Reglamento (CE)</div>
    <div class="legend-item"><div class="legend-square" style="background:#e67e22"></div>Reglamento (UE)</div>
    <div class="legend-item"><div class="legend-square" style="background:#2ecc71"></div>Reglamento CEPE/ONU</div>
    <div class="legend-item"><div class="legend-square" style="background:#7f8c8d"></div>Otras referencias</div>
  </div>

  <hr class="divider">

  <div class="control-group">
    <div class="control-label">Filtrar sección CR</div>
    <select id="sec-filter">
      <option value="">Todas las secciones</option>
      <option value="I">Sección I</option>
      <option value="II">Sección II</option>
      <option value="III">Sección III</option>
      <option value="IV">Sección IV</option>
    </select>
  </div>

  <div class="control-group">
    <div class="control-label">Filtrar tipo AR</div>
    <select id="ar-filter">
      <option value="">Todos los tipos</option>
      <option value="dir_cee">Directiva …/CEE</option>
      <option value="dir_ce">Directiva …/CE</option>
      <option value="reg_ce">Reglamento (CE)</option>
      <option value="reg_ue">Reglamento (UE)</option>
      <option value="cepe_onu">CEPE/ONU</option>
    </select>
  </div>

  <div class="control-group">
    <button onclick="resetCamera()">⟳ &nbsp;Resetear cámara</button>
    <button id="physics-btn" onclick="togglePhysics()">⏸ &nbsp;Pausar física</button>
  </div>
</div>

<!-- ── Panel detalle ── -->
<div id="detail-panel">
  <button class="close-btn" onclick="closeDetail()">✕</button>
  <div id="detail-title"></div>
  <div id="detail-content"></div>
</div>

<!-- ── Tooltip hover ── -->
<div id="tooltip"></div>

<!-- ── Hint ── -->
<div id="hint">
  Arrastra para rotar · Scroll para zoom · Click en nodo para detalles<br>
  Izquierda: Fichas CR &nbsp;·&nbsp; Derecha: Directivas AR
</div>

<script src="https://unpkg.com/3d-force-graph@1"></script>
<script>
// ── Datos ─────────────────────────────────────────────────────────────────
const rawData = __GRAPH_DATA__;
const stats   = __STATS_DATA__;

// ── Stats panel ────────────────────────────────────────────────────────────
const statsRow = document.getElementById('stats-row');
statsRow.innerHTML = [
  `<div class="stat-chip">CR <span>${stats.n_cr}</span></div>`,
  `<div class="stat-chip">AR <span>${stats.n_ar}</span></div>`,
  `<div class="stat-chip">enlaces <span>${stats.n_edges}</span></div>`,
].join('');

// ── Construir grafo ────────────────────────────────────────────────────────
let physicsEnabled = true;

// Construir mapa de adyacencia para highlight rápido
const neighborMap = {};
rawData.nodes.forEach(n => { neighborMap[n.id] = new Set(); });
rawData.links.forEach(l => {
  const s = l.source.id || l.source;
  const t = l.target.id || l.target;
  if (neighborMap[s]) neighborMap[s].add(t);
  if (neighborMap[t]) neighborMap[t].add(s);
});

const highlightNodes = new Set();
const highlightLinks = new Set();
let hoveredNode = null;
let selectedNode = null;

const Graph = ForceGraph3D()(document.getElementById('graph'))
  .backgroundColor('#0d1117')
  .graphData(rawData)
  .nodeId('id')
  .nodeVal(n => {
    if (n.group === 'cr') return 4 + Math.min(n.n_ars / 3, 8);
    return 3 + Math.min(n.n_crs / 5, 6);
  })
  .nodeColor(n => {
    if (highlightNodes.size === 0) return n.color;
    return highlightNodes.has(n.id) ? '#ffffff' : n.color + '44';
  })
  .nodeOpacity(0.92)
  .nodeResolution(12)
  .linkColor(l => {
    if (highlightLinks.size === 0) return l.color + '55';
    const s = l.source.id || l.source;
    const t = l.target.id || l.target;
    const key = `${s}|${t}`;
    return highlightLinks.has(key) ? l.color + 'dd' : l.color + '15';
  })
  .linkWidth(l => {
    if (highlightLinks.size === 0) return 0.4;
    const s = l.source.id || l.source;
    const t = l.target.id || l.target;
    return highlightLinks.has(`${s}|${t}`) ? 2 : 0.2;
  })
  .linkOpacity(0.6)
  .linkDirectionalParticles(l => {
    const s = l.source.id || l.source;
    const t = l.target.id || l.target;
    return highlightLinks.has(`${s}|${t}`) ? 4 : 0;
  })
  .linkDirectionalParticleWidth(2)
  .onNodeHover(node => {
    highlightNodes.clear();
    highlightLinks.clear();
    if (node) {
      highlightNodes.add(node.id);
      const neighbors = neighborMap[node.id] || new Set();
      neighbors.forEach(nid => highlightNodes.add(nid));
      rawData.links.forEach(l => {
        const s = l.source.id || l.source;
        const t = l.target.id || l.target;
        if (s === node.id || t === node.id) {
          highlightLinks.add(`${s}|${t}`);
        }
      });
    }
    hoveredNode = node || null;
    Graph.nodeColor(Graph.nodeColor()).linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth());
    showTooltip(node);
  })
  .onNodeClick(node => {
    selectedNode = node;
    showDetail(node);
    // Zoom suave hacia el nodo
    const dist = 120;
    const distRatio = 1 + dist / Math.hypot(node.x || 0, node.y || 0, node.z || 0);
    Graph.cameraPosition(
      { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
      node,
      800
    );
  })
  .onBackgroundClick(() => {
    highlightNodes.clear();
    highlightLinks.clear();
    Graph.nodeColor(Graph.nodeColor()).linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth());
    closeDetail();
  });

// ── Fuerzas para layout bipartito ─────────────────────────────────────────
// Fuerza X: CR a la izquierda, AR a la derecha
Graph.d3Force('bipartite_x', alpha => {
  Graph.graphData().nodes.forEach(n => {
    const tx = n.group === 'cr' ? -320 : 320;
    n.vx = (n.vx || 0) + (tx - (n.x || 0)) * 0.06 * alpha;
  });
});

// Fuerza Y: agrupar por sección (CR) o tipo de norma (AR)
Graph.d3Force('group_y', alpha => {
  Graph.graphData().nodes.forEach(n => {
    const ty = n.y_bias || 0;
    n.vy = (n.vy || 0) + (ty - (n.y || 0)) * 0.015 * alpha;
  });
});

// Reducir la fuerza de carga por defecto para que no se expanda demasiado
Graph.d3Force('charge').strength(-30);

// ── Tooltip ───────────────────────────────────────────────────────────────
const tooltip = document.getElementById('tooltip');
document.addEventListener('mousemove', e => {
  tooltip.style.left = (e.clientX + 14) + 'px';
  tooltip.style.top  = (e.clientY - 10) + 'px';
});

function showTooltip(node) {
  if (!node) { tooltip.style.display = 'none'; return; }
  if (node.group === 'cr') {
    tooltip.innerHTML = `<strong>${node.id}</strong><br>Vía ${node.via} · Sec. ${node.seccion}<br>${node.n_ars} directivas AR`;
  } else {
    tooltip.innerHTML = `<strong>${node.ref}</strong><br>${node.sistema || ''}<br>${node.tipo_label}<br>Referenciado en ${node.n_crs} fichas`;
  }
  tooltip.style.display = 'block';
}

// ── Panel de detalle ─────────────────────────────────────────────────────
const VIA_COLOR = { A: '#e74c3c', B: '#f39c12', C: '#27ae60', D: '#3498db' };
const VIA_LABEL = { A: 'Vía A', B: 'Vía B', C: 'Vía C', D: 'Vía D' };

function showDetail(node) {
  const panel = document.getElementById('detail-panel');
  const title = document.getElementById('detail-title');
  const content = document.getElementById('detail-content');

  if (node.group === 'cr') {
    const viaBg = VIA_COLOR[node.via] || '#666';
    const secBg = {I:'#e74c3c',II:'#3498db',III:'#27ae60',IV:'#f39c12'}[node.seccion] || '#666';
    title.textContent = node.id;
    content.innerHTML = `
      <div style="margin-bottom:8px">
        <span class="badge" style="background:${secBg}22;color:${secBg};border:1px solid ${secBg}44">Sección ${node.seccion}</span>
        <span class="badge" style="background:${viaBg}22;color:${viaBg};border:1px solid ${viaBg}44">${VIA_LABEL[node.via] || 'Vía ?'}</span>
      </div>
      ${node.desc ? `<div class="field">${node.desc}</div>` : ''}
      <div class="field"><strong>Categorías:</strong> ${(node.categorias || []).join(', ') || '—'}</div>
      <div class="field"><strong>Directivas AR requeridas:</strong> ${node.n_ars}</div>
    `;
  } else {
    const tipoBg = {dir_cee:'#9b59b6',dir_ce:'#1abc9c',reg_ue:'#e67e22',reg_ce:'#e74c3c',cepe_onu:'#2ecc71',otro:'#7f8c8d'}[node.tipo] || '#666';
    title.textContent = node.ref;
    // Buscar las fichas CR que referencian este AR (para mostrar lista)
    const crRefs = rawData.links
      .filter(l => (l.target.id || l.target) === node.id)
      .slice(0, 8)
      .map(l => (l.source.id || l.source));
    const masStr = node.n_crs > 8 ? `<br><span style="color:#8b949e">+ ${node.n_crs - 8} más…</span>` : '';
    content.innerHTML = `
      <div style="margin-bottom:8px">
        <span class="badge" style="background:${tipoBg}22;color:${tipoBg};border:1px solid ${tipoBg}44">${node.tipo_label}</span>
      </div>
      ${node.sistema ? `<div class="field"><strong>Sistema:</strong> ${node.sistema}</div>` : ''}
      <div class="field"><strong>Referenciado en:</strong> ${node.n_crs} fichas CR</div>
      ${crRefs.length ? `<div class="field"><strong>Fichas:</strong><div class="aplic-list">${crRefs.join(' · ')}${masStr}</div></div>` : ''}
    `;
  }
  panel.style.display = 'block';
}

function closeDetail() {
  document.getElementById('detail-panel').style.display = 'none';
  selectedNode = null;
}

// ── Filtros ────────────────────────────────────────────────────────────────
let secFilter = '';
let arFilter  = '';

function applyFilters() {
  const filtered = {
    nodes: rawData.nodes.filter(n => {
      if (n.group === 'cr' && secFilter && n.seccion !== secFilter) return false;
      if (n.group === 'ar' && arFilter && n.tipo !== arFilter) return false;
      return true;
    }),
    links: [],
  };
  const nodeIds = new Set(filtered.nodes.map(n => n.id));
  filtered.links = rawData.links.filter(l => {
    const s = l.source.id || l.source;
    const t = l.target.id || l.target;
    return nodeIds.has(s) && nodeIds.has(t);
  });
  Graph.graphData(filtered);
}

document.getElementById('sec-filter').addEventListener('change', e => {
  secFilter = e.target.value;
  applyFilters();
});
document.getElementById('ar-filter').addEventListener('change', e => {
  arFilter = e.target.value;
  applyFilters();
});

// ── Controles ──────────────────────────────────────────────────────────────
function resetCamera() {
  Graph.cameraPosition({ x: 0, y: 0, z: 900 }, { x: 0, y: 0, z: 0 }, 800);
}

function togglePhysics() {
  physicsEnabled = !physicsEnabled;
  const btn = document.getElementById('physics-btn');
  if (physicsEnabled) {
    Graph.d3AlphaDecay(0.0228).d3ReheatSimulation();
    btn.textContent = '⏸  Pausar física';
  } else {
    Graph.d3AlphaDecay(1);   // detiene la simulación sin cortar el render loop
    btn.textContent = '▶  Reanudar física';
  }
}

// Posición inicial de cámara
Graph.cameraPosition({ x: 0, y: 0, z: 900 });
</script>
</body>
</html>
"""


# ─── Generar HTML ─────────────────────────────────────────────────────────────

def generar_html(data: dict, output: Path) -> None:
    stats = _stats(data)
    graph_json = json.dumps(data, ensure_ascii=False)
    stats_json = json.dumps(stats, ensure_ascii=False)
    html = _HTML_TEMPLATE.replace("__GRAPH_DATA__", graph_json).replace("__STATS_DATA__", stats_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Grafo 3D bipartito CR ↔ Directivas AR")
    parser.add_argument("--seccion",    metavar="SEC",  help="Filtrar fichas CR por sección (I|II|III|IV)")
    parser.add_argument("--output",     metavar="PATH", help="Ruta del HTML de salida")
    parser.add_argument("--no-browser", action="store_true", help="No abrir el navegador automáticamente")
    args = parser.parse_args()

    output = Path(args.output) if args.output else OUTPUT_HTML

    fichas = _cargar_fichas()
    if not fichas:
        print("❌ No se encontraron fichas. Comprueba que existen los JSONs en json/.")
        return

    data = _construir_grafo(fichas, args.seccion)
    s = _stats(data)
    print(f"Fichas CR : {s['n_cr']:>4}  (secciones: {', '.join(s['secciones'])})")
    print(f"Directivas: {s['n_ar']:>4}")
    print(f"Relaciones: {s['n_edges']:>4}")

    generar_html(data, output)
    print(f"\n✅ HTML generado en {output}")

    if not args.no_browser:
        webbrowser.open(output.as_uri())


if __name__ == "__main__":
    main()

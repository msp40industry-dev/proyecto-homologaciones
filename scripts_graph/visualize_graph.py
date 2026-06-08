"""
visualize_graph.py — Genera un HTML interactivo del grafo KAG.

Uso:
    python scripts_graph/visualize_graph.py                    # grafo completo
    python scripts_graph/visualize_graph.py --cr I:5.1 I:2.1  # CRs concretas y sus vecinos
    python scripts_graph/visualize_graph.py --cr 5.1          # CR 5.1 en todas las secciones
    python scripts_graph/visualize_graph.py --tipo implica_cr  # filtrar por tipo de edge
    python scripts_graph/visualize_graph.py --seccion II       # solo sección II

El HTML resultante se abre automáticamente en el navegador.

Leyenda de colores:
  Nodos:  🔴 Vía A  🟡 Vía B  🟢 Vía C  🔵 Vía D
  Edges:  azul = implica_cr  |  naranja = obliga_incorporar  |  gris = restriccion
"""

import argparse
import json
import os
import webbrowser
from pathlib import Path

import networkx as nx
from pyvis.network import Network

GRAPH_PATH  = Path(__file__).resolve().parent / "graph.json"
OUTPUT_HTML = Path(__file__).resolve().parent / "graph.html"

COLOR_VIA = {
    "A": "#e74c3c",   # rojo
    "B": "#f39c12",   # naranja-amarillo
    "C": "#27ae60",   # verde
    "D": "#2980b9",   # azul
}
COLOR_EDGE = {
    "implica_cr":       "#2980b9",   # azul
    "obliga_incorporar": "#e67e22",  # naranja
    "restriccion":      "#95a5a6",   # gris
}
LABEL_EDGE = {
    "implica_cr":        "implica",
    "obliga_incorporar": "incorporar",
    "restriccion":       "restricción",
}


def cargar() -> dict:
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró {GRAPH_PATH}\n"
            "Genera el grafo primero con:\n  python scripts_graph/build_graph.py"
        )
    with open(GRAPH_PATH, encoding="utf-8") as f:
        return json.load(f)


SECCIONES = ("I", "II", "III", "IV")


def _resolver_keys_filtro(crs_arg: list[str], nodos: dict) -> set[str]:
    """Acepta 'I:2.1' o '2.1' (todas las secciones) y devuelve keys del grafo."""
    keys: set[str] = set()
    for cr in crs_arg:
        if ":" in cr:
            sec, codigo = cr.split(":", 1)
            k = f"CR-{sec.upper()}-{codigo}"
            if k in nodos:
                keys.add(k)
        else:
            for sec in SECCIONES:
                k = f"CR-{sec}-{cr}"
                if k in nodos:
                    keys.add(k)
    return keys


def tooltip(key: str, nodo: dict) -> str:
    sec   = nodo.get("seccion", "?")
    via   = nodo.get("via", "?")
    cats  = ", ".join(nodo.get("categorias_aplicables", []))
    desc  = nodo.get("descripcion", "")
    rev   = nodo.get("revision_fuente", "")
    n_ars = sum(len(v) for v in nodo.get("ars_por_categoria", {}).values())
    pt    = "SÍ" if nodo.get("requiere_proyecto") else "NO"
    return (
        f"<b>{key}</b><br>"
        f"Sección: {sec}<br>"
        f"Vía: {via}<br>"
        f"Proyecto técnico: {pt}<br>"
        f"Categorías: {cats}<br>"
        f"ARs totales: {n_ars}<br>"
        f"Revisión: {rev}<br><br>"
        f"<i>{desc[:120]}{'…' if len(desc) > 120 else ''}</i>"
    )


def construir_red(
    grafo: dict,
    crs_filtro: list[str] | None,
    tipo_filtro: str | None,
    seccion_filtro: str | None,
) -> nx.DiGraph:
    G = nx.DiGraph()

    nodos = grafo["nodos"]
    edges = grafo["edges"]

    # Filtrar por sección
    if seccion_filtro:
        sec = seccion_filtro.upper()
        nodos = {k: v for k, v in nodos.items() if k.startswith(f"CR-{sec}-")}
        edges = [e for e in edges if e["cr_origen"].startswith(f"CR-{sec}-")]

    if tipo_filtro:
        edges = [e for e in edges if e["tipo"] == tipo_filtro]

    if crs_filtro:
        keys = _resolver_keys_filtro(crs_filtro, nodos)
        # Incluir vecinos directos
        for e in edges:
            if e["cr_origen"] in keys or (e.get("cr_destino") and e["cr_destino"] in keys):
                keys.add(e["cr_origen"])
                if e.get("cr_destino"):
                    keys.add(e["cr_destino"])
        nodos = {k: v for k, v in nodos.items() if k in keys}
        edges = [
            e for e in edges
            if e["cr_origen"] in keys and (not e.get("cr_destino") or e["cr_destino"] in keys)
        ]

    for key, nodo in nodos.items():
        codigo = nodo["codigo"]
        sec    = nodo.get("seccion", "?")
        via    = nodo.get("via", "?")
        G.add_node(
            key,
            label=f"CR-{sec}-{codigo}",
            title=tooltip(key, nodo),
            color=COLOR_VIA.get(via, "#bdc3c7"),
            size=20,
        )

    for e in edges:
        origen  = e["cr_origen"]
        destino = e.get("cr_destino")
        tipo    = e["tipo"]
        cond    = e.get("condicion") or ""
        fuente  = e.get("fuente_literal", "")[:100]

        # Nodo destino puede ser None (incorporación sin CR)
        if not destino:
            # Crear nodo fantasma para representar la incorporación física
            destino = f"__inc__{origen}_{tipo}"
            if destino not in G:
                G.add_node(
                    destino,
                    label="(incorporar)",
                    title=f"Incorporación física sin CR adicional<br><i>{fuente}</i>",
                    color="#ecf0f1",
                    size=10,
                    shape="diamond",
                )

        if origen in G and destino in G:
            G.add_edge(
                origen, destino,
                title=f"<b>{tipo}</b><br>{cond}<br><i>{fuente}{'…' if len(e.get('fuente_literal',''))>100 else ''}</i>",
                label=LABEL_EDGE.get(tipo, tipo),
                color=COLOR_EDGE.get(tipo, "#666"),
                width=2,
                arrows="to",
            )

    return G


def generar_html(G: nx.DiGraph) -> None:
    net = Network(
        height="900px",
        width="100%",
        directed=True,
        bgcolor="#1a1a2e",
        font_color="white",
        notebook=False,
    )
    net.from_nx(G)
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.01,
          "springLength": 150,
          "springConstant": 0.04
        },
        "solver": "forceAtlas2Based",
        "stabilization": { "iterations": 200 }
      },
      "edges": {
        "smooth": { "type": "curvedCW", "roundness": 0.2 },
        "font": { "size": 10, "color": "#ecf0f1", "strokeWidth": 0 }
      },
      "nodes": {
        "font": { "size": 13, "bold": true }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100,
        "navigationButtons": true
      }
    }
    """)
    net.write_html(str(OUTPUT_HTML))


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualización interactiva del grafo KAG")
    parser.add_argument("--cr",      nargs="+", metavar="[SEC:]X.Y", help="CRs a mostrar (ej. I:5.1 o 5.1 para todas las secciones)")
    parser.add_argument("--tipo",    metavar="TIPO",  help="Filtrar edges: implica_cr | obliga_incorporar | restriccion")
    parser.add_argument("--seccion", metavar="SEC",   help="Mostrar solo una sección (I|II|III|IV)")
    args = parser.parse_args()

    grafo = cargar()
    G = construir_red(grafo, args.cr, args.tipo, args.seccion)

    print(f"Nodos en la visualización : {G.number_of_nodes()}")
    print(f"Edges en la visualización : {G.number_of_edges()}")

    generar_html(G)
    print(f"HTML generado en {OUTPUT_HTML}")
    webbrowser.open(str(OUTPUT_HTML))


if __name__ == "__main__":
    main()

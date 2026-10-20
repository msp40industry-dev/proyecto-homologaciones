"""
inspect_graph.py — Inspección del grafo KAG de relaciones entre CRs.

Uso:
    python scripts_graph/inspect_graph.py                        # resumen general
    python scripts_graph/inspect_graph.py --cr I:2.1            # nodo + relaciones (sección específica)
    python scripts_graph/inspect_graph.py --cr 5.1              # busca CR 5.1 en todas las secciones
    python scripts_graph/inspect_graph.py --tipo implica_cr     # todos los edges de ese tipo
    python scripts_graph/inspect_graph.py --desde I:5.1         # edges que salen de CR-I-5.1
    python scripts_graph/inspect_graph.py --hacia II:2.9        # edges que llegan a CR-II-2.9
    python scripts_graph/inspect_graph.py --seccion II          # resumen de solo la sección II
"""

import argparse
import json
from collections import Counter
from pathlib import Path

GRAPH_PATH = Path(__file__).resolve().parent / "graph.json"
SECCIONES  = ("I", "II", "III", "IV")


def cargar() -> dict:
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró {GRAPH_PATH}\n"
            "Genera el grafo primero con:\n"
            "  python scripts_graph/build_graph.py"
        )
    with open(GRAPH_PATH, encoding="utf-8") as f:
        return json.load(f)


def _resolver_keys(codigo: str, nodos: dict) -> list[str]:
    """
    Acepta 'I:2.1' → ['CR-I-2.1']  o  '2.1' → todas las secciones que lo tengan.
    """
    if ":" in codigo:
        sec, cr = codigo.split(":", 1)
        key = f"CR-{sec.upper()}-{cr}"
        return [key] if key in nodos else []
    else:
        return [f"CR-{sec}-{codigo}" for sec in SECCIONES
                if f"CR-{sec}-{codigo}" in nodos]


def fmt_edge(edge: dict) -> str:
    origen  = edge["cr_origen"]
    destino = edge.get("cr_destino") or "(sin CR)"
    tipo    = edge["tipo"]
    cond    = f"\n    condicion   : {edge['condicion']}" if edge.get("condicion") else ""
    sin_tr  = "  [sin tramitar CR]" if edge.get("sin_tramitar_cr") else ""
    fuente  = edge.get("fuente_literal", "")[:120]
    return (
        f"  {origen} → {destino}  [{tipo}]{sin_tr}{cond}\n"
        f"    fuente      : \"{fuente}{'…' if len(edge.get('fuente_literal','')) > 120 else ''}\""
    )


def resumen(grafo: dict, seccion_filtro: str | None = None) -> None:
    nodos = grafo["nodos"]
    edges = grafo["edges"]

    if seccion_filtro:
        sec = seccion_filtro.upper()
        nodos = {k: v for k, v in nodos.items() if k.startswith(f"CR-{sec}-")}
        edges = [e for e in edges if e["cr_origen"].startswith(f"CR-{sec}-")]

    tipos = Counter(e["tipo"] for e in edges)

    print(f"Grafo KAG — {grafo['manual']['fuente']}")
    print(f"Revisión : {grafo['manual']['revision']}")
    print(f"Generado : {grafo['generado']}")
    if seccion_filtro:
        print(f"Filtro   : Sección {seccion_filtro.upper()}")
    print(f"\nNodos    : {len(nodos)}")
    print(f"Edges    : {len(edges)}")

    if not seccion_filtro:
        print("\nNodos por sección:")
        por_sec: dict[str, int] = {}
        for k in grafo["nodos"]:
            sec = k.split("-")[1] if "-" in k else "?"
            por_sec[sec] = por_sec.get(sec, 0) + 1
        for sec in sorted(por_sec):
            print(f"  Sección {sec}: {por_sec[sec]} nodos")

    if tipos:
        print("\nEdges por tipo:")
        for tipo, n in sorted(tipos.items()):
            print(f"  {tipo:<22} {n}")

    salientes = Counter(e["cr_origen"] for e in edges)
    if salientes:
        print("\nTop 5 CRs con más relaciones salientes:")
        for cr, n in salientes.most_common(5):
            print(f"  {cr}: {n}")


def mostrar_cr(grafo: dict, codigo: str) -> None:
    keys = _resolver_keys(codigo, grafo["nodos"])
    if not keys:
        print(f"'{codigo}' no encontrado en el grafo. Usa 'SEC:X.Y' (ej. I:2.1) o solo 'X.Y'.")
        return

    for key in keys:
        nodo = grafo["nodos"][key]
        print(f"\n{'─'*60}")
        print(f"Nodo: {key}")
        print(f"  Descripción   : {nodo['descripcion']}")
        print(f"  Sección       : {nodo.get('seccion', '?')}")
        print(f"  Vía           : {nodo['via']}")
        print(f"  Categorías    : {', '.join(nodo['categorias_aplicables'])}")
        print(f"  Proyecto      : {'SÍ' if nodo['requiere_proyecto'] else 'NO'}")
        print(f"  Rev. fuente   : {nodo['revision_fuente']}")

        n_ars = sum(len(v) for v in nodo["ars_por_categoria"].values())
        print(f"  ARs (total)   : {n_ars} (en {len(nodo['ars_por_categoria'])} categorías)")

        edges_salientes = [e for e in grafo["edges"] if e["cr_origen"] == key]
        edges_entrantes = [e for e in grafo["edges"] if e.get("cr_destino") == key]

        print(f"\nRelaciones salientes ({len(edges_salientes)}):")
        if edges_salientes:
            for e in edges_salientes:
                print(fmt_edge(e))
        else:
            print("  (ninguna)")

        print(f"\nRelaciones entrantes ({len(edges_entrantes)}):")
        if edges_entrantes:
            for e in edges_entrantes:
                print(fmt_edge(e))
        else:
            print("  (ninguna)")


def mostrar_por_tipo(grafo: dict, tipo: str) -> None:
    edges = [e for e in grafo["edges"] if e["tipo"] == tipo]
    print(f"\nEdges de tipo '{tipo}' ({len(edges)}):")
    if not edges:
        print("  (ninguno)")
        return
    for e in edges:
        print(fmt_edge(e))


def mostrar_desde(grafo: dict, codigo: str) -> None:
    keys = _resolver_keys(codigo, grafo["nodos"])
    if not keys:
        print(f"'{codigo}' no encontrado en el grafo.")
        return
    for key in keys:
        edges = [e for e in grafo["edges"] if e["cr_origen"] == key]
        print(f"\nRelaciones que salen de {key} ({len(edges)}):")
        for e in edges:
            print(fmt_edge(e))


def mostrar_hacia(grafo: dict, codigo: str) -> None:
    keys = _resolver_keys(codigo, grafo["nodos"])
    if not keys:
        print(f"'{codigo}' no encontrado en el grafo.")
        return
    for key in keys:
        edges = [e for e in grafo["edges"] if e.get("cr_destino") == key]
        print(f"\nRelaciones que llegan a {key} ({len(edges)}):")
        for e in edges:
            print(fmt_edge(e))


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspección del grafo KAG")
    parser.add_argument("--cr",      metavar="[SEC:]X.Y", help="Nodo + relaciones (ej. I:2.1 o 2.1 para todas las secciones)")
    parser.add_argument("--tipo",    metavar="TIPO",      help="Filtrar edges por tipo")
    parser.add_argument("--desde",   metavar="[SEC:]X.Y", help="Edges que salen de esa CR")
    parser.add_argument("--hacia",   metavar="[SEC:]X.Y", help="Edges que llegan a esa CR")
    parser.add_argument("--seccion", metavar="SEC",       help="Filtrar resumen a una sección (I|II|III|IV)")
    args = parser.parse_args()

    grafo = cargar()

    if args.cr:
        mostrar_cr(grafo, args.cr)
    elif args.tipo:
        mostrar_por_tipo(grafo, args.tipo)
    elif args.desde:
        mostrar_desde(grafo, args.desde)
    elif args.hacia:
        mostrar_hacia(grafo, args.hacia)
    else:
        resumen(grafo, args.seccion)


if __name__ == "__main__":
    main()

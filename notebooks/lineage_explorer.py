import marimo

__generated_with = "0.23.15"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    from pbix_atlas import (
        LineageGraphBuilder,
        downstream,
        export_edges_csv,
        export_graphml,
        export_nodes_csv,
        find_nodes,
        graph_summary,
        print_tree,
        upstream,
    )

    return (
        LineageGraphBuilder,
        export_edges_csv,
        export_graphml,
        export_nodes_csv,
        find_nodes,
        graph_summary,
        mo,
        print_tree,
    )


@app.cell
def _():
    import subprocess
    subprocess.run("ls", shell=True)

    file_path = "data/DEMO_ANONYM.pbix"
    return (file_path,)


@app.cell
def _(LineageGraphBuilder, export_graphml, file_path):
    graph = LineageGraphBuilder().build(file_path)
    export_graphml(graph, "lineage.graphml")   # opens in Gephi / yEd
    return (graph,)


@app.cell
def _(graph):
    import matplotlib.pyplot as plt
    import networkx as nx

    plt.figure(figsize=(12, 12))
    pos = nx.spring_layout(graph, k=0.15, iterations=50)
    nx.draw(graph, pos, with_labels=True, node_size=50, font_size=4)
    plt.show()
    return


@app.cell
def _(graph, mo):
    from pyvis.network import Network

    net = Network(height="750px", width="100%", directed=True, notebook=False)
    net.from_nx(graph)

    net.repulsion(node_distance=150, central_gravity=0.3)

    html_path = "graph.html"
    net.save_graph(html_path)

    mo.Html(open(html_path, "r", encoding="utf-8").read())
    return


@app.cell
def _(file_path, mo):
    mo.md("# PBIX Lineage Explorer")
    pbix_path = mo.ui.text(value=file_path, label="Path to .pbix file")
    pbix_path
    return (pbix_path,)


@app.cell
def _(LineageGraphBuilder, graph_summary, pbix_path):
    graph = LineageGraphBuilder().build(pbix_path.value)
    summary = graph_summary(graph)
    summary
    return (graph,)


@app.cell
def _(mo):
    mo.md("## Search a node (column, measure, visual field...)")
    search = mo.ui.text(value="", label="Contains (case-insensitive)")
    search
    return (search,)


@app.cell
def _(find_nodes, graph, search):
    matches = find_nodes(graph, search.value) if search.value else []
    matches[:50]
    return


@app.cell
def _(mo):
    mo.md("## Upstream tree: display -> source")
    node_upstream = mo.ui.text(value="", label="Node id (copy from search above)")
    node_upstream
    return (node_upstream,)


@app.cell
def _(graph, node_upstream, print_tree):
    if node_upstream.value and node_upstream.value in graph:
        print_tree(graph, node_upstream.value, direction="upstream")
    else:
        print("(select a valid node above)")
    return


@app.cell
def _(mo):
    mo.md("## Downstream tree: source -> display")
    node_downstream = mo.ui.text(value="", label="Node id")
    node_downstream
    return (node_downstream,)


@app.cell
def _(graph, node_downstream, print_tree):
    if node_downstream.value and node_downstream.value in graph:
        print_tree(graph, node_downstream.value, direction="downstream")
    else:
        print("(select a valid node above)")
    return


@app.cell
def _(mo):
    mo.md("""
    ## Export
    """)
    return


@app.cell
def _(export_edges_csv, export_graphml, export_nodes_csv, graph):
    export_nodes_csv(graph, "lineage_nodes.csv")
    export_edges_csv(graph, "lineage_edges.csv")
    export_graphml(graph, "lineage.graphml")
    print("Exported: lineage_nodes.csv, lineage_edges.csv, lineage.graphml")
    return


if __name__ == "__main__":
    app.run()

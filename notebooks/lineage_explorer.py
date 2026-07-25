import marimo

__generated_with = "0.23.15"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    from pbix_lineage import (
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
    return


@app.cell
def _(mo):
    mo.md("# PBIX Lineage Explorer")
    pbix_path = mo.ui.text(value="data/DEMO_ANONYM.pbix", label="Path to .pbix file")
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

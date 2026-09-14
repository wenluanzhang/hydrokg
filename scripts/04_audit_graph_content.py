"""Create lightweight content audit reports for HydroKG graph tables."""

from __future__ import annotations

from pathlib import Path

from hydrokg.graph.audit import (
    audit_node_labels,
    load_graph_tables,
    summarize_degree_by_edge_type,
    top_nodes_by_total_degree,
    write_graph_audit,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NODES_PATH = REPOSITORY_ROOT / "data" / "processed" / "hydrokg_nodes.csv"
EDGES_PATH = REPOSITORY_ROOT / "data" / "processed" / "hydrokg_edges.csv"
OUTPUT_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"


def main() -> int:
    """Build and write the graph content audit CSV files."""
    tables = load_graph_tables(NODES_PATH, EDGES_PATH)
    top_nodes = top_nodes_by_total_degree(tables.nodes, tables.edges)
    label_audit = audit_node_labels(tables.nodes)
    edge_summary = summarize_degree_by_edge_type(tables.edges)
    paths = write_graph_audit(
        top_nodes=top_nodes,
        label_audit=label_audit,
        edge_type_degree_summary=edge_summary,
        output_directory=OUTPUT_DIRECTORY,
    )

    print(f"Top nodes reported: {len(top_nodes)}")
    print(
        "Empty labels: "
        f"{sum(int(row['empty_label_count']) for row in label_audit)}"
    )
    for path in (
        paths.top_nodes_by_degree,
        paths.node_label_audit,
        paths.edge_type_degree_summary,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

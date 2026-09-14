"""Summarize generated HydroKG node and edge tables."""

from __future__ import annotations

from pathlib import Path

from hydrokg.graph.summary import (
    check_graph_integrity,
    load_graph_tables,
    summarize_edge_types,
    summarize_node_types,
    write_graph_summary,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NODES_PATH = REPOSITORY_ROOT / "data" / "processed" / "hydrokg_nodes.csv"
EDGES_PATH = REPOSITORY_ROOT / "data" / "processed" / "hydrokg_edges.csv"
OUTPUT_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"


def main() -> int:
    """Create graph count and integrity summary CSV files."""
    tables = load_graph_tables(NODES_PATH, EDGES_PATH)
    node_counts = summarize_node_types(tables.nodes)
    edge_counts = summarize_edge_types(tables.edges)
    integrity = check_graph_integrity(tables.nodes, tables.edges)
    paths = write_graph_summary(
        node_type_counts=node_counts,
        edge_type_counts=edge_counts,
        integrity=integrity,
        output_directory=OUTPUT_DIRECTORY,
    )

    print(f"Nodes: {integrity.total_node_count}")
    print(f"Edges: {integrity.total_edge_count}")
    print(
        "Missing edge endpoints: "
        f"{integrity.missing_edge_source_id_count} source, "
        f"{integrity.missing_edge_target_id_count} target"
    )
    for path in (
        paths.node_type_counts,
        paths.edge_type_counts,
        paths.integrity_summary,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

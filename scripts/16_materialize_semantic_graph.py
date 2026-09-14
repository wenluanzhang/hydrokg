"""Materialize semantic concepts and merge them with the HydroKG base graph."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from hydrokg.graph.semantic_materialization import (
    find_missing_edge_endpoints,
    materialize_semantic_graph,
    write_semantic_graph_tables,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIRECTORY = REPOSITORY_ROOT / "data" / "processed"
RESULTS_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"
BASE_NODES_PATH = PROCESSED_DIRECTORY / "hydrokg_nodes.csv"
BASE_EDGES_PATH = PROCESSED_DIRECTORY / "hydrokg_edges.csv"
DEVICE_TABLE_PATH = (
    PROCESSED_DIRECTORY / "hydrokg_r_centered_device_table.csv"
)
PATHWAY_MATCHES_PATH = (
    RESULTS_DIRECTORY / "hydrokg_device_pathway_matches.csv"
)
SEMANTIC_LAYER_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "schema"
    / "hydrokg_semantic_layer_v1.json"
)
PATHWAY_RULES_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "rules"
    / "hydrokg_pathway_rules_v1.json"
)


def main() -> int:
    """Materialize, validate, and write semantic and integrated graph tables."""
    tables = materialize_semantic_graph(
        base_nodes_path=BASE_NODES_PATH,
        base_edges_path=BASE_EDGES_PATH,
        device_table_path=DEVICE_TABLE_PATH,
        pathway_matches_path=PATHWAY_MATCHES_PATH,
        semantic_layer_path=SEMANTIC_LAYER_PATH,
        pathway_rules_path=PATHWAY_RULES_PATH,
    )
    missing_endpoints = find_missing_edge_endpoints(
        tables.integrated_nodes,
        tables.integrated_edges,
    )
    if missing_endpoints:
        raise ValueError(
            "Integrated graph has missing endpoints: "
            + ", ".join(missing_endpoints)
        )
    paths = write_semantic_graph_tables(tables, RESULTS_DIRECTORY)

    print("Semantic node counts by type:")
    for node_type, count in sorted(
        Counter(row["node_type"] for row in tables.semantic_nodes).items()
    ):
        print(f"  {node_type}: {count}")
    print("Semantic edge counts by relation:")
    for edge_type, count in sorted(
        Counter(row["edge_type"] for row in tables.semantic_edges).items()
    ):
        print(f"  {edge_type}: {count}")
    labels_by_id = {
        row["node_id"]: row["label"] for row in tables.semantic_nodes
    }
    for node_type in ("DesignVariable", "ReportingItem"):
        print(f"{node_type} vocabulary:")
        for row in tables.semantic_nodes:
            if row["node_type"] == node_type:
                print(f"  {row['label']}")
    for edge_type in (
        "pathway_uses_design_variable",
        "pathway_requires_reporting_item",
    ):
        print(f"{edge_type} mapping:")
        mapping = sorted(
            (
                labels_by_id[row["source_id"]],
                labels_by_id[row["target_id"]],
            )
            for row in tables.semantic_edges
            if row["edge_type"] == edge_type
        )
        for source_label, target_label in mapping:
            print(f"  {source_label} -> {target_label}")
    print(f"Integrated nodes: {len(tables.integrated_nodes)}")
    print(f"Integrated edges: {len(tables.integrated_edges)}")
    print("Missing integrated endpoints: 0")
    for path in (
        paths.semantic_nodes,
        paths.semantic_edges,
        paths.integrated_nodes,
        paths.integrated_edges,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Tests for HydroKG graph content audits."""

import csv
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


def load_audits():
    tables = load_graph_tables(NODES_PATH, EDGES_PATH)
    return (
        tables,
        top_nodes_by_total_degree(tables.nodes, tables.edges),
        audit_node_labels(tables.nodes),
        summarize_degree_by_edge_type(tables.edges),
    )


def test_top_node_degree_table_is_not_empty() -> None:
    _, top_nodes, _, _ = load_audits()

    assert top_nodes
    assert int(top_nodes[0]["total_degree"]) > 0


def test_all_reported_node_ids_exist_in_nodes() -> None:
    tables, top_nodes, _, _ = load_audits()
    node_ids = {node["node_id"] for node in tables.nodes}

    assert all(row["node_id"] in node_ids for row in top_nodes)


def test_duplicate_label_audit_runs_without_error() -> None:
    _, _, label_audit, _ = load_audits()

    assert label_audit
    assert all("duplicate_label_group_count" in row for row in label_audit)


def test_empty_label_count_is_zero() -> None:
    _, _, label_audit, _ = load_audits()

    assert sum(int(row["empty_label_count"]) for row in label_audit) == 0


def test_graph_audit_can_be_written(tmp_path: Path) -> None:
    _, top_nodes, label_audit, edge_summary = load_audits()
    paths = write_graph_audit(
        top_nodes=top_nodes,
        label_audit=label_audit,
        edge_type_degree_summary=edge_summary,
        output_directory=tmp_path,
    )

    assert paths.top_nodes_by_degree.is_file()
    assert paths.node_label_audit.is_file()
    assert paths.edge_type_degree_summary.is_file()
    with paths.top_nodes_by_degree.open(
        encoding="utf-8", newline=""
    ) as handle:
        assert next(csv.DictReader(handle))["node_id"] in {
            row["node_id"] for row in top_nodes
        }

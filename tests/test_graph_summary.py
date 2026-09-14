"""Tests for HydroKG graph table summaries."""

import csv
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


def load_summaries():
    tables = load_graph_tables(NODES_PATH, EDGES_PATH)
    return (
        tables,
        summarize_node_types(tables.nodes),
        summarize_edge_types(tables.edges),
        check_graph_integrity(tables.nodes, tables.edges),
    )


def test_node_type_counts_sum_to_total_node_count() -> None:
    tables, node_counts, _, integrity = load_summaries()

    assert sum(row["count"] for row in node_counts) == len(tables.nodes)
    assert sum(row["count"] for row in node_counts) == (
        integrity.total_node_count
    )


def test_edge_type_counts_sum_to_total_edge_count() -> None:
    tables, _, edge_counts, integrity = load_summaries()

    assert sum(row["count"] for row in edge_counts) == len(tables.edges)
    assert sum(row["count"] for row in edge_counts) == (
        integrity.total_edge_count
    )


def test_device_record_count_is_159() -> None:
    _, _, _, integrity = load_summaries()

    assert integrity.device_record_node_count == 159


def test_missing_edge_source_ids_is_zero() -> None:
    _, _, _, integrity = load_summaries()

    assert integrity.missing_edge_source_id_count == 0


def test_missing_edge_target_ids_is_zero() -> None:
    _, _, _, integrity = load_summaries()

    assert integrity.missing_edge_target_id_count == 0


def test_graph_summary_can_be_written(tmp_path: Path) -> None:
    _, node_counts, edge_counts, integrity = load_summaries()
    paths = write_graph_summary(
        node_type_counts=node_counts,
        edge_type_counts=edge_counts,
        integrity=integrity,
        output_directory=tmp_path,
    )

    assert paths.node_type_counts.is_file()
    assert paths.edge_type_counts.is_file()
    assert paths.integrity_summary.is_file()

    with paths.integrity_summary.open(
        encoding="utf-8", newline=""
    ) as handle:
        summary = next(csv.DictReader(handle))
    assert summary["device_record_node_count"] == "159"

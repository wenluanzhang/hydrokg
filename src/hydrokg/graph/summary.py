"""Summarize and check the integrity of HydroKG graph tables."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

NODE_TYPE_COUNTS_FILENAME = "hydrokg_node_type_counts.csv"
EDGE_TYPE_COUNTS_FILENAME = "hydrokg_edge_type_counts.csv"
INTEGRITY_SUMMARY_FILENAME = "hydrokg_graph_integrity_summary.csv"


@dataclass(frozen=True)
class LoadedGraphTables:
    """Node and edge rows loaded from CSV files."""

    nodes: tuple[dict[str, str], ...]
    edges: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class GraphIntegritySummary:
    """Integrity measurements for node and edge tables."""

    total_node_count: int
    total_edge_count: int
    unique_node_id_count: int
    unique_edge_id_count: int
    missing_edge_source_id_count: int
    missing_edge_target_id_count: int
    device_record_node_count: int

    def as_row(self) -> dict[str, int]:
        """Return the summary in CSV-ready column order."""
        return {
            "total_node_count": self.total_node_count,
            "total_edge_count": self.total_edge_count,
            "unique_node_id_count": self.unique_node_id_count,
            "unique_edge_id_count": self.unique_edge_id_count,
            "missing_edge_source_id_count": (
                self.missing_edge_source_id_count
            ),
            "missing_edge_target_id_count": (
                self.missing_edge_target_id_count
            ),
            "device_record_node_count": self.device_record_node_count,
        }


@dataclass(frozen=True)
class GraphSummaryPaths:
    """Paths written by :func:`write_graph_summary`."""

    node_type_counts: Path
    edge_type_counts: Path
    integrity_summary: Path


def load_graph_tables(
    nodes_path: Path | str,
    edges_path: Path | str,
) -> LoadedGraphTables:
    """Load node and edge CSV files."""
    return LoadedGraphTables(
        nodes=_load_csv(nodes_path),
        edges=_load_csv(edges_path),
    )


def summarize_node_types(
    nodes: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str | int], ...]:
    """Count nodes by node type."""
    counts = Counter(node["node_type"] for node in nodes)
    return tuple(
        {"node_type": node_type, "count": counts[node_type]}
        for node_type in sorted(counts)
    )


def summarize_edge_types(
    edges: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str | int], ...]:
    """Count edges by edge type."""
    counts = Counter(edge["edge_type"] for edge in edges)
    return tuple(
        {"edge_type": edge_type, "count": counts[edge_type]}
        for edge_type in sorted(counts)
    )


def check_graph_integrity(
    nodes: Sequence[Mapping[str, str]],
    edges: Sequence[Mapping[str, str]],
) -> GraphIntegritySummary:
    """Calculate identifier and endpoint integrity measurements."""
    node_ids = {node["node_id"] for node in nodes}
    edge_ids = {edge["edge_id"] for edge in edges}
    return GraphIntegritySummary(
        total_node_count=len(nodes),
        total_edge_count=len(edges),
        unique_node_id_count=len(node_ids),
        unique_edge_id_count=len(edge_ids),
        missing_edge_source_id_count=sum(
            edge["source_id"] not in node_ids for edge in edges
        ),
        missing_edge_target_id_count=sum(
            edge["target_id"] not in node_ids for edge in edges
        ),
        device_record_node_count=sum(
            node["node_type"] == "DeviceRecord" for node in nodes
        ),
    )


def write_graph_summary(
    node_type_counts: Sequence[Mapping[str, str | int]],
    edge_type_counts: Sequence[Mapping[str, str | int]],
    integrity: GraphIntegritySummary,
    output_directory: Path | str,
) -> GraphSummaryPaths:
    """Write graph type counts and integrity measurements."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    node_counts_path = output_directory / NODE_TYPE_COUNTS_FILENAME
    edge_counts_path = output_directory / EDGE_TYPE_COUNTS_FILENAME
    integrity_path = output_directory / INTEGRITY_SUMMARY_FILENAME

    _write_csv(node_counts_path, ("node_type", "count"), node_type_counts)
    _write_csv(edge_counts_path, ("edge_type", "count"), edge_type_counts)
    _write_csv(
        integrity_path,
        tuple(integrity.as_row()),
        (integrity.as_row(),),
    )
    return GraphSummaryPaths(
        node_type_counts=node_counts_path,
        edge_type_counts=edge_counts_path,
        integrity_summary=integrity_path,
    )


def _load_csv(path: Path | str) -> tuple[dict[str, str], ...]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle))


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

"""Audit the content of generated HydroKG graph tables."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Mapping, Sequence

TOP_NODES_FILENAME = "hydrokg_top_nodes_by_degree.csv"
NODE_LABEL_AUDIT_FILENAME = "hydrokg_node_label_audit.csv"
EDGE_TYPE_DEGREE_SUMMARY_FILENAME = "hydrokg_edge_type_degree_summary.csv"


@dataclass(frozen=True)
class LoadedGraphTables:
    """Node and edge rows loaded from CSV files."""

    nodes: tuple[dict[str, str], ...]
    edges: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class GraphAuditPaths:
    """Paths written by :func:`write_graph_audit`."""

    top_nodes_by_degree: Path
    node_label_audit: Path
    edge_type_degree_summary: Path


def load_graph_tables(
    nodes_path: Path | str,
    edges_path: Path | str,
) -> LoadedGraphTables:
    """Load node and edge CSV files."""
    return LoadedGraphTables(
        nodes=_load_csv(nodes_path),
        edges=_load_csv(edges_path),
    )


def compute_node_degrees(
    nodes: Sequence[Mapping[str, str]],
    edges: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str | int], ...]:
    """Compute incoming, outgoing, and total degree for every node."""
    node_by_id = {node["node_id"]: node for node in nodes}
    in_degree = Counter[str]()
    out_degree = Counter[str]()

    for edge in edges:
        source_id = edge["source_id"]
        target_id = edge["target_id"]
        missing_ids = {
            node_id
            for node_id in (source_id, target_id)
            if node_id not in node_by_id
        }
        if missing_ids:
            missing = ", ".join(sorted(missing_ids))
            raise ValueError(f"Edges reference unknown node_ids: {missing}")
        out_degree[source_id] += 1
        in_degree[target_id] += 1

    return tuple(
        {
            "node_id": node_id,
            "node_type": node["node_type"],
            "label": node["label"],
            "in_degree": in_degree[node_id],
            "out_degree": out_degree[node_id],
            "total_degree": in_degree[node_id] + out_degree[node_id],
        }
        for node_id, node in node_by_id.items()
    )


def top_nodes_by_total_degree(
    nodes: Sequence[Mapping[str, str]],
    edges: Sequence[Mapping[str, str]],
    limit: int = 25,
) -> tuple[dict[str, str | int], ...]:
    """Return the highest-degree nodes, sorted deterministically."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    degrees = compute_node_degrees(nodes, edges)
    return tuple(
        sorted(
            degrees,
            key=lambda row: (-int(row["total_degree"]), str(row["node_id"])),
        )[:limit]
    )


def audit_node_labels(
    nodes: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str | int], ...]:
    """Count empty, whitespace-padded, and duplicate labels by node type."""
    nodes_by_type: dict[str, list[Mapping[str, str]]] = {}
    for node in nodes:
        nodes_by_type.setdefault(node["node_type"], []).append(node)

    rows = []
    for node_type in sorted(nodes_by_type):
        typed_nodes = nodes_by_type[node_type]
        labels = [node.get("label", "") for node in typed_nodes]
        normalized_nonempty_labels = [
            label.strip() for label in labels if label.strip()
        ]
        label_counts = Counter(normalized_nonempty_labels)
        duplicate_labels = {
            label: count for label, count in label_counts.items() if count > 1
        }
        rows.append(
            {
                "node_type": node_type,
                "node_count": len(typed_nodes),
                "empty_label_count": sum(not label.strip() for label in labels),
                "whitespace_label_count": sum(
                    label != label.strip() for label in labels
                ),
                "duplicate_label_group_count": len(duplicate_labels),
                "duplicate_label_node_count": sum(duplicate_labels.values()),
            }
        )
    return tuple(rows)


def summarize_degree_by_edge_type(
    edges: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str | int | float], ...]:
    """Summarize endpoint degree within each edge type."""
    edges_by_type: dict[str, list[Mapping[str, str]]] = {}
    for edge in edges:
        edges_by_type.setdefault(edge["edge_type"], []).append(edge)

    rows = []
    for edge_type in sorted(edges_by_type):
        typed_edges = edges_by_type[edge_type]
        degrees = Counter[str]()
        for edge in typed_edges:
            degrees[edge["source_id"]] += 1
            degrees[edge["target_id"]] += 1
        degree_values = list(degrees.values())
        rows.append(
            {
                "edge_type": edge_type,
                "edge_count": len(typed_edges),
                "incident_node_count": len(degrees),
                "min_degree": min(degree_values),
                "max_degree": max(degree_values),
                "mean_degree": round(mean(degree_values), 6),
                "median_degree": float(median(degree_values)),
            }
        )
    return tuple(rows)


def write_graph_audit(
    top_nodes: Sequence[Mapping[str, object]],
    label_audit: Sequence[Mapping[str, object]],
    edge_type_degree_summary: Sequence[Mapping[str, object]],
    output_directory: Path | str,
) -> GraphAuditPaths:
    """Write all graph content audit tables."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = GraphAuditPaths(
        top_nodes_by_degree=output_directory / TOP_NODES_FILENAME,
        node_label_audit=output_directory / NODE_LABEL_AUDIT_FILENAME,
        edge_type_degree_summary=(
            output_directory / EDGE_TYPE_DEGREE_SUMMARY_FILENAME
        ),
    )
    _write_csv(
        paths.top_nodes_by_degree,
        (
            "node_id",
            "node_type",
            "label",
            "in_degree",
            "out_degree",
            "total_degree",
        ),
        top_nodes,
    )
    _write_csv(
        paths.node_label_audit,
        (
            "node_type",
            "node_count",
            "empty_label_count",
            "whitespace_label_count",
            "duplicate_label_group_count",
            "duplicate_label_node_count",
        ),
        label_audit,
    )
    _write_csv(
        paths.edge_type_degree_summary,
        (
            "edge_type",
            "edge_count",
            "incident_node_count",
            "min_degree",
            "max_degree",
            "mean_degree",
            "median_degree",
        ),
        edge_type_degree_summary,
    )
    return paths


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

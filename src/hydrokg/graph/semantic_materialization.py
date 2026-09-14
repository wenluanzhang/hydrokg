"""Materialize HydroKG semantic concepts into node and edge tables."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from hydrokg.graph.tables import EDGE_COLUMNS, NODE_COLUMNS

SEMANTIC_NODE_TYPES = (
    "RBin",
    "PowerBin",
    "Pathway",
    "WarningFlag",
    "DesignVariable",
    "ReportingItem",
)
SEMANTIC_NODES_FILENAME = "hydrokg_semantic_nodes.csv"
SEMANTIC_EDGES_FILENAME = "hydrokg_semantic_edges.csv"
INTEGRATED_NODES_FILENAME = "hydrokg_integrated_nodes.csv"
INTEGRATED_EDGES_FILENAME = "hydrokg_integrated_edges.csv"


@dataclass(frozen=True)
class SemanticGraphTables:
    """Semantic additions and their integration with the base graph."""

    semantic_nodes: tuple[dict[str, str], ...]
    semantic_edges: tuple[dict[str, str], ...]
    integrated_nodes: tuple[dict[str, str], ...]
    integrated_edges: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class SemanticGraphPaths:
    """Paths written by :func:`write_semantic_graph_tables`."""

    semantic_nodes: Path
    semantic_edges: Path
    integrated_nodes: Path
    integrated_edges: Path


def load_csv_rows(path: Path | str) -> tuple[dict[str, str], ...]:
    """Load CSV rows while preserving their existing string values."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def load_json(path: Path | str) -> dict[str, Any]:
    """Load a JSON object."""
    with Path(path).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def deterministic_semantic_node_id(
    node_type: str,
    canonical_label: str,
) -> str:
    """Return a stable ID derived from semantic type and canonical label."""
    normalized_type = _snake_case(node_type)
    normalized_label = canonical_label.strip()
    digest = hashlib.sha256(
        f"{node_type}\0{normalized_label}".encode("utf-8")
    ).hexdigest()[:12]
    return f"semantic_{normalized_type}_{digest}"


def build_semantic_graph_tables(
    base_nodes: Sequence[Mapping[str, str]],
    base_edges: Sequence[Mapping[str, str]],
    device_rows: Sequence[Mapping[str, str]],
    pathway_matches: Sequence[Mapping[str, str]],
    semantic_layer: Mapping[str, Any],
    pathway_rules: Mapping[str, Any],
) -> SemanticGraphTables:
    """Build semantic tables and merge them with existing base rows."""
    _require_schema(base_nodes, NODE_COLUMNS, "Base node table")
    _require_schema(base_edges, EDGE_COLUMNS, "Base edge table")
    _require_columns(
        device_rows,
        (
            "device_record_id",
            "r_bin",
            "estimated_power_available_flag",
            "high_power_flag",
        ),
        "R-centered device table",
    )
    _require_columns(
        pathway_matches,
        (
            "device_record_id",
            "rule_id",
            "activated_pathway",
            "warning_flags_json",
        ),
        "Device pathway matches",
    )

    concepts = _semantic_concepts(semantic_layer)
    semantic_nodes = _build_semantic_nodes(concepts)
    concept_ids = {
        (row["node_type"], row["label"]): row["node_id"]
        for row in semantic_nodes
    }
    rules = _rules_by_id(pathway_rules)
    base_node_ids = {row["node_id"] for row in base_nodes}

    edge_provenance: dict[
        tuple[str, str, str], tuple[str, str, dict[str, Any]]
    ] = {}
    for row in device_rows:
        device_id = row["device_record_id"].strip()
        if device_id not in base_node_ids:
            raise ValueError(
                f"Device record is missing from base nodes: {device_id}"
            )
        r_bin = row["r_bin"].strip()
        _add_semantic_edge(
            edge_provenance,
            device_id,
            "device_has_r_bin",
            _concept_id(concept_ids, "RBin", r_bin),
            "r_bin",
            r_bin,
        )
        power_bin = _power_bin(row)
        _add_semantic_edge(
            edge_provenance,
            device_id,
            "device_has_power_bin",
            _concept_id(concept_ids, "PowerBin", power_bin),
            "derived_power_bin",
            power_bin,
        )

    for match in pathway_matches:
        device_id = match["device_record_id"].strip()
        if device_id not in base_node_ids:
            raise ValueError(
                f"Pathway match device is missing from base nodes: {device_id}"
            )
        rule_id = match["rule_id"].strip()
        try:
            rule = rules[rule_id]
        except KeyError as error:
            raise ValueError(f"Unknown pathway rule: {rule_id}") from error

        if rule.get("rule_type") != "warning_only":
            pathway = _optional_text(match.get("activated_pathway"))
            if pathway:
                _add_semantic_edge(
                    edge_provenance,
                    device_id,
                    "device_activates_pathway",
                    _concept_id(concept_ids, "Pathway", pathway),
                    "rule_id",
                    rule_id,
                )

        for warning in _json_string_list(match["warning_flags_json"]):
            _add_semantic_edge(
                edge_provenance,
                device_id,
                "device_has_warning_flag",
                _concept_id(concept_ids, "WarningFlag", warning),
                "rule_id",
                rule_id,
            )

    for rule_id, rule in rules.items():
        pathway = _optional_text(rule.get("activates_pathway"))
        if rule.get("rule_type") == "warning_only" or not pathway:
            continue
        pathway_id = _concept_id(concept_ids, "Pathway", pathway)
        for design_variable in _string_list(
            rule.get("design_variables"),
            f"{rule_id}.design_variables",
        ):
            _add_semantic_edge(
                edge_provenance,
                pathway_id,
                "pathway_uses_design_variable",
                _concept_id(
                    concept_ids,
                    "DesignVariable",
                    design_variable,
                ),
                "rule_id",
                rule_id,
            )
        for reporting_item in _string_list(
            rule.get("required_reporting_items"),
            f"{rule_id}.required_reporting_items",
        ):
            _add_semantic_edge(
                edge_provenance,
                pathway_id,
                "pathway_requires_reporting_item",
                _concept_id(
                    concept_ids,
                    "ReportingItem",
                    reporting_item,
                ),
                "rule_id",
                rule_id,
            )

    semantic_edges = _build_semantic_edges(edge_provenance)
    integrated_nodes = tuple(
        sorted(
            (dict(row) for row in (*base_nodes, *semantic_nodes)),
            key=lambda row: row["node_id"],
        )
    )
    integrated_edges = tuple(
        sorted(
            (dict(row) for row in (*base_edges, *semantic_edges)),
            key=lambda row: row["edge_id"],
        )
    )
    missing_endpoints = find_missing_edge_endpoints(
        integrated_nodes,
        integrated_edges,
    )
    if missing_endpoints:
        missing = ", ".join(missing_endpoints)
        raise ValueError(f"Integrated edges have missing endpoints: {missing}")

    return SemanticGraphTables(
        semantic_nodes=semantic_nodes,
        semantic_edges=semantic_edges,
        integrated_nodes=integrated_nodes,
        integrated_edges=integrated_edges,
    )


def materialize_semantic_graph(
    *,
    base_nodes_path: Path | str,
    base_edges_path: Path | str,
    device_table_path: Path | str,
    pathway_matches_path: Path | str,
    semantic_layer_path: Path | str,
    pathway_rules_path: Path | str,
) -> SemanticGraphTables:
    """Load all materialization inputs and build semantic graph tables."""
    return build_semantic_graph_tables(
        base_nodes=load_csv_rows(base_nodes_path),
        base_edges=load_csv_rows(base_edges_path),
        device_rows=load_csv_rows(device_table_path),
        pathway_matches=load_csv_rows(pathway_matches_path),
        semantic_layer=load_json(semantic_layer_path),
        pathway_rules=load_json(pathway_rules_path),
    )


def find_missing_edge_endpoints(
    nodes: Sequence[Mapping[str, str]],
    edges: Sequence[Mapping[str, str]],
) -> tuple[str, ...]:
    """Return sorted endpoint IDs that do not occur in the node table."""
    node_ids = {row["node_id"] for row in nodes}
    endpoints = {
        endpoint
        for row in edges
        for endpoint in (row["source_id"], row["target_id"])
    }
    return tuple(sorted(endpoints - node_ids))


def write_semantic_graph_tables(
    tables: SemanticGraphTables,
    output_directory: Path | str,
) -> SemanticGraphPaths:
    """Write semantic and integrated tables to an output directory."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = SemanticGraphPaths(
        semantic_nodes=output_directory / SEMANTIC_NODES_FILENAME,
        semantic_edges=output_directory / SEMANTIC_EDGES_FILENAME,
        integrated_nodes=output_directory / INTEGRATED_NODES_FILENAME,
        integrated_edges=output_directory / INTEGRATED_EDGES_FILENAME,
    )
    _write_csv(paths.semantic_nodes, NODE_COLUMNS, tables.semantic_nodes)
    _write_csv(paths.semantic_edges, EDGE_COLUMNS, tables.semantic_edges)
    _write_csv(paths.integrated_nodes, NODE_COLUMNS, tables.integrated_nodes)
    _write_csv(paths.integrated_edges, EDGE_COLUMNS, tables.integrated_edges)
    return paths


def _semantic_concepts(
    semantic_layer: Mapping[str, Any],
) -> dict[str, Mapping[str, Mapping[str, Any]]]:
    concept_types = semantic_layer.get("concept_types")
    if not isinstance(concept_types, Mapping):
        raise ValueError("Semantic layer must contain concept_types")
    selected: dict[str, Mapping[str, Mapping[str, Any]]] = {}
    for node_type in SEMANTIC_NODE_TYPES:
        definition = concept_types.get(node_type)
        if not isinstance(definition, Mapping):
            raise ValueError(f"Semantic layer is missing {node_type}")
        concepts = definition.get("concepts")
        if not isinstance(concepts, Mapping):
            raise ValueError(f"{node_type} must contain concepts")
        selected[node_type] = concepts
    return selected


def _build_semantic_nodes(
    concepts: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for node_type in SEMANTIC_NODE_TYPES:
        for canonical_label, definition in concepts[node_type].items():
            properties = {
                key: definition[key]
                for key in ("description", "label")
                if key in definition
            }
            rows.append(
                {
                    "node_id": deterministic_semantic_node_id(
                        node_type,
                        canonical_label,
                    ),
                    "node_type": node_type,
                    "label": canonical_label,
                    "source_column": "semantic_layer",
                    "source_value": canonical_label,
                    "properties_json": _to_json(properties),
                }
            )
    return tuple(sorted(rows, key=lambda row: row["node_id"]))


def _rules_by_id(
    pathway_rules: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rules = pathway_rules.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Pathway rules must contain a rules list")
    result: dict[str, Mapping[str, Any]] = {}
    for rule in rules:
        if not isinstance(rule, Mapping) or not isinstance(
            rule.get("rule_id"), str
        ):
            raise ValueError("Every pathway rule must have a string rule_id")
        rule_id = rule["rule_id"]
        if rule_id in result:
            raise ValueError(f"Duplicate pathway rule ID: {rule_id}")
        result[rule_id] = rule
    return result


def _power_bin(row: Mapping[str, str]) -> str:
    if not _is_true(row.get("estimated_power_available_flag")):
        return "missing_power"
    return "high_power" if _is_true(row.get("high_power_flag")) else (
        "non_high_power"
    )


def _concept_id(
    concept_ids: Mapping[tuple[str, str], str],
    node_type: str,
    canonical_label: str,
) -> str:
    try:
        return concept_ids[(node_type, canonical_label)]
    except KeyError as error:
        raise ValueError(
            f"Unknown {node_type} concept: {canonical_label}"
        ) from error


def _add_semantic_edge(
    edges: dict[tuple[str, str, str], tuple[str, str, dict[str, Any]]],
    source_id: str,
    edge_type: str,
    target_id: str,
    source_column: str,
    source_value: str,
) -> None:
    key = (source_id, edge_type, target_id)
    if key not in edges:
        edges[key] = (
            source_column,
            source_value,
            {"source_values": [source_value]},
        )
        return
    existing_column, _, properties = edges[key]
    values = properties["source_values"]
    if source_value not in values:
        values.append(source_value)
        values.sort()
    edges[key] = (existing_column, "|".join(values), properties)


def _build_semantic_edges(
    provenance: Mapping[
        tuple[str, str, str], tuple[str, str, Mapping[str, Any]]
    ],
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for source_id, edge_type, target_id in sorted(provenance):
        source_column, source_value, properties = provenance[
            (source_id, edge_type, target_id)
        ]
        digest = hashlib.sha256(
            f"{source_id}\0{edge_type}\0{target_id}".encode("utf-8")
        ).hexdigest()[:16]
        rows.append(
            {
                "edge_id": f"semantic_edge_{digest}",
                "source_id": source_id,
                "target_id": target_id,
                "edge_type": edge_type,
                "source_column": source_column,
                "source_value": source_value,
                "properties_json": _to_json(properties),
            }
        )
    return tuple(sorted(rows, key=lambda row: row["edge_id"]))


def _json_string_list(value: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON list: {value}") from error
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise ValueError(f"Expected a JSON list of strings: {value}")
    return tuple(parsed)


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"{field_name} must be a list of strings")
    return tuple(value)


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_true(value: Any) -> bool:
    return _optional_text(value).lower() in {"1", "true", "yes"}


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _to_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_schema(
    rows: Sequence[Mapping[str, str]],
    columns: Sequence[str],
    table_name: str,
) -> None:
    if not rows:
        raise ValueError(f"{table_name} must not be empty")
    actual = tuple(rows[0].keys())
    if actual != tuple(columns):
        raise ValueError(
            f"{table_name} schema is {actual}, expected {tuple(columns)}"
        )


def _require_columns(
    rows: Sequence[Mapping[str, str]],
    columns: Sequence[str],
    table_name: str,
) -> None:
    if not rows:
        raise ValueError(f"{table_name} must not be empty")
    missing = sorted(set(columns) - set(rows[0]))
    if missing:
        raise ValueError(
            f"{table_name} is missing required columns: {', '.join(missing)}"
        )


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

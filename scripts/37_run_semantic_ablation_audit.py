"""Run a deterministic semantic-layer ablation audit for the canonical query."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TABLES_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"
BASE_NODES_PATH = REPOSITORY_ROOT / "data" / "processed" / "hydrokg_nodes.csv"
BASE_EDGES_PATH = REPOSITORY_ROOT / "data" / "processed" / "hydrokg_edges.csv"
SEMANTIC_NODES_PATH = TABLES_DIRECTORY / "hydrokg_semantic_nodes.csv"
SEMANTIC_EDGES_PATH = TABLES_DIRECTORY / "hydrokg_semantic_edges.csv"
CONFIG_PATH = REPOSITORY_ROOT / "configs" / "queries" / "hydrokg_graph_queries_v1.json"
OUTPUT_PATH = TABLES_DIRECTORY / "hydrokg_semantic_ablation_audit.csv"
REQUESTED_QUERY_ID = "polymer_film_low_r_high_power_context"
CONFIG_QUERY_ID = "canonical_polymer_film_low_r_high_power"
OUTPUT_COLUMNS = (
    "stage_index",
    "stage_name",
    "added_node_types_json",
    "added_relation_types_json",
    "supported_constraint_count",
    "total_constraint_count",
    "candidate_device_count",
    "candidate_device_ids_json",
    "explicit_constraint_path_count",
    "candidate_devices_with_warning_count",
    "reachable_warning_flags_json",
    "reachable_design_variables_json",
    "reachable_reporting_items_json",
)
STAGES = (
    {
        "stage_name": "base_graph",
        "node_types": ("MaterialClass", "StructureClass", "Mechanism"),
        "relation_types": (
            "has_material_class",
            "has_structure_class",
            "has_mechanism",
        ),
    },
    {
        "stage_name": "performance_semantics",
        "node_types": ("RBin", "PowerBin"),
        "relation_types": ("device_has_r_bin", "device_has_power_bin"),
    },
    {
        "stage_name": "pathway_semantics",
        "node_types": ("Pathway",),
        "relation_types": ("device_activates_pathway",),
    },
    {
        "stage_name": "warning_semantics",
        "node_types": ("WarningFlag",),
        "relation_types": ("device_has_warning_flag",),
    },
    {
        "stage_name": "design_reporting_semantics",
        "node_types": ("DesignVariable", "ReportingItem"),
        "relation_types": (
            "pathway_uses_design_variable",
            "pathway_requires_reporting_item",
        ),
    },
)


@dataclass(frozen=True)
class Node:
    """Graph node used by the ablation audit."""

    node_id: str
    node_type: str
    label: str


@dataclass(frozen=True)
class Edge:
    """Graph edge used by the ablation audit."""

    source_id: str
    target_id: str
    edge_type: str


@dataclass(frozen=True)
class QueryConstraint:
    """One required query concept."""

    node_type: str
    label: str
    relation_type: str


@dataclass(frozen=True)
class AuditRow:
    """One semantic-ablation audit row."""

    stage_index: int
    stage_name: str
    added_node_types: tuple[str, ...]
    added_relation_types: tuple[str, ...]
    supported_constraint_count: int
    total_constraint_count: int
    candidate_device_ids: tuple[str, ...]
    explicit_constraint_path_count: int
    candidate_devices_with_warning_count: int
    reachable_warning_flags: tuple[str, ...]
    reachable_design_variables: tuple[str, ...]
    reachable_reporting_items: tuple[str, ...]

    @property
    def candidate_device_count(self) -> int:
        return len(self.candidate_device_ids)


def main() -> int:
    """Run and write the semantic ablation audit."""
    rows = run_ablation_audit(
        _load_csv(BASE_NODES_PATH),
        _load_csv(BASE_EDGES_PATH),
        _load_csv(SEMANTIC_NODES_PATH),
        _load_csv(SEMANTIC_EDGES_PATH),
        _load_json(CONFIG_PATH),
    )
    write_audit_csv(OUTPUT_PATH, rows)

    print("Semantic ablation audit:")
    for row in rows:
        print(
            f"  {row.stage_index}. {row.stage_name}: "
            f"constraints={row.supported_constraint_count}/"
            f"{row.total_constraint_count}, "
            f"candidates={row.candidate_device_count}, "
            f"paths={row.explicit_constraint_path_count}, "
            f"warnings={row.candidate_devices_with_warning_count}"
        )
    print(f"Wrote: {OUTPUT_PATH.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


def run_ablation_audit(
    base_node_rows: Sequence[Mapping[str, str]],
    base_edge_rows: Sequence[Mapping[str, str]],
    semantic_node_rows: Sequence[Mapping[str, str]],
    semantic_edge_rows: Sequence[Mapping[str, str]],
    query_config: Mapping[str, object],
) -> tuple[AuditRow, ...]:
    """Compute cumulative semantic-layer audit rows."""
    nodes = _load_nodes((*base_node_rows, *semantic_node_rows))
    base_edges = _load_edges(base_edge_rows)
    semantic_edges = _load_edges(semantic_edge_rows)
    constraints = _load_query_constraints(query_config)
    device_ids = tuple(
        sorted(node.node_id for node in nodes.values() if node.node_type == "DeviceRecord")
    )

    available_node_types: set[str] = set()
    available_relation_types: set[str] = set()
    audit_rows: list[AuditRow] = []
    for stage_index, stage in enumerate(STAGES, start=1):
        added_node_types = tuple(stage["node_types"])
        added_relation_types = tuple(stage["relation_types"])
        available_node_types.update(added_node_types)
        available_relation_types.update(added_relation_types)
        available_edges = tuple(
            edge for edge in (*base_edges, *semantic_edges)
            if edge.edge_type in available_relation_types
        )
        supported_constraints = tuple(
            constraint for constraint in constraints
            if (
                constraint.node_type in available_node_types
                and constraint.relation_type in available_relation_types
            )
        )
        candidate_device_ids = _candidate_devices(
            device_ids,
            nodes,
            available_edges,
            supported_constraints,
        )
        explicit_constraint_path_count = _explicit_constraint_path_count(
            candidate_device_ids,
            nodes,
            available_edges,
            supported_constraints,
        )
        warning_context = _warning_context(
            candidate_device_ids,
            nodes,
            available_edges,
            "WarningFlag" in available_node_types,
        )
        design_variables, reporting_items = _design_reporting_context(
            candidate_device_ids,
            nodes,
            available_edges,
            {"DesignVariable", "ReportingItem"}.issubset(available_node_types),
        )
        audit_rows.append(
            AuditRow(
                stage_index=stage_index,
                stage_name=str(stage["stage_name"]),
                added_node_types=added_node_types,
                added_relation_types=added_relation_types,
                supported_constraint_count=len(supported_constraints),
                total_constraint_count=len(constraints),
                candidate_device_ids=candidate_device_ids,
                explicit_constraint_path_count=explicit_constraint_path_count,
                candidate_devices_with_warning_count=warning_context[0],
                reachable_warning_flags=warning_context[1],
                reachable_design_variables=design_variables,
                reachable_reporting_items=reporting_items,
            )
        )
    return tuple(audit_rows)


def write_audit_csv(path: Path, rows: Sequence[AuditRow]) -> None:
    """Write audit rows in deterministic long-form CSV format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "stage_index": row.stage_index,
                    "stage_name": row.stage_name,
                    "added_node_types_json": _json_list(row.added_node_types),
                    "added_relation_types_json": _json_list(row.added_relation_types),
                    "supported_constraint_count": row.supported_constraint_count,
                    "total_constraint_count": row.total_constraint_count,
                    "candidate_device_count": row.candidate_device_count,
                    "candidate_device_ids_json": _json_list(row.candidate_device_ids),
                    "explicit_constraint_path_count": (
                        row.explicit_constraint_path_count
                    ),
                    "candidate_devices_with_warning_count": (
                        row.candidate_devices_with_warning_count
                    ),
                    "reachable_warning_flags_json": _json_list(
                        row.reachable_warning_flags
                    ),
                    "reachable_design_variables_json": _json_list(
                        row.reachable_design_variables
                    ),
                    "reachable_reporting_items_json": _json_list(
                        row.reachable_reporting_items
                    ),
                }
            )


def _candidate_devices(
    device_ids: Sequence[str],
    nodes: Mapping[str, Node],
    edges: Sequence[Edge],
    constraints: Sequence[QueryConstraint],
) -> tuple[str, ...]:
    candidates = set(device_ids)
    for constraint in constraints:
        matching_devices = {
            edge.source_id for edge in edges
            if (
                edge.edge_type == constraint.relation_type
                and edge.source_id in device_ids
                and edge.target_id in nodes
                and nodes[edge.target_id].node_type == constraint.node_type
                and nodes[edge.target_id].label == constraint.label
            )
        }
        candidates &= matching_devices
    return tuple(sorted(candidates))


def _explicit_constraint_path_count(
    candidate_device_ids: Sequence[str],
    nodes: Mapping[str, Node],
    edges: Sequence[Edge],
    constraints: Sequence[QueryConstraint],
) -> int:
    candidate_set = set(candidate_device_ids)
    count = 0
    for edge in edges:
        if edge.source_id not in candidate_set or edge.target_id not in nodes:
            continue
        target = nodes[edge.target_id]
        for constraint in constraints:
            if (
                edge.edge_type == constraint.relation_type
                and target.node_type == constraint.node_type
                and target.label == constraint.label
            ):
                count += 1
    return count


def _warning_context(
    candidate_device_ids: Sequence[str],
    nodes: Mapping[str, Node],
    edges: Sequence[Edge],
    enabled: bool,
) -> tuple[int, tuple[str, ...]]:
    if not enabled:
        return 0, ()
    candidate_set = set(candidate_device_ids)
    devices_with_warning: set[str] = set()
    flags: set[str] = set()
    for edge in edges:
        if (
            edge.edge_type == "device_has_warning_flag"
            and edge.source_id in candidate_set
            and edge.target_id in nodes
            and nodes[edge.target_id].node_type == "WarningFlag"
        ):
            devices_with_warning.add(edge.source_id)
            flags.add(nodes[edge.target_id].label)
    return len(devices_with_warning), tuple(sorted(flags))


def _design_reporting_context(
    candidate_device_ids: Sequence[str],
    nodes: Mapping[str, Node],
    edges: Sequence[Edge],
    enabled: bool,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not enabled:
        return (), ()
    candidate_set = set(candidate_device_ids)
    pathway_ids = {
        edge.target_id for edge in edges
        if (
            edge.edge_type == "device_activates_pathway"
            and edge.source_id in candidate_set
            and edge.target_id in nodes
            and nodes[edge.target_id].node_type == "Pathway"
        )
    }
    design_variables: set[str] = set()
    reporting_items: set[str] = set()
    for edge in edges:
        if edge.source_id not in pathway_ids or edge.target_id not in nodes:
            continue
        target = nodes[edge.target_id]
        if (
            edge.edge_type == "pathway_uses_design_variable"
            and target.node_type == "DesignVariable"
        ):
            design_variables.add(target.label)
        if (
            edge.edge_type == "pathway_requires_reporting_item"
            and target.node_type == "ReportingItem"
        ):
            reporting_items.add(target.label)
    return tuple(sorted(design_variables)), tuple(sorted(reporting_items))


def _load_query_constraints(
    query_config: Mapping[str, object],
) -> tuple[QueryConstraint, ...]:
    queries = query_config.get("queries")
    if not isinstance(queries, list):
        raise ValueError("Query config must contain a queries list")
    selected: Mapping[str, object] | None = None
    for query in queries:
        if not isinstance(query, dict):
            continue
        if query.get("query_id") in {REQUESTED_QUERY_ID, CONFIG_QUERY_ID}:
            selected = query
            break
    if selected is None:
        raise ValueError(f"Query not found: {REQUESTED_QUERY_ID}")
    required = selected.get("required_concepts")
    if not isinstance(required, list):
        raise ValueError("Selected query has no required_concepts list")
    constraints: list[QueryConstraint] = []
    for item in required:
        if not isinstance(item, dict):
            raise ValueError("Malformed query constraint")
        constraints.append(
            QueryConstraint(
                node_type=str(item["node_type"]),
                label=str(item["label"]),
                relation_type=str(item["relation_type"]),
            )
        )
    return tuple(constraints)


def _load_nodes(rows: Iterable[Mapping[str, str]]) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for row in rows:
        nodes[row["node_id"]] = Node(
            node_id=row["node_id"],
            node_type=row["node_type"],
            label=row["label"],
        )
    return nodes


def _load_edges(rows: Iterable[Mapping[str, str]]) -> tuple[Edge, ...]:
    return tuple(
        Edge(
            source_id=row["source_id"],
            target_id=row["target_id"],
            edge_type=row["edge_type"],
        )
        for row in rows
    )


def _json_list(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _load_csv(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def _load_json(path: Path) -> Mapping[str, object]:
    with path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return loaded


if __name__ == "__main__":
    raise SystemExit(main())

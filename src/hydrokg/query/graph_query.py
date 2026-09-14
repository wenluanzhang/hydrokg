"""Run deterministic multi-hop queries over integrated HydroKG tables."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from hydrokg.graph.tables import EDGE_COLUMNS, NODE_COLUMNS

DEVICE_MATCH_COLUMNS = (
    "query_id",
    "device_record_id",
    "paper_doi",
    "matched_concepts_json",
    "warning_flags_json",
    "path_count",
)
PATH_COLUMNS = (
    "query_id",
    "device_record_id",
    "path_id",
    "step_index",
    "traversal_source_node_id",
    "traversal_source_label",
    "relation_type",
    "traversal_target_node_id",
    "traversal_target_label",
    "traversal_direction",
)
DEVICE_MATCHES_FILENAME = "hydrokg_query_device_matches.csv"
QUERY_PATHS_FILENAME = "hydrokg_query_paths.csv"
NACL_DEVICE_MATCHES_FILENAME = (
    "hydrokg_query_nacl_primary_na_device_matches.csv"
)
NACL_QUERY_PATHS_FILENAME = "hydrokg_query_nacl_primary_na_paths.csv"
LOW_R_ROUTE_COLUMNS = (
    "query_id",
    "device_record_id",
    "paper_doi",
    "material_class",
    "structure_class",
    "power_bin",
    "pathways_json",
    "warning_flags_json",
    "route_id",
)
LOW_R_ROUTE_SUMMARY_COLUMNS = (
    "query_id",
    "route_id",
    "material_class",
    "structure_class",
    "matched_device_count",
    "high_power_device_count",
    "high_power_fraction",
    "pathway_device_count",
    "warning_device_count",
    "device_ids_json",
)
LOW_R_ROUTES_FILENAME = "hydrokg_query_low_r_routes.csv"
LOW_R_ROUTE_SUMMARY_FILENAME = "hydrokg_query_low_r_route_summary.csv"
HIGH_POWER_WARNING_CONTEXT_COLUMNS = (
    "query_id",
    "device_record_id",
    "paper_doi",
    "r_bin",
    "material_class",
    "structure_class",
    "pathways_json",
    "warning_flags_json",
    "warning_profile",
)
HIGH_POWER_WARNING_SUMMARY_COLUMNS = (
    "query_id",
    "warning_cohort",
    "matched_device_count",
    "low_R_device_count",
    "pathway_device_count",
    "device_ids_json",
)
HIGH_POWER_WARNING_CONTEXTS_FILENAME = (
    "hydrokg_query_high_power_warning_contexts.csv"
)
HIGH_POWER_WARNING_SUMMARY_FILENAME = (
    "hydrokg_query_high_power_warning_summary.csv"
)
REPORTING_WARNINGS = frozenset(
    {
        "missing_R_warning",
        "missing_humidity_warning",
        "incomplete_reporting_warning",
    }
)
ELECTROCHEMICAL_WARNING = "electrochemical_control_needed_warning"
WARNING_COHORTS = (
    "no_warning",
    "missing_R_warning",
    "missing_humidity_warning",
    "incomplete_reporting_warning",
    ELECTROCHEMICAL_WARNING,
)
PATHWAY_REQUIREMENT_COLUMNS = (
    "query_id",
    "pathway",
    "matched_device_count",
    "design_variables_json",
    "reporting_items_json",
    "device_ids_json",
)
SHARED_PATHWAY_CONCEPT_COLUMNS = (
    "query_id",
    "concept_type",
    "concept_label",
    "pathway_count",
    "pathways_json",
)
PATHWAY_REQUIREMENTS_FILENAME = "hydrokg_query_pathway_requirements.csv"
SHARED_PATHWAY_CONCEPTS_FILENAME = (
    "hydrokg_query_shared_pathway_concepts.csv"
)


@dataclass(frozen=True)
class IntegratedGraph:
    """Validated integrated node and edge rows."""

    nodes: tuple[dict[str, str], ...]
    edges: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class GraphQueryOutputs:
    """Device matches and explicit traversal path steps."""

    device_matches: tuple[dict[str, str], ...]
    paths: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class GraphQueryOutputPaths:
    """Paths written by :func:`write_graph_query_outputs`."""

    device_matches: Path
    paths: Path


@dataclass(frozen=True)
class MaterialStructureRouteOutputs:
    """Device-level material-structure routes and derived summaries."""

    routes: tuple[dict[str, str], ...]
    summaries: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class MaterialStructureRouteOutputPaths:
    """Paths written by :func:`write_material_structure_route_outputs`."""

    routes: Path
    summaries: Path


@dataclass(frozen=True)
class HighPowerWarningOutputs:
    """High-power device warning contexts and cohort summaries."""

    contexts: tuple[dict[str, str], ...]
    summaries: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class HighPowerWarningOutputPaths:
    """Paths written by :func:`write_high_power_warning_outputs`."""

    contexts: Path
    summaries: Path


@dataclass(frozen=True)
class PathwayRequirementOutputs:
    """Pathway requirements and concepts shared across pathways."""

    requirements: tuple[dict[str, str], ...]
    shared_concepts: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class PathwayRequirementOutputPaths:
    """Paths written by :func:`write_pathway_requirement_outputs`."""

    requirements: Path
    shared_concepts: Path


def load_integrated_graph(
    nodes_path: Path | str,
    edges_path: Path | str,
) -> IntegratedGraph:
    """Load and validate integrated graph CSV tables."""
    nodes = _load_csv(nodes_path)
    edges = _load_csv(edges_path)
    _require_schema(nodes, NODE_COLUMNS, "Integrated node table")
    _require_schema(edges, EDGE_COLUMNS, "Integrated edge table")

    node_ids = [row["node_id"] for row in nodes]
    edge_ids = [row["edge_id"] for row in edges]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("Integrated node IDs must be unique")
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError("Integrated edge IDs must be unique")

    known_nodes = set(node_ids)
    missing_endpoints = sorted(
        {
            endpoint
            for edge in edges
            for endpoint in (edge["source_id"], edge["target_id"])
            if endpoint not in known_nodes
        }
    )
    if missing_endpoints:
        raise ValueError(
            "Integrated edges reference missing nodes: "
            + ", ".join(missing_endpoints)
        )
    return IntegratedGraph(nodes=nodes, edges=edges)


def load_graph_query_config(path: Path | str) -> dict[str, Any]:
    """Load a graph-query configuration object."""
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict) or not isinstance(
        config.get("queries"), list
    ):
        raise ValueError("Graph query config must contain a queries list")
    return config


def run_graph_query(
    graph: IntegratedGraph,
    query: Mapping[str, Any],
) -> GraphQueryOutputs:
    """Run one configured query using only graph nodes and relations."""
    query_id = _required_text(query, "query_id")
    required = query.get("required_concepts")
    anchor = query.get("anchor")
    if not isinstance(required, list) or not required:
        raise ValueError("Query must contain required_concepts")
    if not isinstance(anchor, Mapping):
        raise ValueError("Query must contain an anchor concept")

    node_by_id = {row["node_id"]: row for row in graph.nodes}
    concept_by_identity = _index_concepts(graph.nodes)
    forward, reverse, stored_edges = _index_relations(graph.edges)
    resolved = tuple(
        _resolve_requirement(requirement, concept_by_identity)
        for requirement in required
    )
    resolved_anchor = _resolve_requirement(anchor, concept_by_identity)
    if resolved_anchor not in resolved:
        raise ValueError("Anchor must also occur in required_concepts")

    candidate_sets = [
        {
            source_id
            for source_id in reverse[
                (requirement["relation_type"], requirement["node_id"])
            ]
            if node_by_id[source_id]["node_type"] == "DeviceRecord"
        }
        for requirement in resolved
    ]
    device_ids = sorted(set.intersection(*candidate_sets))
    target_requirements = sorted(
        (
            requirement
            for requirement in resolved
            if requirement != resolved_anchor
        ),
        key=lambda item: (item["node_type"], item["label"]),
    )

    device_matches: list[dict[str, str]] = []
    path_rows: list[dict[str, str]] = []
    for device_id in device_ids:
        paper_doi = _paper_doi(
            device_id,
            reverse,
            node_by_id,
            stored_edges,
        )
        warning_flags = sorted(
            node_by_id[target_id]["label"]
            for target_id in forward[
                (device_id, "device_has_warning_flag")
            ]
            if node_by_id[target_id]["node_type"] == "WarningFlag"
        )
        matched_concepts = {
            requirement["node_type"]: requirement["label"]
            for requirement in sorted(
                resolved,
                key=lambda item: (item["node_type"], item["label"]),
            )
        }
        device_matches.append(
            {
                "query_id": query_id,
                "device_record_id": device_id,
                "paper_doi": paper_doi,
                "matched_concepts_json": _to_json(matched_concepts),
                "warning_flags_json": _to_json(warning_flags),
                "path_count": str(len(target_requirements)),
            }
        )

        anchor_edge = (
            device_id,
            resolved_anchor["relation_type"],
            resolved_anchor["node_id"],
        )
        _require_stored_edge(anchor_edge, stored_edges)
        for path_number, target in enumerate(target_requirements, start=1):
            target_edge = (
                device_id,
                target["relation_type"],
                target["node_id"],
            )
            _require_stored_edge(target_edge, stored_edges)
            path_id = f"{query_id}:{device_id}:path_{path_number:02d}"
            path_rows.extend(
                (
                    _path_row(
                        query_id=query_id,
                        device_id=device_id,
                        path_id=path_id,
                        step_index=1,
                        source=resolved_anchor,
                        relation_type=resolved_anchor["relation_type"],
                        target=node_by_id[device_id],
                        direction="reverse",
                    ),
                    _path_row(
                        query_id=query_id,
                        device_id=device_id,
                        path_id=path_id,
                        step_index=2,
                        source=node_by_id[device_id],
                        relation_type=target["relation_type"],
                        target=target,
                        direction="forward",
                    ),
                )
            )

    outputs = GraphQueryOutputs(
        device_matches=tuple(
            sorted(
                device_matches,
                key=lambda row: (row["query_id"], row["device_record_id"]),
            )
        ),
        paths=tuple(
            sorted(
                path_rows,
                key=lambda row: (
                    row["query_id"],
                    row["device_record_id"],
                    row["path_id"],
                    int(row["step_index"]),
                ),
            )
        ),
    )
    _validate_outputs(outputs, graph, resolved, resolved_anchor)
    return outputs


def write_graph_query_outputs(
    outputs: GraphQueryOutputs,
    output_directory: Path | str,
    *,
    device_matches_filename: str = DEVICE_MATCHES_FILENAME,
    paths_filename: str = QUERY_PATHS_FILENAME,
) -> GraphQueryOutputPaths:
    """Write graph-query device matches and path rows."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = GraphQueryOutputPaths(
        device_matches=output_directory / device_matches_filename,
        paths=output_directory / paths_filename,
    )
    _write_csv(
        paths.device_matches,
        DEVICE_MATCH_COLUMNS,
        outputs.device_matches,
    )
    _write_csv(paths.paths, PATH_COLUMNS, outputs.paths)
    return paths


def run_material_structure_route_query(
    graph: IntegratedGraph,
    query: Mapping[str, Any],
) -> MaterialStructureRouteOutputs:
    """Retrieve material-structure routes from graph relations."""
    query_id = _required_text(query, "query_id")
    if query.get("query_type") != "material_structure_routes":
        raise ValueError("Expected a material_structure_routes query")
    anchor = query.get("anchor")
    retrieved = query.get("retrieved_concepts")
    if not isinstance(anchor, Mapping):
        raise ValueError("Route query must contain an anchor concept")
    if not isinstance(retrieved, list) or not retrieved:
        raise ValueError("Route query must contain retrieved_concepts")

    node_by_id = {row["node_id"]: row for row in graph.nodes}
    concept_by_identity = _index_concepts(graph.nodes)
    forward, reverse, stored_edges = _index_relations(graph.edges)
    resolved_anchor = _resolve_requirement(anchor, concept_by_identity)
    specifications = {
        _required_text(item, "node_type"): {
            "relation_type": _required_text(item, "relation_type"),
            "cardinality": _required_text(item, "cardinality"),
        }
        for item in retrieved
        if isinstance(item, Mapping)
    }
    expected_types = {
        "MaterialClass",
        "StructureClass",
        "PowerBin",
        "Pathway",
        "WarningFlag",
    }
    if set(specifications) != expected_types:
        raise ValueError(
            "Route query must retrieve MaterialClass, StructureClass, "
            "PowerBin, Pathway, and WarningFlag"
        )

    device_ids = sorted(
        source_id
        for source_id in reverse[
            (resolved_anchor["relation_type"], resolved_anchor["node_id"])
        ]
        if node_by_id[source_id]["node_type"] == "DeviceRecord"
    )
    route_rows: list[dict[str, str]] = []
    for device_id in device_ids:
        _require_stored_edge(
            (
                device_id,
                resolved_anchor["relation_type"],
                resolved_anchor["node_id"],
            ),
            stored_edges,
        )
        values = {
            node_type: _related_labels(
                device_id,
                node_type,
                specification["relation_type"],
                forward,
                node_by_id,
                stored_edges,
            )
            for node_type, specification in specifications.items()
        }
        for node_type in ("MaterialClass", "StructureClass", "PowerBin"):
            if specifications[node_type]["cardinality"] != "one":
                raise ValueError(f"{node_type} must have cardinality one")
            if len(values[node_type]) != 1:
                raise ValueError(
                    f"Expected one {node_type} for {device_id}, "
                    f"found {len(values[node_type])}"
                )
        for node_type in ("Pathway", "WarningFlag"):
            if specifications[node_type]["cardinality"] != "many":
                raise ValueError(f"{node_type} must have cardinality many")

        material_class = values["MaterialClass"][0]
        structure_class = values["StructureClass"][0]
        route_rows.append(
            {
                "query_id": query_id,
                "device_record_id": device_id,
                "paper_doi": _paper_doi(
                    device_id,
                    reverse,
                    node_by_id,
                    stored_edges,
                ),
                "material_class": material_class,
                "structure_class": structure_class,
                "power_bin": values["PowerBin"][0],
                "pathways_json": _to_json(values["Pathway"]),
                "warning_flags_json": _to_json(values["WarningFlag"]),
                "route_id": _route_id(material_class, structure_class),
            }
        )

    routes = tuple(
        sorted(
            route_rows,
            key=lambda row: (
                row["route_id"],
                row["device_record_id"],
            ),
        )
    )
    outputs = MaterialStructureRouteOutputs(
        routes=routes,
        summaries=_summarize_routes(query_id, routes),
    )
    _validate_route_outputs(outputs)
    return outputs


def write_material_structure_route_outputs(
    outputs: MaterialStructureRouteOutputs,
    output_directory: Path | str,
) -> MaterialStructureRouteOutputPaths:
    """Write material-structure route rows and summaries."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = MaterialStructureRouteOutputPaths(
        routes=output_directory / LOW_R_ROUTES_FILENAME,
        summaries=output_directory / LOW_R_ROUTE_SUMMARY_FILENAME,
    )
    _write_csv(paths.routes, LOW_R_ROUTE_COLUMNS, outputs.routes)
    _write_csv(
        paths.summaries,
        LOW_R_ROUTE_SUMMARY_COLUMNS,
        outputs.summaries,
    )
    return paths


def run_high_power_warning_query(
    graph: IntegratedGraph,
    query: Mapping[str, Any],
) -> HighPowerWarningOutputs:
    """Retrieve high-power device contexts through graph relations."""
    query_id = _required_text(query, "query_id")
    if query.get("query_type") != "high_power_warning_contexts":
        raise ValueError("Expected a high_power_warning_contexts query")
    anchor = query.get("anchor")
    retrieved = query.get("retrieved_concepts")
    if not isinstance(anchor, Mapping):
        raise ValueError("Warning query must contain an anchor concept")
    if not isinstance(retrieved, list) or not retrieved:
        raise ValueError("Warning query must contain retrieved_concepts")

    node_by_id = {row["node_id"]: row for row in graph.nodes}
    concept_by_identity = _index_concepts(graph.nodes)
    forward, reverse, stored_edges = _index_relations(graph.edges)
    resolved_anchor = _resolve_requirement(anchor, concept_by_identity)
    specifications = {
        _required_text(item, "node_type"): {
            "relation_type": _required_text(item, "relation_type"),
            "cardinality": _required_text(item, "cardinality"),
        }
        for item in retrieved
        if isinstance(item, Mapping)
    }
    expected_types = {
        "RBin",
        "MaterialClass",
        "StructureClass",
        "Pathway",
        "WarningFlag",
    }
    if set(specifications) != expected_types:
        raise ValueError(
            "Warning query must retrieve RBin, MaterialClass, "
            "StructureClass, Pathway, and WarningFlag"
        )

    device_ids = sorted(
        source_id
        for source_id in reverse[
            (resolved_anchor["relation_type"], resolved_anchor["node_id"])
        ]
        if node_by_id[source_id]["node_type"] == "DeviceRecord"
    )
    context_rows: list[dict[str, str]] = []
    for device_id in device_ids:
        _require_stored_edge(
            (
                device_id,
                resolved_anchor["relation_type"],
                resolved_anchor["node_id"],
            ),
            stored_edges,
        )
        values = {
            node_type: _related_labels(
                device_id,
                node_type,
                specification["relation_type"],
                forward,
                node_by_id,
                stored_edges,
            )
            for node_type, specification in specifications.items()
        }
        for node_type in ("RBin", "MaterialClass", "StructureClass"):
            if specifications[node_type]["cardinality"] != "one":
                raise ValueError(f"{node_type} must have cardinality one")
            if len(values[node_type]) != 1:
                raise ValueError(
                    f"Expected one {node_type} for {device_id}, "
                    f"found {len(values[node_type])}"
                )
        for node_type in ("Pathway", "WarningFlag"):
            if specifications[node_type]["cardinality"] != "many":
                raise ValueError(f"{node_type} must have cardinality many")

        warning_flags = values["WarningFlag"]
        context_rows.append(
            {
                "query_id": query_id,
                "device_record_id": device_id,
                "paper_doi": _paper_doi(
                    device_id,
                    reverse,
                    node_by_id,
                    stored_edges,
                ),
                "r_bin": values["RBin"][0],
                "material_class": values["MaterialClass"][0],
                "structure_class": values["StructureClass"][0],
                "pathways_json": _to_json(values["Pathway"]),
                "warning_flags_json": _to_json(warning_flags),
                "warning_profile": _warning_profile(warning_flags),
            }
        )

    contexts = tuple(
        sorted(context_rows, key=lambda row: row["device_record_id"])
    )
    outputs = HighPowerWarningOutputs(
        contexts=contexts,
        summaries=_summarize_warning_contexts(query_id, contexts),
    )
    _validate_high_power_warning_outputs(outputs)
    return outputs


def write_high_power_warning_outputs(
    outputs: HighPowerWarningOutputs,
    output_directory: Path | str,
) -> HighPowerWarningOutputPaths:
    """Write high-power warning contexts and cohort summaries."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = HighPowerWarningOutputPaths(
        contexts=output_directory / HIGH_POWER_WARNING_CONTEXTS_FILENAME,
        summaries=output_directory / HIGH_POWER_WARNING_SUMMARY_FILENAME,
    )
    _write_csv(
        paths.contexts,
        HIGH_POWER_WARNING_CONTEXT_COLUMNS,
        outputs.contexts,
    )
    _write_csv(
        paths.summaries,
        HIGH_POWER_WARNING_SUMMARY_COLUMNS,
        outputs.summaries,
    )
    return paths


def _warning_profile(warning_flags: Sequence[str]) -> str:
    warnings = set(warning_flags)
    has_reporting = bool(warnings & REPORTING_WARNINGS)
    has_electrochemical = ELECTROCHEMICAL_WARNING in warnings
    if not warnings:
        return "no_warning"
    if has_reporting and has_electrochemical:
        return "mixed_warning"
    if has_electrochemical:
        return "electrochemical_warning_only"
    if has_reporting and warnings <= REPORTING_WARNINGS:
        return "reporting_warning_only"
    raise ValueError(f"Unrecognized warning profile: {sorted(warnings)}")


def _summarize_warning_contexts(
    query_id: str,
    contexts: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str], ...]:
    summaries: list[dict[str, str]] = []
    for cohort in WARNING_COHORTS:
        rows = [
            row
            for row in contexts
            if (
                not json.loads(row["warning_flags_json"])
                if cohort == "no_warning"
                else cohort in json.loads(row["warning_flags_json"])
            )
        ]
        summaries.append(
            {
                "query_id": query_id,
                "warning_cohort": cohort,
                "matched_device_count": str(len(rows)),
                "low_R_device_count": str(
                    sum(row["r_bin"] == "low_R" for row in rows)
                ),
                "pathway_device_count": str(
                    sum(bool(json.loads(row["pathways_json"])) for row in rows)
                ),
                "device_ids_json": _to_json(
                    sorted(row["device_record_id"] for row in rows)
                ),
            }
        )
    return tuple(summaries)


def _validate_high_power_warning_outputs(
    outputs: HighPowerWarningOutputs,
) -> None:
    device_ids = [row["device_record_id"] for row in outputs.contexts]
    if len(device_ids) != len(set(device_ids)):
        raise ValueError("Warning query produced duplicate device rows")
    for row in outputs.contexts:
        pathways = json.loads(row["pathways_json"])
        warnings = json.loads(row["warning_flags_json"])
        if pathways != sorted(set(pathways)):
            raise ValueError("Pathways must be sorted and deduplicated")
        if warnings != sorted(set(warnings)):
            raise ValueError("Warnings must be sorted and deduplicated")
        if row["warning_profile"] != _warning_profile(warnings):
            raise ValueError("Warning profile is inconsistent with warnings")
    query_id = outputs.contexts[0]["query_id"] if outputs.contexts else ""
    if outputs.summaries != _summarize_warning_contexts(
        query_id,
        outputs.contexts,
    ):
        raise ValueError("Warning summaries do not match context rows")


def run_pathway_requirement_query(
    graph: IntegratedGraph,
    query: Mapping[str, Any],
) -> PathwayRequirementOutputs:
    """Retrieve pathway design, reporting, and device relations."""
    query_id = _required_text(query, "query_id")
    if (
        query.get("query_type")
        != "pathway_design_and_reporting_requirements"
    ):
        raise ValueError(
            "Expected a pathway_design_and_reporting_requirements query"
        )
    anchor = query.get("anchor")
    retrieved = query.get("retrieved_concepts")
    if not isinstance(anchor, Mapping):
        raise ValueError("Pathway query must contain an anchor")
    if _required_text(anchor, "node_type") != "Pathway":
        raise ValueError("Pathway query anchor must be Pathway")
    if not isinstance(retrieved, list) or not retrieved:
        raise ValueError("Pathway query must contain retrieved_concepts")

    specifications = {
        _required_text(item, "node_type"): {
            "relation_type": _required_text(item, "relation_type"),
            "direction": _required_text(item, "direction"),
        }
        for item in retrieved
        if isinstance(item, Mapping)
    }
    expected = {
        "DesignVariable": {
            "relation_type": "pathway_uses_design_variable",
            "direction": "forward",
        },
        "ReportingItem": {
            "relation_type": "pathway_requires_reporting_item",
            "direction": "forward",
        },
        "DeviceRecord": {
            "relation_type": "device_activates_pathway",
            "direction": "reverse",
        },
    }
    if specifications != expected:
        raise ValueError("Pathway query relation specifications are invalid")

    node_by_id = {row["node_id"]: row for row in graph.nodes}
    forward, reverse, stored_edges = _index_relations(graph.edges)
    pathways = sorted(
        (
            node
            for node in graph.nodes
            if node["node_type"] == "Pathway"
        ),
        key=lambda node: node["label"],
    )
    if len(pathways) != 4:
        raise ValueError(f"Expected four Pathway nodes, found {len(pathways)}")

    requirement_rows: list[dict[str, str]] = []
    for pathway in pathways:
        pathway_id = pathway["node_id"]
        design_variables = _related_labels(
            pathway_id,
            "DesignVariable",
            specifications["DesignVariable"]["relation_type"],
            forward,
            node_by_id,
            stored_edges,
        )
        reporting_items = _related_labels(
            pathway_id,
            "ReportingItem",
            specifications["ReportingItem"]["relation_type"],
            forward,
            node_by_id,
            stored_edges,
        )
        device_ids = _reverse_related_ids(
            pathway_id,
            "DeviceRecord",
            specifications["DeviceRecord"]["relation_type"],
            reverse,
            node_by_id,
            stored_edges,
        )
        requirement_rows.append(
            {
                "query_id": query_id,
                "pathway": pathway["label"],
                "matched_device_count": str(len(device_ids)),
                "design_variables_json": _to_json(design_variables),
                "reporting_items_json": _to_json(reporting_items),
                "device_ids_json": _to_json(device_ids),
            }
        )

    requirements = tuple(requirement_rows)
    outputs = PathwayRequirementOutputs(
        requirements=requirements,
        shared_concepts=_shared_pathway_concepts(query_id, requirements),
    )
    _validate_pathway_requirement_outputs(outputs)
    return outputs


def write_pathway_requirement_outputs(
    outputs: PathwayRequirementOutputs,
    output_directory: Path | str,
) -> PathwayRequirementOutputPaths:
    """Write pathway requirements and shared-concept rows."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = PathwayRequirementOutputPaths(
        requirements=output_directory / PATHWAY_REQUIREMENTS_FILENAME,
        shared_concepts=(
            output_directory / SHARED_PATHWAY_CONCEPTS_FILENAME
        ),
    )
    _write_csv(
        paths.requirements,
        PATHWAY_REQUIREMENT_COLUMNS,
        outputs.requirements,
    )
    _write_csv(
        paths.shared_concepts,
        SHARED_PATHWAY_CONCEPT_COLUMNS,
        outputs.shared_concepts,
    )
    return paths


def _reverse_related_ids(
    target_id: str,
    node_type: str,
    relation_type: str,
    reverse: Mapping[tuple[str, str], set[str]],
    node_by_id: Mapping[str, Mapping[str, str]],
    stored_edges: set[tuple[str, str, str]],
) -> tuple[str, ...]:
    source_ids: set[str] = set()
    for source_id in reverse[(relation_type, target_id)]:
        if node_by_id[source_id]["node_type"] != node_type:
            continue
        _require_stored_edge(
            (source_id, relation_type, target_id),
            stored_edges,
        )
        source_ids.add(source_id)
    return tuple(sorted(source_ids))


def _shared_pathway_concepts(
    query_id: str,
    requirements: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str], ...]:
    concept_pathways: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in requirements:
        for concept_type, column in (
            ("DesignVariable", "design_variables_json"),
            ("ReportingItem", "reporting_items_json"),
        ):
            for concept_label in json.loads(row[column]):
                concept_pathways[(concept_type, concept_label)].add(
                    row["pathway"]
                )

    rows = [
        {
            "query_id": query_id,
            "concept_type": concept_type,
            "concept_label": concept_label,
            "pathway_count": str(len(pathways)),
            "pathways_json": _to_json(sorted(pathways)),
        }
        for (concept_type, concept_label), pathways
        in concept_pathways.items()
        if len(pathways) >= 2
    ]
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row["concept_type"],
                row["concept_label"],
            ),
        )
    )


def _validate_pathway_requirement_outputs(
    outputs: PathwayRequirementOutputs,
) -> None:
    if len(outputs.requirements) != 4:
        raise ValueError("Pathway query must produce exactly four rows")
    pathway_labels = [row["pathway"] for row in outputs.requirements]
    if pathway_labels != sorted(set(pathway_labels)):
        raise ValueError("Pathway rows must be unique and sorted")
    for row in outputs.requirements:
        device_ids = json.loads(row["device_ids_json"])
        if int(row["matched_device_count"]) != len(device_ids):
            raise ValueError("Pathway device count is inconsistent")
        for column in (
            "design_variables_json",
            "reporting_items_json",
            "device_ids_json",
        ):
            values = json.loads(row[column])
            if values != sorted(set(values)):
                raise ValueError(f"{column} must be sorted and deduplicated")
    for row in outputs.shared_concepts:
        pathways = json.loads(row["pathways_json"])
        if int(row["pathway_count"]) < 2:
            raise ValueError("Shared concepts require at least two pathways")
        if int(row["pathway_count"]) != len(pathways):
            raise ValueError("Shared concept pathway count is inconsistent")
        if pathways != sorted(set(pathways)):
            raise ValueError("Shared concept pathways must be deduplicated")
    query_id = outputs.requirements[0]["query_id"]
    if outputs.shared_concepts != _shared_pathway_concepts(
        query_id,
        outputs.requirements,
    ):
        raise ValueError("Shared concepts do not match pathway requirements")


def _related_labels(
    device_id: str,
    node_type: str,
    relation_type: str,
    forward: Mapping[tuple[str, str], set[str]],
    node_by_id: Mapping[str, Mapping[str, str]],
    stored_edges: set[tuple[str, str, str]],
) -> tuple[str, ...]:
    target_ids = sorted(forward[(device_id, relation_type)])
    labels: set[str] = set()
    for target_id in target_ids:
        target = node_by_id[target_id]
        if target["node_type"] != node_type:
            continue
        _require_stored_edge(
            (device_id, relation_type, target_id),
            stored_edges,
        )
        labels.add(target["label"])
    return tuple(sorted(labels))


def _route_id(material_class: str, structure_class: str) -> str:
    return (
        "route_"
        + _slug(material_class)
        + "__"
        + _slug(structure_class)
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        raise ValueError("Route labels must contain letters or numbers")
    return slug


def _summarize_routes(
    query_id: str,
    routes: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str], ...]:
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in routes:
        grouped[row["route_id"]].append(row)

    summaries: list[dict[str, str]] = []
    for route_id, rows in grouped.items():
        material_classes = {row["material_class"] for row in rows}
        structure_classes = {row["structure_class"] for row in rows}
        if len(material_classes) != 1 or len(structure_classes) != 1:
            raise ValueError(f"Route ID collision for {route_id}")
        matched_count = len(rows)
        high_power_count = sum(
            row["power_bin"] == "high_power" for row in rows
        )
        summaries.append(
            {
                "query_id": query_id,
                "route_id": route_id,
                "material_class": next(iter(material_classes)),
                "structure_class": next(iter(structure_classes)),
                "matched_device_count": str(matched_count),
                "high_power_device_count": str(high_power_count),
                "high_power_fraction": str(
                    high_power_count / matched_count
                ),
                "pathway_device_count": str(
                    sum(bool(json.loads(row["pathways_json"])) for row in rows)
                ),
                "warning_device_count": str(
                    sum(
                        bool(json.loads(row["warning_flags_json"]))
                        for row in rows
                    )
                ),
                "device_ids_json": _to_json(
                    sorted(row["device_record_id"] for row in rows)
                ),
            }
        )
    return tuple(
        sorted(
            summaries,
            key=lambda row: (
                -int(row["matched_device_count"]),
                row["route_id"],
            ),
        )
    )


def _validate_route_outputs(
    outputs: MaterialStructureRouteOutputs,
) -> None:
    device_ids = [row["device_record_id"] for row in outputs.routes]
    if len(device_ids) != len(set(device_ids)):
        raise ValueError("Route query produced duplicate device rows")
    route_keys = [
        (row["device_record_id"], row["route_id"])
        for row in outputs.routes
    ]
    if len(route_keys) != len(set(route_keys)):
        raise ValueError("Route query produced duplicate route rows")
    for row in outputs.routes:
        if row["route_id"] != _route_id(
            row["material_class"],
            row["structure_class"],
        ):
            raise ValueError("Route ID is inconsistent with route labels")
        if json.loads(row["pathways_json"]) != sorted(
            set(json.loads(row["pathways_json"]))
        ):
            raise ValueError("Pathways must be sorted and deduplicated")
        if json.loads(row["warning_flags_json"]) != sorted(
            set(json.loads(row["warning_flags_json"]))
        ):
            raise ValueError("Warnings must be sorted and deduplicated")

    expected = _summarize_routes(
        outputs.routes[0]["query_id"] if outputs.routes else "",
        outputs.routes,
    )
    if outputs.summaries != expected:
        raise ValueError("Route summaries do not match route rows")


def _index_concepts(
    nodes: Sequence[Mapping[str, str]],
) -> dict[tuple[str, str], tuple[str, ...]]:
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for node in nodes:
        index[(node["node_type"], node["label"])].append(node["node_id"])
    return {
        identity: tuple(sorted(node_ids))
        for identity, node_ids in index.items()
    }


def _index_relations(
    edges: Sequence[Mapping[str, str]],
) -> tuple[
    dict[tuple[str, str], set[str]],
    dict[tuple[str, str], set[str]],
    set[tuple[str, str, str]],
]:
    forward: dict[tuple[str, str], set[str]] = defaultdict(set)
    reverse: dict[tuple[str, str], set[str]] = defaultdict(set)
    stored_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        source_id = edge["source_id"]
        relation = edge["edge_type"]
        target_id = edge["target_id"]
        forward[(source_id, relation)].add(target_id)
        reverse[(relation, target_id)].add(source_id)
        stored_edges.add((source_id, relation, target_id))
    return forward, reverse, stored_edges


def _resolve_requirement(
    requirement: Mapping[str, Any],
    concepts: Mapping[tuple[str, str], tuple[str, ...]],
) -> dict[str, str]:
    node_type = _required_text(requirement, "node_type")
    label = _required_text(requirement, "label")
    relation_type = _required_text(requirement, "relation_type")
    node_ids = concepts.get((node_type, label), ())
    if len(node_ids) != 1:
        raise ValueError(
            f"Expected one {node_type}:{label} node, found {len(node_ids)}"
        )
    return {
        "node_id": node_ids[0],
        "node_type": node_type,
        "label": label,
        "relation_type": relation_type,
    }


def _paper_doi(
    device_id: str,
    reverse: Mapping[tuple[str, str], set[str]],
    node_by_id: Mapping[str, Mapping[str, str]],
    stored_edges: set[tuple[str, str, str]],
) -> str:
    paper_ids = sorted(
        source_id
        for source_id in reverse[("reports", device_id)]
        if node_by_id[source_id]["node_type"] == "Paper"
    )
    if len(paper_ids) != 1:
        raise ValueError(
            f"Expected one reporting Paper for {device_id}, "
            f"found {len(paper_ids)}"
        )
    _require_stored_edge((paper_ids[0], "reports", device_id), stored_edges)
    return node_by_id[paper_ids[0]]["label"]


def _path_row(
    *,
    query_id: str,
    device_id: str,
    path_id: str,
    step_index: int,
    source: Mapping[str, str],
    relation_type: str,
    target: Mapping[str, str],
    direction: str,
) -> dict[str, str]:
    return {
        "query_id": query_id,
        "device_record_id": device_id,
        "path_id": path_id,
        "step_index": str(step_index),
        "traversal_source_node_id": source["node_id"],
        "traversal_source_label": source["label"],
        "relation_type": relation_type,
        "traversal_target_node_id": target["node_id"],
        "traversal_target_label": target["label"],
        "traversal_direction": direction,
    }


def _validate_outputs(
    outputs: GraphQueryOutputs,
    graph: IntegratedGraph,
    resolved: Sequence[Mapping[str, str]],
    anchor: Mapping[str, str],
) -> None:
    node_ids = {row["node_id"] for row in graph.nodes}
    stored_edges = {
        (row["source_id"], row["edge_type"], row["target_id"])
        for row in graph.edges
    }
    match_ids = [row["device_record_id"] for row in outputs.device_matches]
    if len(match_ids) != len(set(match_ids)):
        raise ValueError("Query produced duplicate device matches")

    path_steps = [
        (
            row["query_id"],
            row["device_record_id"],
            row["path_id"],
            row["step_index"],
        )
        for row in outputs.paths
    ]
    if len(path_steps) != len(set(path_steps)):
        raise ValueError("Query produced duplicate path steps")

    for device_id in match_ids:
        for requirement in resolved:
            _require_stored_edge(
                (
                    device_id,
                    requirement["relation_type"],
                    requirement["node_id"],
                ),
                stored_edges,
            )
    for row in outputs.paths:
        source_id = row["traversal_source_node_id"]
        target_id = row["traversal_target_node_id"]
        if source_id not in node_ids or target_id not in node_ids:
            raise ValueError("Query path references a missing node")
        if row["traversal_direction"] == "reverse":
            stored = (target_id, row["relation_type"], source_id)
        else:
            stored = (source_id, row["relation_type"], target_id)
        _require_stored_edge(stored, stored_edges)
        if row["step_index"] == "1" and source_id != anchor["node_id"]:
            raise ValueError("Every query path must begin at the anchor")


def _require_stored_edge(
    edge: tuple[str, str, str],
    stored_edges: set[tuple[str, str, str]],
) -> None:
    if edge not in stored_edges:
        raise ValueError(
            "Required integrated edge does not exist: "
            + " -> ".join(edge)
        )


def _required_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return item.strip()


def _to_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _load_csv(path: Path | str) -> tuple[dict[str, str], ...]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def _require_schema(
    rows: Sequence[Mapping[str, str]],
    columns: Sequence[str],
    table_name: str,
) -> None:
    if not rows:
        raise ValueError(f"{table_name} must not be empty")
    actual = tuple(rows[0])
    if actual != tuple(columns):
        raise ValueError(
            f"{table_name} schema is {actual}, expected {tuple(columns)}"
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

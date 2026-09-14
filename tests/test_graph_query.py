"""Tests for graph-native HydroKG multi-hop queries."""

import csv
import json
import re
from collections import Counter
from pathlib import Path

from hydrokg.query.graph_query import (
    DEVICE_MATCH_COLUMNS,
    HIGH_POWER_WARNING_CONTEXT_COLUMNS,
    HIGH_POWER_WARNING_SUMMARY_COLUMNS,
    LOW_R_ROUTE_COLUMNS,
    LOW_R_ROUTE_SUMMARY_COLUMNS,
    PATH_COLUMNS,
    PATHWAY_REQUIREMENT_COLUMNS,
    SHARED_PATHWAY_CONCEPT_COLUMNS,
    load_graph_query_config,
    load_integrated_graph,
    run_graph_query,
    run_high_power_warning_query,
    run_material_structure_route_query,
    run_pathway_requirement_query,
    write_graph_query_outputs,
    write_high_power_warning_outputs,
    write_material_structure_route_outputs,
    write_pathway_requirement_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"
NODES_PATH = RESULTS_DIRECTORY / "hydrokg_integrated_nodes.csv"
EDGES_PATH = RESULTS_DIRECTORY / "hydrokg_integrated_edges.csv"
QUERY_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "queries"
    / "hydrokg_graph_queries_v1.json"
)
EXPECTED_DEVICE_IDS = {
    "device_record_069",
    "device_record_071",
    "device_record_104",
    "device_record_155",
    "device_record_158",
    "device_record_159",
}


def build_query_outputs():
    graph = load_integrated_graph(NODES_PATH, EDGES_PATH)
    config = load_graph_query_config(QUERY_CONFIG_PATH)
    return graph, config["queries"][0], run_graph_query(
        graph,
        config["queries"][0],
    )


def build_route_outputs():
    graph = load_integrated_graph(NODES_PATH, EDGES_PATH)
    config = load_graph_query_config(QUERY_CONFIG_PATH)
    query = next(
        item
        for item in config["queries"]
        if item["query_id"] == "low_r_material_structure_routes"
    )
    return graph, query, run_material_structure_route_query(graph, query)


def build_nacl_outputs():
    graph = load_integrated_graph(NODES_PATH, EDGES_PATH)
    config = load_graph_query_config(QUERY_CONFIG_PATH)
    query = next(
        item
        for item in config["queries"]
        if item["query_id"] == "exact_nacl_primary_na_context"
    )
    return graph, query, run_graph_query(graph, query)


def build_warning_outputs():
    graph = load_integrated_graph(NODES_PATH, EDGES_PATH)
    config = load_graph_query_config(QUERY_CONFIG_PATH)
    query = next(
        item
        for item in config["queries"]
        if item["query_id"] == "high_power_warning_contexts"
    )
    return graph, query, run_high_power_warning_query(graph, query)


def build_pathway_requirement_outputs():
    graph = load_integrated_graph(NODES_PATH, EDGES_PATH)
    config = load_graph_query_config(QUERY_CONFIG_PATH)
    query = next(
        item
        for item in config["queries"]
        if item["query_id"]
        == "pathway_design_and_reporting_requirements"
    )
    return graph, query, run_pathway_requirement_query(graph, query)


def test_device_record_069_is_included() -> None:
    _, _, outputs = build_query_outputs()

    assert "device_record_069" in {
        row["device_record_id"] for row in outputs.device_matches
    }


def test_query_returns_expected_unique_devices() -> None:
    _, _, outputs = build_query_outputs()
    device_ids = [row["device_record_id"] for row in outputs.device_matches]

    assert set(device_ids) == EXPECTED_DEVICE_IDS
    assert len(device_ids) == len(set(device_ids))


def test_exact_nacl_primary_na_query_returns_20_7_2() -> None:
    graph, _, outputs = build_nacl_outputs()
    device_ids = {row["device_record_id"] for row in outputs.device_matches}
    nodes = {row["node_id"]: row for row in graph.nodes}
    material_classes = {
        nodes[edge["target_id"]]["label"]
        for edge in graph.edges
        if edge["source_id"] in device_ids
        and edge["edge_type"] == "has_material_class"
    }
    structure_classes = {
        nodes[edge["target_id"]]["label"]
        for edge in graph.edges
        if edge["source_id"] in device_ids
        and edge["edge_type"] == "has_structure_class"
    }

    assert len(device_ids) == 20
    assert len(material_classes) == 7
    assert len(structure_classes) == 2
    for row in outputs.device_matches:
        assert json.loads(row["matched_concepts_json"]) == {
            "Electrolyte": "NaCl",
            "Ion": "Na+",
        }


def test_all_returned_devices_satisfy_every_required_relation() -> None:
    graph, query, outputs = build_query_outputs()
    node_ids = {
        (node["node_type"], node["label"]): node["node_id"]
        for node in graph.nodes
    }
    edges = {
        (edge["source_id"], edge["edge_type"], edge["target_id"])
        for edge in graph.edges
    }

    for match in outputs.device_matches:
        device_id = match["device_record_id"]
        for requirement in query["required_concepts"]:
            target_id = node_ids[
                (requirement["node_type"], requirement["label"])
            ]
            assert (
                device_id,
                requirement["relation_type"],
                target_id,
            ) in edges


def test_match_json_and_path_counts_are_deterministic_and_complete() -> None:
    _, query, outputs = build_query_outputs()
    expected_concepts = {
        item["node_type"]: item["label"]
        for item in query["required_concepts"]
    }

    for match in outputs.device_matches:
        assert json.loads(match["matched_concepts_json"]) == expected_concepts
        assert isinstance(json.loads(match["warning_flags_json"]), list)
        assert match["path_count"] == "3"
        assert match["matched_concepts_json"] == json.dumps(
            expected_concepts,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


def test_all_paths_have_two_steps() -> None:
    _, _, outputs = build_query_outputs()
    counts = Counter(row["path_id"] for row in outputs.paths)

    assert len(counts) == len(EXPECTED_DEVICE_IDS) * 3
    assert set(counts.values()) == {2}
    assert len(outputs.paths) == len(
        {
            (
                row["query_id"],
                row["device_record_id"],
                row["path_id"],
                row["step_index"],
            )
            for row in outputs.paths
        }
    )


def test_paths_begin_at_polymer_and_end_at_requested_concepts() -> None:
    _, query, outputs = build_query_outputs()
    anchor = query["anchor"]["label"]
    target_labels = {
        item["label"]
        for item in query["required_concepts"]
        if item["label"] != anchor
    }
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in outputs.paths:
        grouped.setdefault(row["path_id"], []).append(row)

    for steps in grouped.values():
        ordered = sorted(steps, key=lambda row: int(row["step_index"]))
        assert ordered[0]["traversal_source_label"] == "polymer"
        assert ordered[0]["traversal_direction"] == "reverse"
        assert ordered[0]["relation_type"] == "has_material_class"
        assert ordered[0]["traversal_target_node_id"].startswith(
            "device_record_"
        )
        assert ordered[1]["traversal_source_node_id"] == (
            ordered[0]["traversal_target_node_id"]
        )
        assert ordered[1]["traversal_target_label"] in target_labels
        assert ordered[1]["traversal_direction"] == "forward"


def test_every_path_step_corresponds_to_an_integrated_edge() -> None:
    graph, _, outputs = build_query_outputs()
    edges = {
        (edge["source_id"], edge["edge_type"], edge["target_id"])
        for edge in graph.edges
    }

    for step in outputs.paths:
        source_id = step["traversal_source_node_id"]
        target_id = step["traversal_target_node_id"]
        if step["traversal_direction"] == "reverse":
            stored_edge = (target_id, step["relation_type"], source_id)
        else:
            stored_edge = (source_id, step["relation_type"], target_id)
        assert stored_edge in edges


def test_outputs_are_deterministic() -> None:
    graph, query, first = build_query_outputs()
    second = run_graph_query(graph, query)

    assert first == second
    assert list(first.device_matches) == sorted(
        first.device_matches,
        key=lambda row: (row["query_id"], row["device_record_id"]),
    )
    assert list(first.paths) == sorted(
        first.paths,
        key=lambda row: (
            row["query_id"],
            row["device_record_id"],
            row["path_id"],
            int(row["step_index"]),
        ),
    )


def test_temporary_output_writing_works(tmp_path: Path) -> None:
    _, _, outputs = build_query_outputs()
    output_directory = tmp_path / ".test_graph_query_outputs"
    paths = write_graph_query_outputs(outputs, output_directory)

    assert paths.device_matches.is_file()
    assert paths.paths.is_file()
    with paths.device_matches.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        assert tuple(next(csv.reader(handle))) == DEVICE_MATCH_COLUMNS
    with paths.paths.open(encoding="utf-8", newline="") as handle:
        assert tuple(next(csv.reader(handle))) == PATH_COLUMNS


def test_low_r_routes_return_55_unique_devices() -> None:
    _, _, outputs = build_route_outputs()
    device_ids = [row["device_record_id"] for row in outputs.routes]

    assert len(device_ids) == 55
    assert len(outputs.summaries) == 13
    assert len(device_ids) == len(set(device_ids))


def test_low_r_routes_have_no_duplicate_rows() -> None:
    _, _, outputs = build_route_outputs()
    keys = [
        (row["device_record_id"], row["route_id"])
        for row in outputs.routes
    ]

    assert len(keys) == len(set(keys))
    for row in outputs.routes:
        assert row["route_id"] == (
            "route_"
            + re.sub(
                r"[^a-z0-9]+",
                "_",
                row["material_class"].lower(),
            ).strip("_")
            + "__"
            + re.sub(
                r"[^a-z0-9]+",
                "_",
                row["structure_class"].lower(),
            ).strip("_")
        )
        assert json.loads(row["pathways_json"]) == sorted(
            set(json.loads(row["pathways_json"]))
        )
        assert json.loads(row["warning_flags_json"]) == sorted(
            set(json.loads(row["warning_flags_json"]))
        )


def test_low_r_route_summaries_equal_underlying_rows() -> None:
    _, _, outputs = build_route_outputs()

    for summary in outputs.summaries:
        rows = [
            row
            for row in outputs.routes
            if row["route_id"] == summary["route_id"]
        ]
        assert int(summary["matched_device_count"]) == len(rows)
        assert int(summary["high_power_device_count"]) == sum(
            row["power_bin"] == "high_power" for row in rows
        )
        assert int(summary["pathway_device_count"]) == sum(
            bool(json.loads(row["pathways_json"])) for row in rows
        )
        assert int(summary["warning_device_count"]) == sum(
            bool(json.loads(row["warning_flags_json"])) for row in rows
        )
        assert json.loads(summary["device_ids_json"]) == sorted(
            row["device_record_id"] for row in rows
        )


def test_low_r_route_high_power_fraction_is_correct() -> None:
    _, _, outputs = build_route_outputs()

    for summary in outputs.summaries:
        expected = int(summary["high_power_device_count"]) / int(
            summary["matched_device_count"]
        )
        assert float(summary["high_power_fraction"]) == expected


def test_low_r_route_relations_exist_in_integrated_graph() -> None:
    graph, query, outputs = build_route_outputs()
    nodes = {node["node_id"]: node for node in graph.nodes}
    edges = {
        (edge["source_id"], edge["edge_type"], edge["target_id"])
        for edge in graph.edges
    }
    anchor_id = next(
        node["node_id"]
        for node in graph.nodes
        if node["node_type"] == query["anchor"]["node_type"]
        and node["label"] == query["anchor"]["label"]
    )

    for row in outputs.routes:
        device_id = row["device_record_id"]
        assert (
            device_id,
            query["anchor"]["relation_type"],
            anchor_id,
        ) in edges
        expected_labels = {
            "MaterialClass": {row["material_class"]},
            "StructureClass": {row["structure_class"]},
            "PowerBin": {row["power_bin"]},
            "Pathway": set(json.loads(row["pathways_json"])),
            "WarningFlag": set(json.loads(row["warning_flags_json"])),
        }
        for specification in query["retrieved_concepts"]:
            related_labels = {
                nodes[target_id]["label"]
                for source_id, edge_type, target_id in edges
                if source_id == device_id
                and edge_type == specification["relation_type"]
                and nodes[target_id]["node_type"]
                == specification["node_type"]
            }
            assert related_labels == expected_labels[
                specification["node_type"]
            ]


def test_low_r_route_outputs_are_deterministic() -> None:
    graph, query, first = build_route_outputs()
    second = run_material_structure_route_query(graph, query)

    assert first == second
    assert list(first.routes) == sorted(
        first.routes,
        key=lambda row: (row["route_id"], row["device_record_id"]),
    )
    assert list(first.summaries) == sorted(
        first.summaries,
        key=lambda row: (
            -int(row["matched_device_count"]),
            row["route_id"],
        ),
    )


def test_low_r_route_temporary_output_writing_works(tmp_path: Path) -> None:
    _, _, outputs = build_route_outputs()
    output_directory = tmp_path / ".test_low_r_route_outputs"
    paths = write_material_structure_route_outputs(
        outputs,
        output_directory,
    )

    assert paths.routes.is_file()
    assert paths.summaries.is_file()
    with paths.routes.open(encoding="utf-8", newline="") as handle:
        assert tuple(next(csv.reader(handle))) == LOW_R_ROUTE_COLUMNS
    with paths.summaries.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        assert tuple(next(csv.reader(handle))) == (
            LOW_R_ROUTE_SUMMARY_COLUMNS
        )


def test_high_power_count_matches_anchor_edges() -> None:
    graph, query, outputs = build_warning_outputs()
    high_power_id = next(
        node["node_id"]
        for node in graph.nodes
        if node["node_type"] == "PowerBin"
        and node["label"] == "high_power"
    )
    anchor_edges = [
        edge
        for edge in graph.edges
        if edge["edge_type"] == query["anchor"]["relation_type"]
        and edge["target_id"] == high_power_id
    ]

    assert len(outputs.contexts) == len(anchor_edges)
    assert len(outputs.contexts) == 40


def test_high_power_contexts_have_required_single_values() -> None:
    graph, query, outputs = build_warning_outputs()
    nodes = {node["node_id"]: node for node in graph.nodes}
    expected_relations = {
        item["node_type"]: item["relation_type"]
        for item in query["retrieved_concepts"]
    }

    for row in outputs.contexts:
        device_edges = [
            edge
            for edge in graph.edges
            if edge["source_id"] == row["device_record_id"]
        ]
        for node_type, column in (
            ("RBin", "r_bin"),
            ("MaterialClass", "material_class"),
            ("StructureClass", "structure_class"),
        ):
            labels = [
                nodes[edge["target_id"]]["label"]
                for edge in device_edges
                if edge["edge_type"] == expected_relations[node_type]
                and nodes[edge["target_id"]]["node_type"] == node_type
            ]
            assert labels == [row[column]]


def test_high_power_warning_profiles_follow_definitions() -> None:
    _, _, outputs = build_warning_outputs()
    reporting = {
        "missing_R_warning",
        "missing_humidity_warning",
        "incomplete_reporting_warning",
    }
    electrochemical = "electrochemical_control_needed_warning"

    for row in outputs.contexts:
        warnings = set(json.loads(row["warning_flags_json"]))
        if not warnings:
            expected = "no_warning"
        elif warnings & reporting and electrochemical in warnings:
            expected = "mixed_warning"
        elif electrochemical in warnings:
            expected = "electrochemical_warning_only"
        else:
            assert warnings <= reporting
            expected = "reporting_warning_only"
        assert row["warning_profile"] == expected


def test_high_power_summary_matches_context_rows() -> None:
    _, _, outputs = build_warning_outputs()

    for summary in outputs.summaries:
        cohort = summary["warning_cohort"]
        rows = [
            row
            for row in outputs.contexts
            if (
                not json.loads(row["warning_flags_json"])
                if cohort == "no_warning"
                else cohort in json.loads(row["warning_flags_json"])
            )
        ]
        assert int(summary["matched_device_count"]) == len(rows)
        assert int(summary["low_R_device_count"]) == sum(
            row["r_bin"] == "low_R" for row in rows
        )
        assert int(summary["pathway_device_count"]) == sum(
            bool(json.loads(row["pathways_json"])) for row in rows
        )
        assert json.loads(summary["device_ids_json"]) == sorted(
            row["device_record_id"] for row in rows
        )


def test_high_power_contexts_are_unique_and_deterministic() -> None:
    graph, query, first = build_warning_outputs()
    second = run_high_power_warning_query(graph, query)
    device_ids = [row["device_record_id"] for row in first.contexts]

    assert first == second
    assert len(device_ids) == len(set(device_ids))
    assert device_ids == sorted(device_ids)
    assert [row["warning_cohort"] for row in first.summaries] == [
        "no_warning",
        "missing_R_warning",
        "missing_humidity_warning",
        "incomplete_reporting_warning",
        "electrochemical_control_needed_warning",
    ]
    for row in first.contexts:
        assert json.loads(row["pathways_json"]) == sorted(
            set(json.loads(row["pathways_json"]))
        )
        assert json.loads(row["warning_flags_json"]) == sorted(
            set(json.loads(row["warning_flags_json"]))
        )


def test_high_power_temporary_output_writing_works(tmp_path: Path) -> None:
    _, _, outputs = build_warning_outputs()
    output_directory = tmp_path / ".test_high_power_outputs"
    paths = write_high_power_warning_outputs(outputs, output_directory)

    assert paths.contexts.is_file()
    assert paths.summaries.is_file()
    with paths.contexts.open(encoding="utf-8", newline="") as handle:
        assert tuple(next(csv.reader(handle))) == (
            HIGH_POWER_WARNING_CONTEXT_COLUMNS
        )
    with paths.summaries.open(encoding="utf-8", newline="") as handle:
        assert tuple(next(csv.reader(handle))) == (
            HIGH_POWER_WARNING_SUMMARY_COLUMNS
        )


def test_pathway_requirements_return_four_pathways() -> None:
    _, _, outputs = build_pathway_requirement_outputs()

    assert len(outputs.requirements) == 4
    assert [row["pathway"] for row in outputs.requirements] == sorted(
        row["pathway"] for row in outputs.requirements
    )


def test_pathway_device_counts_match_graph_edges() -> None:
    graph, _, outputs = build_pathway_requirement_outputs()
    pathway_ids = {
        node["label"]: node["node_id"]
        for node in graph.nodes
        if node["node_type"] == "Pathway"
    }

    for row in outputs.requirements:
        device_ids = sorted(
            {
                edge["source_id"]
                for edge in graph.edges
                if edge["edge_type"] == "device_activates_pathway"
                and edge["target_id"] == pathway_ids[row["pathway"]]
            }
        )
        assert int(row["matched_device_count"]) == len(device_ids)
        assert json.loads(row["device_ids_json"]) == device_ids


def test_pathway_mappings_match_graph_relations() -> None:
    graph, _, outputs = build_pathway_requirement_outputs()
    nodes = {node["node_id"]: node for node in graph.nodes}
    pathway_ids = {
        node["label"]: node["node_id"]
        for node in graph.nodes
        if node["node_type"] == "Pathway"
    }

    for row in outputs.requirements:
        pathway_id = pathway_ids[row["pathway"]]
        for node_type, relation_type, column in (
            (
                "DesignVariable",
                "pathway_uses_design_variable",
                "design_variables_json",
            ),
            (
                "ReportingItem",
                "pathway_requires_reporting_item",
                "reporting_items_json",
            ),
        ):
            labels = sorted(
                {
                    nodes[edge["target_id"]]["label"]
                    for edge in graph.edges
                    if edge["source_id"] == pathway_id
                    and edge["edge_type"] == relation_type
                    and nodes[edge["target_id"]]["node_type"] == node_type
                }
            )
            assert json.loads(row[column]) == labels


def test_shared_pathway_concepts_match_requirement_rows() -> None:
    _, _, outputs = build_pathway_requirement_outputs()

    for shared in outputs.shared_concepts:
        assert shared["concept_type"] in {
            "DesignVariable",
            "ReportingItem",
        }
        assert int(shared["pathway_count"]) >= 2
        column = (
            "design_variables_json"
            if shared["concept_type"] == "DesignVariable"
            else "reporting_items_json"
        )
        pathways = sorted(
            row["pathway"]
            for row in outputs.requirements
            if shared["concept_label"] in json.loads(row[column])
        )
        assert int(shared["pathway_count"]) == len(pathways)
        assert json.loads(shared["pathways_json"]) == pathways


def test_pathway_requirement_outputs_are_deterministic() -> None:
    graph, query, first = build_pathway_requirement_outputs()
    second = run_pathway_requirement_query(graph, query)

    assert first == second
    assert list(first.shared_concepts) == sorted(
        first.shared_concepts,
        key=lambda row: (row["concept_type"], row["concept_label"]),
    )
    for row in first.requirements:
        for column in (
            "design_variables_json",
            "reporting_items_json",
            "device_ids_json",
        ):
            values = json.loads(row[column])
            assert values == sorted(set(values))


def test_pathway_requirement_temporary_output_writing_works(tmp_path: Path) -> None:
    _, _, outputs = build_pathway_requirement_outputs()
    output_directory = tmp_path / ".test_pathway_requirements"
    paths = write_pathway_requirement_outputs(
        outputs,
        output_directory,
    )

    assert paths.requirements.is_file()
    assert paths.shared_concepts.is_file()
    with paths.requirements.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        assert tuple(next(csv.reader(handle))) == PATHWAY_REQUIREMENT_COLUMNS
    with paths.shared_concepts.open(
        encoding="utf-8",
        newline="",
    ) as handle:
        assert tuple(next(csv.reader(handle))) == (
            SHARED_PATHWAY_CONCEPT_COLUMNS
        )

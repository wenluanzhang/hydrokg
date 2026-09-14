"""Tests for semantic graph materialization and integration."""

import json
from collections import Counter
from pathlib import Path

from hydrokg.graph.semantic_materialization import (
    deterministic_semantic_node_id,
    find_missing_edge_endpoints,
    load_csv_rows,
    materialize_semantic_graph,
    write_semantic_graph_tables,
)
from hydrokg.graph.tables import EDGE_COLUMNS, NODE_COLUMNS

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
EXPECTED_PATHWAY_COUNTS = {
    "connected_pore_ion_transport_pathway": 34,
    "biomass_fiber_capillary_pathway": 20,
    "hydrated_network_ionic_conduction_pathway": 14,
    "film_based_ion_concentration_gradient_pathway": 13,
}
EXPECTED_WARNING_COUNTS = {
    "missing_R_warning": 47,
    "missing_humidity_warning": 33,
    "incomplete_reporting_warning": 65,
    "electrochemical_control_needed_warning": 84,
}
PREVIOUS_NODE_COUNTS = {
    "RBin": 3,
    "PowerBin": 3,
    "Pathway": 4,
    "WarningFlag": 4,
}
PREVIOUS_EDGE_COUNTS = {
    "device_has_r_bin": 159,
    "device_has_power_bin": 159,
    "device_activates_pathway": 81,
    "device_has_warning_flag": 229,
}
NEW_EDGE_TYPES = {
    "pathway_uses_design_variable": (
        "DesignVariable",
        "design_variables",
    ),
    "pathway_requires_reporting_item": (
        "ReportingItem",
        "required_reporting_items",
    ),
}


def build_tables():
    return materialize_semantic_graph(
        base_nodes_path=BASE_NODES_PATH,
        base_edges_path=BASE_EDGES_PATH,
        device_table_path=DEVICE_TABLE_PATH,
        pathway_matches_path=PATHWAY_MATCHES_PATH,
        semantic_layer_path=SEMANTIC_LAYER_PATH,
        pathway_rules_path=PATHWAY_RULES_PATH,
    )


def test_semantic_node_ids_are_deterministic() -> None:
    first = deterministic_semantic_node_id("RBin", "low_R")
    second = deterministic_semantic_node_id("RBin", "low_R")

    assert first == second
    assert first != deterministic_semantic_node_id("PowerBin", "low_R")
    assert first != deterministic_semantic_node_id("RBin", "high_R")


def test_semantic_nodes_are_unique_and_use_base_schema() -> None:
    nodes = build_tables().semantic_nodes
    node_ids = [row["node_id"] for row in nodes]
    identities = [(row["node_type"], row["label"]) for row in nodes]

    assert len(nodes) == 33
    assert len(node_ids) == len(set(node_ids))
    assert len(identities) == len(set(identities))
    assert all(tuple(row) == NODE_COLUMNS for row in nodes)


def test_semantic_edges_are_unique_and_use_base_schema() -> None:
    edges = build_tables().semantic_edges
    edge_ids = [row["edge_id"] for row in edges]
    triples = [
        (row["source_id"], row["edge_type"], row["target_id"])
        for row in edges
    ]

    assert len(edge_ids) == len(set(edge_ids))
    assert len(triples) == len(set(triples))
    assert all(tuple(row) == EDGE_COLUMNS for row in edges)


def test_previous_semantic_counts_and_relations_are_unchanged() -> None:
    tables = build_tables()

    assert {
        node_type: sum(
            row["node_type"] == node_type for row in tables.semantic_nodes
        )
        for node_type in PREVIOUS_NODE_COUNTS
    } == PREVIOUS_NODE_COUNTS
    assert {
        edge_type: sum(
            row["edge_type"] == edge_type for row in tables.semantic_edges
        )
        for edge_type in PREVIOUS_EDGE_COUNTS
    } == PREVIOUS_EDGE_COUNTS


def test_new_semantic_vocabularies_match_configuration() -> None:
    tables = build_tables()
    semantic_layer = _load_json(SEMANTIC_LAYER_PATH)

    for node_type in ("DesignVariable", "ReportingItem"):
        actual = {
            row["label"]
            for row in tables.semantic_nodes
            if row["node_type"] == node_type
        }
        expected = set(
            semantic_layer["concept_types"][node_type]["concepts"]
        )

        assert actual == expected
        assert len(actual) == sum(
            row["node_type"] == node_type for row in tables.semantic_nodes
        )


def test_new_edges_are_unique_and_explicitly_supported_by_rules() -> None:
    tables = build_tables()
    rules = _load_json(PATHWAY_RULES_PATH)["rules"]
    labels_by_id = {
        row["node_id"]: row["label"] for row in tables.semantic_nodes
    }

    for edge_type, (_, rule_field) in NEW_EDGE_TYPES.items():
        actual = {
            (
                labels_by_id[row["source_id"]],
                labels_by_id[row["target_id"]],
            )
            for row in tables.semantic_edges
            if row["edge_type"] == edge_type
        }
        expected = {
            (rule["activates_pathway"], concept)
            for rule in rules
            if rule["rule_type"] != "warning_only"
            and rule["activates_pathway"]
            for concept in rule[rule_field]
        }
        edge_count = sum(
            row["edge_type"] == edge_type for row in tables.semantic_edges
        )

        assert actual == expected
        assert edge_count == len(actual)


def test_new_edges_connect_pathways_to_expected_concept_types() -> None:
    tables = build_tables()
    types_by_id = {
        row["node_id"]: row["node_type"] for row in tables.semantic_nodes
    }

    for edge_type, (target_type, _) in NEW_EDGE_TYPES.items():
        edges = [
            row
            for row in tables.semantic_edges
            if row["edge_type"] == edge_type
        ]

        assert edges
        assert all(types_by_id[row["source_id"]] == "Pathway" for row in edges)
        assert all(types_by_id[row["target_id"]] == target_type for row in edges)


def test_no_device_edges_target_new_concept_types() -> None:
    tables = build_tables()
    types_by_id = {
        row["node_id"]: row["node_type"] for row in tables.semantic_nodes
    }

    assert not [
        row
        for row in tables.semantic_edges
        if row["source_id"].startswith("device_record_")
        and types_by_id.get(row["target_id"])
        in {"DesignVariable", "ReportingItem"}
    ]


def test_all_devices_have_exactly_one_r_bin_edge() -> None:
    edges = [
        row
        for row in build_tables().semantic_edges
        if row["edge_type"] == "device_has_r_bin"
    ]

    assert len(edges) == 159
    assert Counter(row["source_id"] for row in edges) == {
        f"device_record_{index:03d}": 1 for index in range(1, 160)
    }


def test_power_bin_assignments_match_r_centered_table() -> None:
    tables = build_tables()
    labels_by_id = {
        row["node_id"]: row["label"] for row in tables.semantic_nodes
    }
    actual = {
        row["source_id"]: labels_by_id[row["target_id"]]
        for row in tables.semantic_edges
        if row["edge_type"] == "device_has_power_bin"
    }
    expected = {}
    for row in load_csv_rows(DEVICE_TABLE_PATH):
        if row["estimated_power_available_flag"].lower() != "true":
            power_bin = "missing_power"
        elif row["high_power_flag"].lower() == "true":
            power_bin = "high_power"
        else:
            power_bin = "non_high_power"
        expected[row["device_record_id"]] = power_bin

    assert actual == expected


def test_missing_source_power_does_not_make_estimated_power_bin_missing() -> None:
    tables = build_tables()
    labels_by_id = {
        row["node_id"]: row["label"] for row in tables.semantic_nodes
    }
    actual = {
        row["source_id"]: labels_by_id[row["target_id"]]
        for row in tables.semantic_edges
        if row["edge_type"] == "device_has_power_bin"
    }
    device_rows = load_csv_rows(DEVICE_TABLE_PATH)
    missing_source_power = {
        row["device_record_id"]
        for row in device_rows
        if row["power_reported_flag"].lower() != "true"
        and row["estimated_power_available_flag"].lower() == "true"
    }

    assert len(missing_source_power) == 51
    assert all(actual[device_id] != "missing_power" for device_id in missing_source_power)


def test_expected_pathway_and_warning_device_counts() -> None:
    tables = build_tables()
    labels_by_id = {
        row["node_id"]: row["label"] for row in tables.semantic_nodes
    }
    pathway_counts = _unique_device_counts(
        tables.semantic_edges,
        labels_by_id,
        "device_activates_pathway",
    )
    warning_counts = _unique_device_counts(
        tables.semantic_edges,
        labels_by_id,
        "device_has_warning_flag",
    )

    assert pathway_counts == EXPECTED_PATHWAY_COUNTS
    assert warning_counts == EXPECTED_WARNING_COUNTS


def test_warning_only_matches_do_not_create_pathway_edges() -> None:
    matches = load_csv_rows(PATHWAY_MATCHES_PATH)
    warning_only_devices = {
        row["device_record_id"]
        for row in matches
        if row["rule_type"] == "warning_only"
    }
    warning_only_rule_ids = {
        row["rule_id"] for row in matches if row["rule_type"] == "warning_only"
    }
    pathway_edges = [
        row
        for row in build_tables().semantic_edges
        if row["edge_type"] == "device_activates_pathway"
    ]

    assert warning_only_devices
    assert all(
        not (set(row["source_value"].split("|")) & warning_only_rule_ids)
        for row in pathway_edges
    )


def test_repeated_incomplete_reporting_matches_are_collapsed() -> None:
    tables = build_tables()
    incomplete_id = next(
        row["node_id"]
        for row in tables.semantic_nodes
        if row["node_type"] == "WarningFlag"
        and row["label"] == "incomplete_reporting_warning"
    )
    incomplete_edges = [
        row
        for row in tables.semantic_edges
        if row["target_id"] == incomplete_id
    ]

    assert len(incomplete_edges) == 65
    assert len({row["source_id"] for row in incomplete_edges}) == 65
    assert any("|" in row["source_value"] for row in incomplete_edges)


def test_integrated_graph_has_zero_missing_endpoints() -> None:
    tables = build_tables()

    assert (
        find_missing_edge_endpoints(
            tables.integrated_nodes,
            tables.integrated_edges,
        )
        == ()
    )


def test_base_graph_rows_are_fully_preserved() -> None:
    tables = build_tables()
    base_nodes = load_csv_rows(BASE_NODES_PATH)
    base_edges = load_csv_rows(BASE_EDGES_PATH)
    integrated_nodes = {row["node_id"]: row for row in tables.integrated_nodes}
    integrated_edges = {row["edge_id"]: row for row in tables.integrated_edges}

    assert all(integrated_nodes[row["node_id"]] == row for row in base_nodes)
    assert all(integrated_edges[row["edge_id"]] == row for row in base_edges)


def test_outputs_are_sorted_deterministically() -> None:
    tables = build_tables()

    assert [row["node_id"] for row in tables.semantic_nodes] == sorted(
        row["node_id"] for row in tables.semantic_nodes
    )
    assert [row["edge_id"] for row in tables.semantic_edges] == sorted(
        row["edge_id"] for row in tables.semantic_edges
    )
    assert [row["node_id"] for row in tables.integrated_nodes] == sorted(
        row["node_id"] for row in tables.integrated_nodes
    )
    assert [row["edge_id"] for row in tables.integrated_edges] == sorted(
        row["edge_id"] for row in tables.integrated_edges
    )


def test_temporary_output_writing_works(tmp_path: Path) -> None:
    paths = write_semantic_graph_tables(build_tables(), tmp_path / "tables")

    assert paths.semantic_nodes.is_file()
    assert paths.semantic_edges.is_file()
    assert paths.integrated_nodes.is_file()
    assert paths.integrated_edges.is_file()
    assert tuple(load_csv_rows(paths.semantic_nodes)[0]) == NODE_COLUMNS
    assert tuple(load_csv_rows(paths.semantic_edges)[0]) == EDGE_COLUMNS


def _unique_device_counts(edges, labels_by_id, edge_type):
    grouped: dict[str, set[str]] = {}
    for row in edges:
        if row["edge_type"] != edge_type:
            continue
        label = labels_by_id[row["target_id"]]
        grouped.setdefault(label, set()).add(row["source_id"])
    return {label: len(device_ids) for label, device_ids in grouped.items()}


def _load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)

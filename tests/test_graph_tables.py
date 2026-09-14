"""Tests for HydroKG node and edge table generation."""

import csv
from pathlib import Path

from hydrokg.graph.tables import (
    GraphTables,
    build_graph_tables,
    load_schema,
    write_graph_tables,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPOSITORY_ROOT / "configs" / "schema" / "hydrokg_schema_v1.json"
SEED_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "raw"
    / "hydrovoltaic_ml_curated_159_seed.csv"
)
EXPECTED_NODE_TYPES = {
    "Paper",
    "DeviceRecord",
    "Material",
    "MaterialClass",
    "StructureClass",
    "Ion",
    "Electrolyte",
    "Electrode",
    "Mechanism",
    "AsymmetryOrigin",
    "WaterInteractionMode",
}
EXPECTED_EDGE_TYPES = {
    "reports",
    "uses_material",
    "has_material_class",
    "has_structure_class",
    "has_primary_mobile_ion",
    "has_secondary_mobile_ion",
    "uses_electrolyte",
    "has_top_electrode",
    "has_bottom_electrode",
    "has_mechanism",
    "has_asymmetry_origin",
    "has_water_interaction_mode",
}


def build_tables() -> GraphTables:
    return build_graph_tables(SEED_PATH, load_schema(SCHEMA_PATH))


def test_device_record_node_count_is_159() -> None:
    device_nodes = [
        node
        for node in build_tables().nodes
        if node["node_type"] == "DeviceRecord"
    ]

    assert len(device_nodes) == 159
    assert device_nodes[0]["node_id"] == "device_record_001"
    assert device_nodes[-1]["node_id"] == "device_record_159"


def test_node_ids_are_unique() -> None:
    node_ids = [node["node_id"] for node in build_tables().nodes]

    assert len(node_ids) == len(set(node_ids))


def test_edge_ids_are_unique() -> None:
    edge_ids = [edge["edge_id"] for edge in build_tables().edges]

    assert len(edge_ids) == len(set(edge_ids))


def test_all_edge_endpoints_exist_in_nodes() -> None:
    tables = build_tables()
    node_ids = {node["node_id"] for node in tables.nodes}

    assert all(edge["source_id"] in node_ids for edge in tables.edges)
    assert all(edge["target_id"] in node_ids for edge in tables.edges)


def test_expected_node_types_are_present() -> None:
    node_types = {node["node_type"] for node in build_tables().nodes}

    assert node_types == EXPECTED_NODE_TYPES


def test_expected_edge_types_are_present() -> None:
    edge_types = {edge["edge_type"] for edge in build_tables().edges}

    assert edge_types == EXPECTED_EDGE_TYPES


def test_graph_tables_can_be_written(tmp_path: Path) -> None:
    paths = write_graph_tables(build_tables(), tmp_path)

    assert paths.nodes.is_file()
    assert paths.edges.is_file()
    with paths.nodes.open(encoding="utf-8", newline="") as handle:
        assert next(csv.DictReader(handle))["node_id"] == "device_record_001"
    with paths.edges.open(encoding="utf-8", newline="") as handle:
        assert next(csv.DictReader(handle))["edge_id"] == "edge_000001"

"""Tests for the HydroKG low-R/high-power subset analysis."""

from pathlib import Path

from hydrokg.analysis.subsets import (
    build_concept_counts,
    build_pathway_summary,
    get_connected_concept_nodes,
    load_graph_edges,
    load_graph_nodes,
    load_r_centered_device_table,
    select_low_r_high_power_devices,
    write_low_r_high_power_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIRECTORY = REPOSITORY_ROOT / "data" / "processed"


def build_subset_tables():
    device_table = load_r_centered_device_table(
        PROCESSED_DIRECTORY / "hydrokg_r_centered_device_table.csv"
    )
    nodes = load_graph_nodes(PROCESSED_DIRECTORY / "hydrokg_nodes.csv")
    edges = load_graph_edges(PROCESSED_DIRECTORY / "hydrokg_edges.csv")
    selected = select_low_r_high_power_devices(device_table)
    concepts = get_connected_concept_nodes(selected, nodes, edges)
    return (
        selected,
        nodes,
        build_concept_counts(selected, concepts),
        build_pathway_summary(selected),
    )


def test_selected_device_table_is_not_empty() -> None:
    selected, _, _, _ = build_subset_tables()

    assert not selected.empty


def test_all_selected_devices_are_low_r() -> None:
    selected, _, _, _ = build_subset_tables()

    assert selected["low_R_flag"].all()


def test_all_selected_devices_are_high_power() -> None:
    selected, _, _, _ = build_subset_tables()

    assert selected["high_power_flag"].all()


def test_selected_device_ids_exist_as_device_record_nodes() -> None:
    selected, nodes, _, _ = build_subset_tables()
    device_node_ids = set(
        nodes.loc[nodes["node_type"].eq("DeviceRecord"), "node_id"]
    )

    assert set(selected["device_record_id"]) <= device_node_ids


def test_concept_counts_table_is_not_empty() -> None:
    _, _, concept_counts, _ = build_subset_tables()

    assert not concept_counts.empty


def test_pathway_summary_table_is_not_empty() -> None:
    _, _, _, pathway_summary = build_subset_tables()

    assert not pathway_summary.empty


def test_subset_outputs_can_be_written(tmp_path: Path) -> None:
    selected, _, concept_counts, pathway_summary = build_subset_tables()
    paths = write_low_r_high_power_outputs(
        selected,
        concept_counts,
        pathway_summary,
        tmp_path / "tables",
    )

    assert paths.devices.is_file()
    assert paths.concept_counts.is_file()
    assert paths.pathway_summary.is_file()

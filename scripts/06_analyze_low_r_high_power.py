"""Analyze the low-resistance, high-power HydroKG device subset."""

from __future__ import annotations

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
RESULTS_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"


def main() -> int:
    """Build and write the low-R/high-power subset analysis tables."""
    device_table = load_r_centered_device_table(
        PROCESSED_DIRECTORY / "hydrokg_r_centered_device_table.csv"
    )
    nodes = load_graph_nodes(PROCESSED_DIRECTORY / "hydrokg_nodes.csv")
    edges = load_graph_edges(PROCESSED_DIRECTORY / "hydrokg_edges.csv")

    selected_devices = select_low_r_high_power_devices(device_table)
    connected_concepts = get_connected_concept_nodes(
        selected_devices,
        nodes,
        edges,
    )
    concept_counts = build_concept_counts(
        selected_devices,
        connected_concepts,
    )
    pathway_summary = build_pathway_summary(selected_devices)
    paths = write_low_r_high_power_outputs(
        selected_devices,
        concept_counts,
        pathway_summary,
        RESULTS_DIRECTORY,
    )

    print(f"Selected devices: {len(selected_devices)}")
    for path in (
        paths.devices,
        paths.concept_counts,
        paths.pathway_summary,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build figure-ready R, material, structure, and power statistics."""

from __future__ import annotations

from pathlib import Path

from hydrokg.analysis.figure_stats import (
    build_r_bin_by_material_structure_counts,
    load_r_centered_device_table,
    summarize_power_by_material_structure,
    summarize_r_by_material_class,
    summarize_r_by_structure_class,
    write_figure_statistics_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEVICE_TABLE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "hydrokg_r_centered_device_table.csv"
)
RESULTS_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"


def main() -> int:
    """Build and write all Stage 5A figure-ready statistics tables."""
    device_table = load_r_centered_device_table(DEVICE_TABLE_PATH)
    material_summary = summarize_r_by_material_class(device_table)
    structure_summary = summarize_r_by_structure_class(device_table)
    power_summary = summarize_power_by_material_structure(device_table)
    r_bin_counts = build_r_bin_by_material_structure_counts(device_table)
    paths = write_figure_statistics_outputs(
        material_summary,
        structure_summary,
        power_summary,
        r_bin_counts,
        RESULTS_DIRECTORY,
    )

    print(f"Devices: {len(device_table)}")
    for path in (
        paths.material_summary,
        paths.structure_summary,
        paths.power_summary,
        paths.r_bin_counts,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

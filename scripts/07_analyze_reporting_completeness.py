"""Analyze reporting completeness across HydroKG device records."""

from __future__ import annotations

from pathlib import Path

from hydrokg.analysis.reporting import (
    calculate_device_completeness,
    calculate_field_completeness,
    load_r_centered_device_table,
    summarize_completeness_by_material_class,
    write_reporting_outputs,
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
    """Build and write all reporting completeness tables."""
    device_table = load_r_centered_device_table(DEVICE_TABLE_PATH)
    field_completeness = calculate_field_completeness(device_table)
    device_completeness = calculate_device_completeness(device_table)
    material_class_summary = summarize_completeness_by_material_class(
        device_table,
        device_completeness,
    )
    paths = write_reporting_outputs(
        field_completeness,
        material_class_summary,
        device_completeness,
        RESULTS_DIRECTORY,
    )

    print(f"Devices: {len(device_completeness)}")
    print(f"Reporting fields: {len(field_completeness)}")
    for path in (
        paths.field_completeness,
        paths.material_class_summary,
        paths.device_completeness,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

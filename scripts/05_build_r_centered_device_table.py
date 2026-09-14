"""Build the HydroKG R-centered device and summary tables."""

from __future__ import annotations

from pathlib import Path

from hydrokg.analysis.r_centered import (
    build_r_centered_device_table,
    load_seed_csv,
    write_r_centered_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "raw"
    / "hydrovoltaic_ml_curated_159_seed.csv"
)
PROCESSED_DIRECTORY = REPOSITORY_ROOT / "data" / "processed"
RESULTS_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"


def main() -> int:
    """Build and write all R-centered analysis tables."""
    table = build_r_centered_device_table(load_seed_csv(SEED_PATH))
    paths = write_r_centered_outputs(
        table,
        processed_directory=PROCESSED_DIRECTORY,
        results_directory=RESULTS_DIRECTORY,
    )

    print(f"Devices: {len(table)}")
    for path in (
        paths.device_table,
        paths.r_bin_summary,
        paths.power_by_r_bin_summary,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

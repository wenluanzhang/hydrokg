"""Validate the frozen HydroKG seed dataset."""

from __future__ import annotations

from pathlib import Path

from hydrokg.data.validation import (
    load_csv,
    validate_data,
    write_validation_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "raw"
    / "hydrovoltaic_ml_curated_159_seed.csv"
)
VALIDATION_SUMMARY_PATH = (
    REPOSITORY_ROOT / "results" / "tables" / "data_validation_summary.csv"
)
MISSING_SUMMARY_PATH = (
    REPOSITORY_ROOT / "results" / "tables" / "key_column_missing_summary.csv"
)


def main() -> int:
    """Validate the seed data and return a process exit code."""
    result = validate_data(load_csv(INPUT_PATH))

    print(f"Input: {INPUT_PATH.relative_to(REPOSITORY_ROOT)}")
    print(f"Rows: {result.row_count}")
    print(f"Columns: {result.column_count}")
    print(
        f"Missing required columns: {len(result.missing_required_columns)}"
    )

    write_validation_outputs(
        result=result,
        output_directory=VALIDATION_SUMMARY_PATH.parent,
        input_file=INPUT_PATH.relative_to(REPOSITORY_ROOT),
    )

    print(
        "Wrote: "
        f"{VALIDATION_SUMMARY_PATH.relative_to(REPOSITORY_ROOT).as_posix()}"
    )
    print(
        f"Wrote: {MISSING_SUMMARY_PATH.relative_to(REPOSITORY_ROOT).as_posix()}"
    )
    return 0 if result.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

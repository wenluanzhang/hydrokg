"""Tests for loading and validating the frozen seed dataset."""

import csv
from pathlib import Path

from hydrokg.data.validation import (
    REQUIRED_COLUMNS,
    load_csv,
    validate_data,
    write_validation_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SEED_CSV = (
    REPOSITORY_ROOT
    / "data"
    / "raw"
    / "hydrovoltaic_ml_curated_159_seed.csv"
)


def test_load_seed_csv() -> None:
    data = load_csv(SEED_CSV)

    assert data.fieldnames
    assert data.rows


def test_seed_csv_has_159_rows() -> None:
    assert load_csv(SEED_CSV).row_count == 159


def test_seed_csv_has_52_columns() -> None:
    assert load_csv(SEED_CSV).column_count == 52


def test_seed_csv_has_required_columns() -> None:
    data = load_csv(SEED_CSV)
    result = validate_data(data)

    assert set(REQUIRED_COLUMNS).issubset(data.fieldnames)
    assert result.missing_required_columns == ()
    assert result.is_valid


def test_validation_outputs_can_be_written(tmp_path: Path) -> None:
    result = validate_data(load_csv(SEED_CSV))

    paths = write_validation_outputs(
        result=result,
        output_directory=tmp_path,
        input_file=Path("data/raw") / SEED_CSV.name,
    )

    assert paths.validation_summary.is_file()
    assert paths.missing_summary.is_file()

    with paths.validation_summary.open(encoding="utf-8", newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert summary["row_count"] == "159"
    assert summary["column_count"] == "52"
    assert summary["status"] == "pass"

    with paths.missing_summary.open(
        encoding="utf-8", newline=""
    ) as handle:
        missing_rows = list(csv.DictReader(handle))
    assert len(missing_rows) == len(REQUIRED_COLUMNS)

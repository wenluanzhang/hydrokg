"""Reusable validation helpers for the frozen HydroKG seed dataset."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REQUIRED_COLUMNS = (
    "paper_doi",
    "ref_year",
    "device_structure",
    "active_material_raw",
    "material_class",
    "structure_class",
    "primary_mobile_ion",
    "ion_origin",
    "electrode_symmetry",
    "voc_V",
    "jsc_uA_cm2",
    "power_density_uW_cm2",
    "estimated_power_density_uW_cm2",
    "log_estimated_power_density",
    "internal_resistance_Mohm",
    "log_internal_resistance_Mohm",
    "has_internal_resistance",
    "dominant_mechanism",
    "mechanism_simple",
)

VALIDATION_SUMMARY_FILENAME = "data_validation_summary.csv"
MISSING_SUMMARY_FILENAME = "key_column_missing_summary.csv"


@dataclass(frozen=True)
class LoadedCsv:
    """CSV field names and rows loaded from disk."""

    fieldnames: tuple[str, ...]
    rows: tuple[dict[str, str | None], ...]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.fieldnames)


@dataclass(frozen=True)
class ValidationResult:
    """Results of validating a loaded CSV dataset."""

    row_count: int
    column_count: int
    required_columns: tuple[str, ...]
    missing_required_columns: tuple[str, ...]
    missing_counts: tuple[tuple[str, int], ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_required_columns


@dataclass(frozen=True)
class ValidationOutputPaths:
    """Paths written by :func:`write_validation_outputs`."""

    validation_summary: Path
    missing_summary: Path


def is_missing(value: str | None) -> bool:
    """Return whether a CSV value is absent or blank."""
    return value is None or not value.strip()


def load_csv(path: Path | str) -> LoadedCsv:
    """Load a CSV file while preserving its declared column order."""
    csv_path = Path(path)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return LoadedCsv(
            fieldnames=tuple(reader.fieldnames or ()),
            rows=tuple(reader),
        )


def validate_data(
    data: LoadedCsv,
    required_columns: Sequence[str] = REQUIRED_COLUMNS,
) -> ValidationResult:
    """Validate required columns and count missing values in each one."""
    required = tuple(required_columns)
    missing_required = tuple(
        column for column in required if column not in data.fieldnames
    )
    missing_counts = tuple(
        (
            column,
            sum(is_missing(row.get(column)) for row in data.rows),
        )
        for column in required
    )
    return ValidationResult(
        row_count=data.row_count,
        column_count=data.column_count,
        required_columns=required,
        missing_required_columns=missing_required,
        missing_counts=missing_counts,
    )


def write_validation_outputs(
    result: ValidationResult,
    output_directory: Path | str,
    input_file: Path | str,
) -> ValidationOutputPaths:
    """Write validation and required-column missingness summaries."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    validation_summary = output_directory / VALIDATION_SUMMARY_FILENAME
    missing_summary = output_directory / MISSING_SUMMARY_FILENAME

    with validation_summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "input_file",
                "row_count",
                "column_count",
                "required_column_count",
                "missing_required_columns",
                "status",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "input_file": Path(input_file).as_posix(),
                "row_count": result.row_count,
                "column_count": result.column_count,
                "required_column_count": len(result.required_columns),
                "missing_required_columns": ";".join(
                    result.missing_required_columns
                ),
                "status": "pass" if result.is_valid else "fail",
            }
        )

    with missing_summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "column",
                "missing_count",
                "missing_fraction",
                "non_missing_count",
            ),
        )
        writer.writeheader()
        for column, missing_count in result.missing_counts:
            writer.writerow(
                {
                    "column": column,
                    "missing_count": missing_count,
                    "missing_fraction": (
                        missing_count / result.row_count
                        if result.row_count
                        else 0.0
                    ),
                    "non_missing_count": result.row_count - missing_count,
                }
            )

    return ValidationOutputPaths(
        validation_summary=validation_summary,
        missing_summary=missing_summary,
    )

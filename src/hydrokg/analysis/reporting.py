"""Analyze experimental and performance field reporting completeness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

FIELD_COMPLETENESS_FILENAME = "hydrokg_reporting_field_completeness.csv"
MATERIAL_CLASS_FILENAME = (
    "hydrokg_reporting_completeness_by_material_class.csv"
)
DEVICE_COMPLETENESS_FILENAME = "hydrokg_device_reporting_completeness.csv"

REQUESTED_REPORTING_FIELDS = (
    "active_material_raw",
    "device_structure",
    "primary_mobile_ion",
    "top_electrode",
    "bottom_electrode",
    "voc_V",
    "jsc_uA_cm2",
    "power_density_uW_cm2",
    "internal_resistance_Mohm",
    "stability_time_min",
    "rh_percent",
)
DEVICE_IDENTITY_COLUMNS = (
    "device_record_id",
    "paper_doi",
    "material_class",
    "structure_class",
    "r_bin",
    "low_R_flag",
    "high_power_flag",
)
FIELD_COMPLETENESS_COLUMNS = (
    "field",
    "reported_count",
    "missing_count",
    "reported_fraction",
)
DEVICE_COMPLETENESS_COLUMNS = (
    *DEVICE_IDENTITY_COLUMNS,
    "reported_field_count",
    "total_field_count",
    "reporting_completeness_score",
)
MATERIAL_CLASS_COLUMNS = (
    "material_class",
    "device_count",
    "mean_reporting_completeness_score",
    "median_reporting_completeness_score",
    "r_reported_fraction",
    "power_reported_fraction",
)


@dataclass(frozen=True)
class ReportingOutputPaths:
    """Paths written by :func:`write_reporting_outputs`."""

    field_completeness: Path
    material_class_summary: Path
    device_completeness: Path


def load_r_centered_device_table(path: Path | str) -> pd.DataFrame:
    """Load the processed R-centered device table."""
    table = pd.read_csv(path)
    _require_columns(
        table,
        (
            *DEVICE_IDENTITY_COLUMNS,
            *REQUESTED_REPORTING_FIELDS,
        ),
        "R-centered device table",
    )
    return table


def available_reporting_fields(
    device_table: pd.DataFrame,
) -> tuple[str, ...]:
    """Return requested reporting fields available in the processed table."""
    return tuple(
        field
        for field in REQUESTED_REPORTING_FIELDS
        if field in device_table.columns
    )


def calculate_field_completeness(
    device_table: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate reported and missing counts for each available field."""
    reporting_fields = available_reporting_fields(device_table)
    rows = []
    for field in reporting_fields:
        reported = _reported_mask(device_table[field])
        reported_count = int(reported.sum())
        rows.append(
            {
                "field": field,
                "reported_count": reported_count,
                "missing_count": len(device_table) - reported_count,
                "reported_fraction": (
                    reported_count / len(device_table)
                    if len(device_table)
                    else 0.0
                ),
            }
        )
    return pd.DataFrame(rows, columns=FIELD_COMPLETENESS_COLUMNS)


def calculate_device_completeness(
    device_table: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate a reporting completeness score for every device."""
    _require_columns(
        device_table,
        DEVICE_IDENTITY_COLUMNS,
        "R-centered device table",
    )
    reporting_fields = available_reporting_fields(device_table)
    if not reporting_fields:
        raise ValueError("R-centered device table has no reporting fields")

    reported = pd.DataFrame(
        {
            field: _reported_mask(device_table[field])
            for field in reporting_fields
        },
        index=device_table.index,
    )
    output = device_table.loc[:, DEVICE_IDENTITY_COLUMNS].copy()
    output["reported_field_count"] = reported.sum(axis=1).astype(int)
    output["total_field_count"] = len(reporting_fields)
    output["reporting_completeness_score"] = (
        output["reported_field_count"] / len(reporting_fields)
    )
    return output.loc[:, DEVICE_COMPLETENESS_COLUMNS]


def summarize_completeness_by_material_class(
    device_table: pd.DataFrame,
    device_completeness: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize device reporting completeness by material class."""
    _require_columns(
        device_table,
        (
            "device_record_id",
            "material_class",
            "internal_resistance_Mohm",
            "power_density_uW_cm2",
        ),
        "R-centered device table",
    )
    if device_completeness is None:
        device_completeness = calculate_device_completeness(device_table)
    _require_columns(
        device_completeness,
        ("device_record_id", "reporting_completeness_score"),
        "device completeness table",
    )

    reporting = device_table.loc[
        :,
        (
            "device_record_id",
            "material_class",
            "internal_resistance_Mohm",
            "power_density_uW_cm2",
        ),
    ].merge(
        device_completeness.loc[
            :,
            ("device_record_id", "reporting_completeness_score"),
        ],
        on="device_record_id",
        how="inner",
        validate="one_to_one",
    )
    reporting["r_reported"] = _reported_mask(
        reporting["internal_resistance_Mohm"]
    )
    reporting["power_reported"] = _reported_mask(
        reporting["power_density_uW_cm2"]
    )
    summary = (
        reporting.groupby("material_class", sort=True, dropna=False)
        .agg(
            device_count=("device_record_id", "nunique"),
            mean_reporting_completeness_score=(
                "reporting_completeness_score",
                "mean",
            ),
            median_reporting_completeness_score=(
                "reporting_completeness_score",
                "median",
            ),
            r_reported_fraction=("r_reported", "mean"),
            power_reported_fraction=("power_reported", "mean"),
        )
        .reset_index()
    )
    return summary.loc[:, MATERIAL_CLASS_COLUMNS]


def write_reporting_outputs(
    field_completeness: pd.DataFrame,
    material_class_summary: pd.DataFrame,
    device_completeness: pd.DataFrame,
    output_directory: Path | str,
) -> ReportingOutputPaths:
    """Write all reporting completeness result tables."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = ReportingOutputPaths(
        field_completeness=(
            output_directory / FIELD_COMPLETENESS_FILENAME
        ),
        material_class_summary=output_directory / MATERIAL_CLASS_FILENAME,
        device_completeness=output_directory / DEVICE_COMPLETENESS_FILENAME,
    )
    field_completeness.loc[:, FIELD_COMPLETENESS_COLUMNS].to_csv(
        paths.field_completeness,
        index=False,
    )
    material_class_summary.loc[:, MATERIAL_CLASS_COLUMNS].to_csv(
        paths.material_class_summary,
        index=False,
    )
    device_completeness.loc[:, DEVICE_COMPLETENESS_COLUMNS].to_csv(
        paths.device_completeness,
        index=False,
    )
    return paths


def _reported_mask(values: pd.Series) -> pd.Series:
    reported = values.notna()
    if pd.api.types.is_object_dtype(values.dtype) or isinstance(
        values.dtype,
        pd.StringDtype,
    ):
        reported &= values.astype("string").str.strip().ne("")
    return reported.fillna(False)


def _require_columns(
    table: pd.DataFrame,
    required_columns: tuple[str, ...],
    table_name: str,
) -> None:
    missing_columns = sorted(set(required_columns) - set(table.columns))
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"{table_name} is missing required columns: {missing}")

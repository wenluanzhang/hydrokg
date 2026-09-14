"""Build figure-ready resistance, material, structure, and power statistics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

MATERIAL_SUMMARY_FILENAME = "hydrokg_r_by_material_class_summary.csv"
STRUCTURE_SUMMARY_FILENAME = "hydrokg_r_by_structure_class_summary.csv"
POWER_SUMMARY_FILENAME = (
    "hydrokg_power_by_material_structure_summary.csv"
)
R_BIN_COUNTS_FILENAME = (
    "hydrokg_r_bin_by_material_structure_counts.csv"
)

R_BIN_ORDER = ("missing_R", "low_R", "high_R")
REQUIRED_COLUMNS = (
    "device_record_id",
    "material_class",
    "structure_class",
    "internal_resistance_Mohm",
    "log_internal_resistance_Mohm",
    "estimated_power_density_uW_cm2",
    "log_estimated_power_density",
    "r_bin",
    "low_R_flag",
    "high_power_flag",
)
GROUP_SUMMARY_COLUMNS = (
    "device_count",
    "r_reported_count",
    "r_reported_fraction",
    "low_R_count",
    "high_R_count",
    "missing_R_count",
    "low_R_fraction",
    "median_internal_resistance_Mohm",
    "median_log_internal_resistance_Mohm",
    "median_estimated_power_density_uW_cm2",
    "median_log_estimated_power_density",
)
MATERIAL_SUMMARY_COLUMNS = (
    "material_class",
    *GROUP_SUMMARY_COLUMNS,
)
STRUCTURE_SUMMARY_COLUMNS = (
    "structure_class",
    *GROUP_SUMMARY_COLUMNS,
)
POWER_SUMMARY_COLUMNS = (
    "material_class",
    "structure_class",
    "device_count",
    "r_reported_count",
    "low_R_count",
    "high_power_count",
    "low_R_high_power_count",
    "median_internal_resistance_Mohm",
    "median_estimated_power_density_uW_cm2",
    "median_log_estimated_power_density",
)
R_BIN_COUNT_COLUMNS = (
    "material_class",
    "structure_class",
    "r_bin",
    "device_count",
)


@dataclass(frozen=True)
class FigureStatisticsOutputPaths:
    """Paths written by :func:`write_figure_statistics_outputs`."""

    material_summary: Path
    structure_summary: Path
    power_summary: Path
    r_bin_counts: Path


def load_r_centered_device_table(path: Path | str) -> pd.DataFrame:
    """Load and type the processed R-centered device table."""
    table = pd.read_csv(path)
    _require_columns(table, REQUIRED_COLUMNS)
    for column in ("low_R_flag", "high_power_flag"):
        table[column] = _to_boolean(table[column])
    return table


def summarize_r_by_material_class(device_table: pd.DataFrame) -> pd.DataFrame:
    """Summarize resistance reporting, bins, and power by material class."""
    return _summarize_r_by_group(device_table, "material_class").loc[
        :,
        MATERIAL_SUMMARY_COLUMNS,
    ]


def summarize_r_by_structure_class(device_table: pd.DataFrame) -> pd.DataFrame:
    """Summarize resistance reporting, bins, and power by structure class."""
    return _summarize_r_by_group(device_table, "structure_class").loc[
        :,
        STRUCTURE_SUMMARY_COLUMNS,
    ]


def summarize_power_by_material_structure(
    device_table: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize power and resistance by material/structure combination."""
    _require_columns(device_table, REQUIRED_COLUMNS)
    table = device_table.copy()
    table["r_reported"] = table["internal_resistance_Mohm"].notna()
    table["low_R"] = table["r_bin"].eq("low_R")
    table["high_power"] = _to_boolean(table["high_power_flag"])
    table["low_R_high_power"] = table["low_R"] & table["high_power"]

    summary = (
        table.groupby(
            ["material_class", "structure_class"],
            sort=True,
            dropna=False,
        )
        .agg(
            device_count=("device_record_id", "size"),
            r_reported_count=("r_reported", "sum"),
            low_R_count=("low_R", "sum"),
            high_power_count=("high_power", "sum"),
            low_R_high_power_count=("low_R_high_power", "sum"),
            median_internal_resistance_Mohm=(
                "internal_resistance_Mohm",
                "median",
            ),
            median_estimated_power_density_uW_cm2=(
                "estimated_power_density_uW_cm2",
                "median",
            ),
            median_log_estimated_power_density=(
                "log_estimated_power_density",
                "median",
            ),
        )
        .reset_index()
    )
    _convert_count_columns(
        summary,
        (
            "device_count",
            "r_reported_count",
            "low_R_count",
            "high_power_count",
            "low_R_high_power_count",
        ),
    )
    return summary.loc[:, POWER_SUMMARY_COLUMNS]


def build_r_bin_by_material_structure_counts(
    device_table: pd.DataFrame,
) -> pd.DataFrame:
    """Count each R bin for every observed material/structure combination."""
    _require_columns(device_table, REQUIRED_COLUMNS)
    group_columns = ["material_class", "structure_class"]
    combinations = (
        device_table.loc[:, group_columns]
        .drop_duplicates()
        .sort_values(group_columns, kind="stable")
    )
    bins = pd.DataFrame({"r_bin": R_BIN_ORDER})
    combinations["_join_key"] = 1
    bins["_join_key"] = 1
    complete_index = combinations.merge(bins, on="_join_key").drop(
        columns="_join_key"
    )

    counts = (
        device_table.groupby(
            [*group_columns, "r_bin"],
            sort=True,
            dropna=False,
        )
        .size()
        .rename("device_count")
        .reset_index()
    )
    output = complete_index.merge(
        counts,
        on=[*group_columns, "r_bin"],
        how="left",
        validate="one_to_one",
    )
    output["device_count"] = output["device_count"].fillna(0).astype(int)
    output["r_bin"] = pd.Categorical(
        output["r_bin"],
        categories=R_BIN_ORDER,
        ordered=True,
    )
    output = output.sort_values(
        [*group_columns, "r_bin"],
        kind="stable",
    )
    output["r_bin"] = output["r_bin"].astype("string")
    return output.loc[:, R_BIN_COUNT_COLUMNS].reset_index(drop=True)


def write_figure_statistics_outputs(
    material_summary: pd.DataFrame,
    structure_summary: pd.DataFrame,
    power_summary: pd.DataFrame,
    r_bin_counts: pd.DataFrame,
    output_directory: Path | str,
) -> FigureStatisticsOutputPaths:
    """Write all Stage 5A figure-ready statistics tables."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = FigureStatisticsOutputPaths(
        material_summary=output_directory / MATERIAL_SUMMARY_FILENAME,
        structure_summary=output_directory / STRUCTURE_SUMMARY_FILENAME,
        power_summary=output_directory / POWER_SUMMARY_FILENAME,
        r_bin_counts=output_directory / R_BIN_COUNTS_FILENAME,
    )
    material_summary.loc[:, MATERIAL_SUMMARY_COLUMNS].to_csv(
        paths.material_summary,
        index=False,
    )
    structure_summary.loc[:, STRUCTURE_SUMMARY_COLUMNS].to_csv(
        paths.structure_summary,
        index=False,
    )
    power_summary.loc[:, POWER_SUMMARY_COLUMNS].to_csv(
        paths.power_summary,
        index=False,
    )
    r_bin_counts.loc[:, R_BIN_COUNT_COLUMNS].to_csv(
        paths.r_bin_counts,
        index=False,
    )
    return paths


def _summarize_r_by_group(
    device_table: pd.DataFrame,
    group_column: str,
) -> pd.DataFrame:
    _require_columns(device_table, REQUIRED_COLUMNS)
    table = device_table.copy()
    table["r_reported"] = table["internal_resistance_Mohm"].notna()
    table["low_R"] = table["r_bin"].eq("low_R")
    table["high_R"] = table["r_bin"].eq("high_R")
    table["missing_R"] = table["r_bin"].eq("missing_R")

    summary = (
        table.groupby(group_column, sort=True, dropna=False)
        .agg(
            device_count=("device_record_id", "size"),
            r_reported_count=("r_reported", "sum"),
            low_R_count=("low_R", "sum"),
            high_R_count=("high_R", "sum"),
            missing_R_count=("missing_R", "sum"),
            median_internal_resistance_Mohm=(
                "internal_resistance_Mohm",
                "median",
            ),
            median_log_internal_resistance_Mohm=(
                "log_internal_resistance_Mohm",
                "median",
            ),
            median_estimated_power_density_uW_cm2=(
                "estimated_power_density_uW_cm2",
                "median",
            ),
            median_log_estimated_power_density=(
                "log_estimated_power_density",
                "median",
            ),
        )
        .reset_index()
    )
    _convert_count_columns(
        summary,
        (
            "device_count",
            "r_reported_count",
            "low_R_count",
            "high_R_count",
            "missing_R_count",
        ),
    )
    summary.insert(
        3,
        "r_reported_fraction",
        summary["r_reported_count"] / summary["device_count"],
    )
    summary.insert(
        8,
        "low_R_fraction",
        summary["low_R_count"] / summary["device_count"],
    )
    return summary


def _convert_count_columns(
    table: pd.DataFrame,
    columns: tuple[str, ...],
) -> None:
    for column in columns:
        table[column] = table[column].astype(int)


def _require_columns(
    table: pd.DataFrame,
    required_columns: tuple[str, ...],
) -> None:
    missing_columns = sorted(set(required_columns) - set(table.columns))
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(
            f"R-centered device table is missing required columns: {missing}"
        )


def _to_boolean(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False)
    normalized = values.astype("string").str.strip().str.lower()
    return normalized.isin(("1", "true", "yes"))

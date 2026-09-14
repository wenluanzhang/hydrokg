"""Build R-centered device-level analysis tables."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DEVICE_TABLE_FILENAME = "hydrokg_r_centered_device_table.csv"
R_BIN_SUMMARY_FILENAME = "hydrokg_r_bin_summary.csv"
POWER_BY_R_BIN_SUMMARY_FILENAME = "hydrokg_power_by_r_bin_summary.csv"

SOURCE_COLUMNS = (
    "paper_doi",
    "ref_year",
    "active_material_raw",
    "device_structure",
    "material_class",
    "structure_class",
    "ion_type",
    "primary_mobile_ion",
    "inorganic_electrolyte_present",
    "polyelectrolyte_present",
    "top_electrode",
    "bottom_electrode",
    "electrode_symmetry",
    "metal_electrode",
    "auxiliary_redox_present",
    "dominant_mechanism",
    "mechanism_simple",
    "rh_percent",
    "voc_V",
    "jsc_uA_cm2",
    "power_density_uW_cm2",
    "internal_resistance_Mohm",
    "stability_time_min",
    "log_internal_resistance_Mohm",
    "has_internal_resistance",
    "estimated_power_density_uW_cm2",
    "log_estimated_power_density",
)
BOOLEAN_COLUMNS = (
    "inorganic_electrolyte_present",
    "polyelectrolyte_present",
    "electrode_symmetry",
    "metal_electrode",
    "auxiliary_redox_present",
    "has_internal_resistance",
)
NUMERIC_COLUMNS = (
    "rh_percent",
    "voc_V",
    "jsc_uA_cm2",
    "power_density_uW_cm2",
    "internal_resistance_Mohm",
    "stability_time_min",
    "log_internal_resistance_Mohm",
    "estimated_power_density_uW_cm2",
    "log_estimated_power_density",
)
R_BIN_ORDER = ("missing_R", "low_R", "high_R")
R_LOW_THRESHOLD_MOHM = 0.1
HIGH_POWER_QUANTILE = 0.75


@dataclass(frozen=True)
class RCenteredOutputPaths:
    """Paths written by :func:`write_r_centered_outputs`."""

    device_table: Path
    r_bin_summary: Path
    power_by_r_bin_summary: Path


def load_seed_csv(path: Path | str) -> pd.DataFrame:
    """Load the curated seed CSV in its original row order."""
    return pd.read_csv(path, encoding="utf-8-sig")


def create_device_record_ids(row_count: int) -> tuple[str, ...]:
    """Create graph-compatible device identifiers in deterministic order."""
    if row_count < 0:
        raise ValueError("row_count must be non-negative")
    return tuple(
        f"device_record_{index:03d}" for index in range(1, row_count + 1)
    )


def build_r_centered_device_table(seed: pd.DataFrame) -> pd.DataFrame:
    """Create a typed device table with resistance and power flags."""
    missing_columns = sorted(set(SOURCE_COLUMNS) - set(seed.columns))
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Seed CSV is missing required columns: {missing}")

    table = seed.loc[:, SOURCE_COLUMNS].copy()
    table.insert(
        0,
        "device_record_id",
        create_device_record_ids(len(table)),
    )

    table["ref_year"] = pd.to_numeric(table["ref_year"], errors="coerce").astype(
        "Int64"
    )
    for column in NUMERIC_COLUMNS:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    for column in BOOLEAN_COLUMNS:
        table[column] = _to_boolean(table[column])

    resistance = table["internal_resistance_Mohm"]
    table["r_reported_flag"] = resistance.notna()
    table["r_bin"] = "missing_R"
    table.loc[
        resistance.notna() & resistance.le(R_LOW_THRESHOLD_MOHM),
        "r_bin",
    ] = "low_R"
    table.loc[
        resistance.notna() & resistance.gt(R_LOW_THRESHOLD_MOHM),
        "r_bin",
    ] = "high_R"
    table["low_R_flag"] = table["r_bin"].eq("low_R")

    table["power_reported_flag"] = table["power_density_uW_cm2"].notna()
    estimated_power = table["estimated_power_density_uW_cm2"]
    table["estimated_power_available_flag"] = estimated_power.notna()
    power_threshold = estimated_power.dropna().quantile(HIGH_POWER_QUANTILE)
    table["high_power_flag"] = (
        table["estimated_power_available_flag"]
        & estimated_power.ge(power_threshold)
        if pd.notna(power_threshold)
        else False
    )
    return table


def build_r_bin_summary(table: pd.DataFrame) -> pd.DataFrame:
    """Count devices and calculate their fraction in each R bin."""
    counts = table["r_bin"].value_counts().reindex(R_BIN_ORDER, fill_value=0)
    summary = counts.rename_axis("r_bin").reset_index(name="device_count")
    summary["fraction"] = summary["device_count"] / len(table)
    return summary


def build_power_by_r_bin_summary(table: pd.DataFrame) -> pd.DataFrame:
    """Summarize estimated power within each R bin."""
    grouped = table.groupby("r_bin", sort=False)
    summary = grouped.agg(
        device_count=("device_record_id", "size"),
        median_estimated_power_density_uW_cm2=(
            "estimated_power_density_uW_cm2",
            "median",
        ),
        median_log_estimated_power_density=(
            "log_estimated_power_density",
            "median",
        ),
    )
    return summary.reindex(R_BIN_ORDER).rename_axis("r_bin").reset_index()


def write_r_centered_outputs(
    device_table: pd.DataFrame,
    processed_directory: Path | str,
    results_directory: Path | str,
) -> RCenteredOutputPaths:
    """Write the device table and both R-bin summary tables."""
    processed_directory = Path(processed_directory)
    results_directory = Path(results_directory)
    processed_directory.mkdir(parents=True, exist_ok=True)
    results_directory.mkdir(parents=True, exist_ok=True)

    paths = RCenteredOutputPaths(
        device_table=processed_directory / DEVICE_TABLE_FILENAME,
        r_bin_summary=results_directory / R_BIN_SUMMARY_FILENAME,
        power_by_r_bin_summary=(
            results_directory / POWER_BY_R_BIN_SUMMARY_FILENAME
        ),
    )
    device_table.to_csv(paths.device_table, index=False)
    build_r_bin_summary(device_table).to_csv(paths.r_bin_summary, index=False)
    build_power_by_r_bin_summary(device_table).to_csv(
        paths.power_by_r_bin_summary,
        index=False,
    )
    return paths


def _to_boolean(values: pd.Series) -> pd.Series:
    normalized = values.astype("string").str.strip().str.lower()
    return normalized.isin(("1", "true", "yes"))

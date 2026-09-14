"""Tests for HydroKG R-centered device analysis."""

from pathlib import Path

import pandas as pd
import pytest

from hydrokg.analysis.r_centered import (
    HIGH_POWER_QUANTILE,
    R_LOW_THRESHOLD_MOHM,
    build_r_bin_summary,
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


def build_device_table():
    return build_r_centered_device_table(load_seed_csv(SEED_PATH))


def test_output_device_table_has_159_rows() -> None:
    assert len(build_device_table()) == 159


def test_device_record_ids_are_unique_and_deterministic() -> None:
    device_ids = build_device_table()["device_record_id"]

    assert device_ids.is_unique
    assert device_ids.iloc[0] == "device_record_001"
    assert device_ids.iloc[-1] == "device_record_159"


def test_r_bin_contains_only_expected_values() -> None:
    assert set(build_device_table()["r_bin"]) <= {
        "missing_R",
        "low_R",
        "high_R",
    }


def test_r_bin_counts_sum_to_159() -> None:
    summary = build_r_bin_summary(build_device_table())

    assert int(summary["device_count"].sum()) == 159


def test_r_bin_counts_match_final_published_definition() -> None:
    counts = build_device_table()["r_bin"].value_counts().to_dict()

    assert counts == {"high_R": 57, "low_R": 55, "missing_R": 47}


@pytest.mark.parametrize(
    ("resistance", "expected_bin"),
    (
        (pd.NA, "missing_R"),
        (0.0999, "low_R"),
        (0.1, "low_R"),
        (0.1001, "high_R"),
        (1.0, "high_R"),
    ),
)
def test_r_bin_boundary_is_inclusive_on_low_side(
    resistance: object,
    expected_bin: str,
) -> None:
    seed = load_seed_csv(SEED_PATH).iloc[[0]].copy()
    seed["internal_resistance_Mohm"] = resistance

    assert build_r_centered_device_table(seed).loc[0, "r_bin"] == expected_bin
    assert R_LOW_THRESHOLD_MOHM == 0.1


def test_low_r_flag_is_true_only_for_low_r() -> None:
    table = build_device_table()

    assert table["low_R_flag"].equals(table["r_bin"].eq("low_R"))


def test_power_availability_flags_are_scientifically_distinct() -> None:
    table = build_device_table()

    assert int(table["power_reported_flag"].sum()) == 108
    assert int(table["estimated_power_available_flag"].sum()) == 159
    assert int(table["high_power_flag"].sum()) == 40
    assert table.loc[
        table["high_power_flag"], "estimated_power_available_flag"
    ].all()
    threshold = table["estimated_power_density_uW_cm2"].quantile(
        HIGH_POWER_QUANTILE
    )
    assert threshold == pytest.approx(3.640625)


def test_rh_percent_is_included_as_numeric_data() -> None:
    table = build_device_table()

    assert "rh_percent" in table.columns
    assert table["rh_percent"].notna().sum() == 126


def test_r_centered_outputs_can_be_written(tmp_path: Path) -> None:
    table = build_device_table()
    paths = write_r_centered_outputs(
        table,
        processed_directory=tmp_path / "processed",
        results_directory=tmp_path / "tables",
    )

    assert paths.device_table.is_file()
    assert paths.r_bin_summary.is_file()
    assert paths.power_by_r_bin_summary.is_file()

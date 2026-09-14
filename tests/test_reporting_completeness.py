"""Tests for HydroKG reporting completeness analysis."""

import json
from pathlib import Path

from hydrokg.analysis.reporting import (
    REQUESTED_REPORTING_FIELDS,
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
DIRECT_REPORTING_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "reporting"
    / "hydrokg_direct_reporting_fields_v1.json"
)


def build_reporting_tables():
    device_table = load_r_centered_device_table(DEVICE_TABLE_PATH)
    field_completeness = calculate_field_completeness(device_table)
    device_completeness = calculate_device_completeness(device_table)
    material_summary = summarize_completeness_by_material_class(
        device_table,
        device_completeness,
    )
    return (
        device_table,
        field_completeness,
        device_completeness,
        material_summary,
    )


def test_device_completeness_has_159_rows() -> None:
    _, _, device_completeness, _ = build_reporting_tables()

    assert len(device_completeness) == 159


def test_reporting_completeness_score_is_between_zero_and_one() -> None:
    _, _, device_completeness, _ = build_reporting_tables()

    assert device_completeness["reporting_completeness_score"].between(
        0,
        1,
    ).all()


def test_field_completeness_table_is_not_empty() -> None:
    _, field_completeness, _, _ = build_reporting_tables()

    assert not field_completeness.empty


def test_all_reporting_fields_include_rh_percent() -> None:
    _, field_completeness, device_completeness, _ = build_reporting_tables()

    assert tuple(field_completeness["field"]) == REQUESTED_REPORTING_FIELDS
    assert device_completeness["total_field_count"].eq(11).all()
    assert "power_density_uW_cm2" in REQUESTED_REPORTING_FIELDS
    assert "estimated_power_density_uW_cm2" not in REQUESTED_REPORTING_FIELDS
    assert "log_estimated_power_density" not in REQUESTED_REPORTING_FIELDS


def test_reporting_fields_match_direct_source_reporting_configuration() -> None:
    config = json.loads(DIRECT_REPORTING_CONFIG_PATH.read_text(encoding="utf-8"))
    core = next(
        group
        for group in config["groups"]
        if group["group_id"] == "core_source_reporting_fields"
    )

    assert tuple(core["fields"]) == REQUESTED_REPORTING_FIELDS


def test_material_class_summary_is_not_empty() -> None:
    _, _, _, material_summary = build_reporting_tables()

    assert not material_summary.empty


def test_internal_resistance_reported_count_matches_non_missing() -> None:
    device_table, field_completeness, _, _ = build_reporting_tables()
    reported_count = field_completeness.loc[
        field_completeness["field"].eq("internal_resistance_Mohm"),
        "reported_count",
    ].item()

    assert reported_count == device_table[
        "internal_resistance_Mohm"
    ].notna().sum()


def test_source_reported_power_count_is_108() -> None:
    _, field_completeness, _, material_summary = build_reporting_tables()
    reported_count = field_completeness.loc[
        field_completeness["field"].eq("power_density_uW_cm2"),
        "reported_count",
    ].item()

    assert reported_count == 108
    assert not material_summary["power_reported_fraction"].eq(1.0).all()


def test_reporting_outputs_can_be_written(tmp_path: Path) -> None:
    _, field_completeness, device_completeness, material_summary = (
        build_reporting_tables()
    )
    paths = write_reporting_outputs(
        field_completeness,
        material_summary,
        device_completeness,
        tmp_path / "tables",
    )

    assert paths.field_completeness.is_file()
    assert paths.material_class_summary.is_file()
    assert paths.device_completeness.is_file()

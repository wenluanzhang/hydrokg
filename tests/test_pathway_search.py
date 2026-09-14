"""Tests for HydroKG Stage 5D device-context pathway search."""

import json
from pathlib import Path

import pytest

from hydrokg.reasoning.pathway_search import (
    build_pathway_activation_counts,
    build_warning_flag_counts,
    evaluate_condition,
    find_pathway_matches,
    load_device_table,
    load_pathway_rules,
    write_pathway_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEVICE_TABLE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "hydrokg_r_centered_device_table.csv"
)
RULES_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "rules"
    / "hydrokg_pathway_rules_v1.json"
)


def build_pathway_tables():
    device_table = load_device_table(DEVICE_TABLE_PATH)
    rule_set = load_pathway_rules(RULES_PATH)
    matches = find_pathway_matches(device_table, rule_set)
    pathway_counts = build_pathway_activation_counts(
        matches,
        len(device_table),
    )
    warning_counts = build_warning_flag_counts(matches, len(device_table))
    return (
        device_table,
        rule_set,
        matches,
        pathway_counts,
        warning_counts,
    )


def test_rule_matching_output_is_not_empty() -> None:
    _, _, matches, _, _ = build_pathway_tables()

    assert not matches.empty


def test_matched_device_ids_exist_in_device_table() -> None:
    device_table, _, matches, _, _ = build_pathway_tables()

    assert set(matches["device_record_id"]) <= set(
        device_table["device_record_id"]
    )


def test_activated_pathways_exist_in_rule_file() -> None:
    _, rule_set, matches, _, _ = build_pathway_tables()
    rule_pathways = {
        rule["activates_pathway"]
        for rule in rule_set["rules"]
        if rule["activates_pathway"] is not None
    }

    assert set(matches["activated_pathway"].dropna()) <= rule_pathways


def test_warning_only_matches_preserve_empty_activated_pathway() -> None:
    _, _, matches, _, _ = build_pathway_tables()
    warning_matches = matches.loc[matches["rule_type"].eq("warning_only")]

    assert not warning_matches.empty
    assert warning_matches["activated_pathway"].isna().all()


def test_pathway_activation_counts_are_not_empty() -> None:
    _, _, _, pathway_counts, _ = build_pathway_tables()

    assert not pathway_counts.empty


def test_warning_flag_counts_are_not_empty() -> None:
    _, _, _, _, warning_counts = build_pathway_tables()

    assert not warning_counts.empty


def test_missing_r_warning_count_matches_missing_r_devices() -> None:
    device_table, _, _, _, warning_counts = build_pathway_tables()
    expected_count = int(device_table["r_bin"].eq("missing_R").sum())

    assert warning_count(warning_counts, "missing_R_warning") == expected_count


def test_missing_humidity_warning_count_matches_missing_values() -> None:
    device_table, _, _, _, warning_counts = build_pathway_tables()
    expected_count = int(device_table["rh_percent"].isna().sum())

    assert (
        warning_count(warning_counts, "missing_humidity_warning")
        == expected_count
    )


def test_incomplete_reporting_warning_count_matches_reporting_gap_union() -> None:
    device_table, _, _, _, warning_counts = build_pathway_tables()
    expected_count = int(
        (
            device_table["r_bin"].eq("missing_R")
            | device_table["rh_percent"].isna()
        ).sum()
    )

    assert (
        warning_count(warning_counts, "incomplete_reporting_warning")
        == expected_count
    )


def test_pathway_counts_exclude_warning_only_pseudo_pathways() -> None:
    _, _, _, pathway_counts, _ = build_pathway_tables()
    pseudo_pathways = {
        "reporting_gap_pathway",
        "electrochemical_confounding_pathway",
    }

    assert not (set(pathway_counts["activated_pathway"]) & pseudo_pathways)


def test_warning_counts_match_expected_unique_device_counts() -> None:
    _, _, _, _, warning_counts = build_pathway_tables()
    expected = {
        "missing_R_warning": 47,
        "missing_humidity_warning": 33,
        "incomplete_reporting_warning": 65,
        "electrochemical_control_needed_warning": 84,
    }

    assert dict(
        warning_counts.set_index("warning_flag")["match_count"]
    ) == expected


def test_summary_fractions_are_between_zero_and_one() -> None:
    _, _, _, pathway_counts, warning_counts = build_pathway_tables()

    for summary in (pathway_counts, warning_counts):
        assert summary["fraction_of_devices"].between(0, 1).all()


def test_pathway_outputs_can_be_written(tmp_path: Path) -> None:
    _, _, matches, pathway_counts, warning_counts = build_pathway_tables()
    paths = write_pathway_outputs(
        matches,
        pathway_counts,
        warning_counts,
        tmp_path / "tables",
    )

    assert paths.device_pathway_matches.is_file()
    assert paths.pathway_activation_counts.is_file()
    assert paths.warning_flag_counts.is_file()


def test_unsupported_operator_raises_clear_value_error() -> None:
    with pytest.raises(ValueError, match="Unsupported condition operator"):
        evaluate_condition(
            {"structure_class": "porous"},
            {
                "field": "structure_class",
                "operator": "starts_with",
                "value": "por",
            },
        )


def test_json_columns_contain_valid_json_lists() -> None:
    _, _, matches, _, _ = build_pathway_tables()

    for column in (
        "warning_flags_json",
        "design_variables_json",
        "required_reporting_items_json",
    ):
        assert matches[column].map(json.loads).map(
            lambda value: isinstance(value, list)
        ).all()


def warning_count(warning_counts, warning_flag: str) -> int:
    return warning_counts.loc[
        warning_counts["warning_flag"].eq(warning_flag),
        "match_count",
    ].item()

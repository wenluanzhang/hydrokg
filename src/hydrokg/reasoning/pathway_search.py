"""Apply declarative pathway rules to R-centered device records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

DEVICE_PATHWAY_MATCHES_FILENAME = "hydrokg_device_pathway_matches.csv"
PATHWAY_ACTIVATION_COUNTS_FILENAME = (
    "hydrokg_pathway_activation_counts.csv"
)
WARNING_FLAG_COUNTS_FILENAME = "hydrokg_warning_flag_counts.csv"

MATCH_COLUMNS = (
    "device_record_id",
    "paper_doi",
    "material_class",
    "structure_class",
    "r_bin",
    "high_power_flag",
    "rule_id",
    "rule_name",
    "rule_type",
    "activated_pathway",
    "warning_flags_json",
    "design_variables_json",
    "required_reporting_items_json",
    "interpretation_note",
)
PATHWAY_COUNT_COLUMNS = (
    "activated_pathway",
    "match_count",
    "fraction_of_devices",
)
WARNING_COUNT_COLUMNS = (
    "warning_flag",
    "match_count",
    "fraction_of_devices",
)
DEVICE_CONTEXT_COLUMNS = (
    "device_record_id",
    "paper_doi",
    "material_class",
    "structure_class",
    "r_bin",
    "high_power_flag",
)
SUPPORTED_OPERATORS = {"equals", "in", "contains", "is_missing"}
SUPPORTED_MATCH_MODES = {"all", "any"}


@dataclass(frozen=True)
class PathwayOutputPaths:
    """Paths written by :func:`write_pathway_outputs`."""

    device_pathway_matches: Path
    pathway_activation_counts: Path
    warning_flag_counts: Path


def load_device_table(path: Path | str) -> pd.DataFrame:
    """Load the processed R-centered device table."""
    table = pd.read_csv(path)
    _require_columns(table, DEVICE_CONTEXT_COLUMNS, "R-centered device table")
    return table


def load_pathway_rules(path: Path | str) -> dict[str, Any]:
    """Load a declarative pathway rule set from JSON."""
    with Path(path).open(encoding="utf-8") as handle:
        rule_set = json.load(handle)
    if not isinstance(rule_set, dict) or not isinstance(
        rule_set.get("rules"), list
    ):
        raise ValueError("Pathway rule file must contain a 'rules' list")
    return rule_set


def evaluate_condition(
    record: Mapping[str, Any],
    condition: Mapping[str, Any],
) -> bool:
    """Evaluate one supported condition against a device record."""
    operator = condition.get("operator")
    if operator not in SUPPORTED_OPERATORS:
        raise ValueError(f"Unsupported condition operator: {operator!r}")

    field = condition.get("field")
    if field not in record:
        raise ValueError(f"Condition field is missing from device table: {field}")

    actual = record[field]
    expected = condition.get("value")
    if operator == "is_missing":
        return _is_missing(actual)
    if _is_missing(actual):
        return False
    if operator == "equals":
        return bool(actual == expected)
    if operator == "in":
        if not isinstance(expected, (list, tuple, set, frozenset)):
            raise ValueError("Condition operator 'in' requires a list value")
        return actual in expected
    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        try:
            return expected in actual
        except TypeError:
            return False
    raise AssertionError("Supported operator was not evaluated")


def rule_matches(
    record: Mapping[str, Any],
    rule: Mapping[str, Any],
) -> bool:
    """Return whether a device record satisfies a pathway rule."""
    conditions = rule.get("conditions", {})
    match_mode = conditions.get("match")
    if match_mode not in SUPPORTED_MATCH_MODES:
        raise ValueError(f"Unsupported rule match mode: {match_mode!r}")

    clauses = conditions.get("clauses")
    if not isinstance(clauses, list) or not clauses:
        raise ValueError("Rule conditions must contain a non-empty clauses list")
    evaluations = [
        evaluate_condition(record, condition) for condition in clauses
    ]
    return all(evaluations) if match_mode == "all" else any(evaluations)


def find_pathway_matches(
    device_table: pd.DataFrame,
    rule_set: Mapping[str, Any],
) -> pd.DataFrame:
    """Return one row for every matched device-rule pair."""
    _require_columns(
        device_table,
        DEVICE_CONTEXT_COLUMNS,
        "R-centered device table",
    )
    rules = rule_set.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Pathway rule set must contain a 'rules' list")
    _validate_rule_fields(device_table, rules)

    matches: list[dict[str, Any]] = []
    for record in device_table.to_dict(orient="records"):
        for rule in rules:
            if not rule_matches(record, rule):
                continue
            matches.append(
                {
                    **{
                        column: record[column]
                        for column in DEVICE_CONTEXT_COLUMNS
                    },
                    "rule_id": rule.get("rule_id"),
                    "rule_name": rule.get("rule_name"),
                    "rule_type": rule.get("rule_type"),
                    "activated_pathway": rule.get("activates_pathway"),
                    "warning_flags_json": _to_json(
                        rule.get("warning_flags", [])
                    ),
                    "design_variables_json": _to_json(
                        rule.get("design_variables", [])
                    ),
                    "required_reporting_items_json": _to_json(
                        rule.get("required_reporting_items", [])
                    ),
                    "interpretation_note": rule.get("interpretation_note"),
                }
            )
    return pd.DataFrame(matches, columns=MATCH_COLUMNS)


def build_pathway_activation_counts(
    matches: pd.DataFrame,
    device_count: int,
) -> pd.DataFrame:
    """Count matched devices for each non-empty activated pathway."""
    _validate_device_count(device_count)
    _require_columns(
        matches,
        ("device_record_id", "activated_pathway"),
        "Pathway matches",
    )
    activated = matches.loc[
        matches["activated_pathway"].notna()
        & matches["activated_pathway"].astype(str).str.strip().ne("")
    ]
    counts = (
        activated.groupby("activated_pathway", sort=True)[
            "device_record_id"
        ]
        .nunique()
        .rename("match_count")
        .reset_index()
    )
    counts["fraction_of_devices"] = counts["match_count"] / device_count
    return counts.loc[:, PATHWAY_COUNT_COLUMNS]


def build_warning_flag_counts(
    matches: pd.DataFrame,
    device_count: int,
) -> pd.DataFrame:
    """Count matched devices for each warning flag."""
    _validate_device_count(device_count)
    _require_columns(
        matches,
        ("device_record_id", "warning_flags_json"),
        "Pathway matches",
    )
    warning_rows: list[dict[str, str]] = []
    for match in matches.loc[
        :, ("device_record_id", "warning_flags_json")
    ].to_dict(orient="records"):
        for warning_flag in json.loads(match["warning_flags_json"]):
            warning_rows.append(
                {
                    "device_record_id": match["device_record_id"],
                    "warning_flag": warning_flag,
                }
            )

    warnings = pd.DataFrame(
        warning_rows,
        columns=("device_record_id", "warning_flag"),
    )
    counts = (
        warnings.groupby("warning_flag", sort=True)["device_record_id"]
        .nunique()
        .rename("match_count")
        .reset_index()
    )
    counts["fraction_of_devices"] = counts["match_count"] / device_count
    return counts.loc[:, WARNING_COUNT_COLUMNS]


def write_pathway_outputs(
    matches: pd.DataFrame,
    pathway_counts: pd.DataFrame,
    warning_counts: pd.DataFrame,
    output_directory: Path | str,
) -> PathwayOutputPaths:
    """Write pathway matches and both summary tables."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = PathwayOutputPaths(
        device_pathway_matches=(
            output_directory / DEVICE_PATHWAY_MATCHES_FILENAME
        ),
        pathway_activation_counts=(
            output_directory / PATHWAY_ACTIVATION_COUNTS_FILENAME
        ),
        warning_flag_counts=(
            output_directory / WARNING_FLAG_COUNTS_FILENAME
        ),
    )
    matches.loc[:, MATCH_COLUMNS].to_csv(
        paths.device_pathway_matches,
        index=False,
    )
    pathway_counts.loc[:, PATHWAY_COUNT_COLUMNS].to_csv(
        paths.pathway_activation_counts,
        index=False,
    )
    warning_counts.loc[:, WARNING_COUNT_COLUMNS].to_csv(
        paths.warning_flag_counts,
        index=False,
    )
    return paths


def _is_missing(value: Any) -> bool:
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _validate_rule_fields(
    device_table: pd.DataFrame,
    rules: list[dict[str, Any]],
) -> None:
    for rule in rules:
        conditions = rule.get("conditions", {})
        for condition in conditions.get("clauses", []):
            operator = condition.get("operator")
            if operator not in SUPPORTED_OPERATORS:
                raise ValueError(
                    f"Unsupported condition operator: {operator!r}"
                )
            field = condition.get("field")
            if field not in device_table.columns:
                raise ValueError(
                    f"Condition field is missing from device table: {field}"
                )


def _validate_device_count(device_count: int) -> None:
    if device_count <= 0:
        raise ValueError("device_count must be greater than zero")


def _require_columns(
    table: pd.DataFrame,
    required_columns: tuple[str, ...],
    table_name: str,
) -> None:
    missing_columns = sorted(set(required_columns) - set(table.columns))
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"{table_name} is missing required columns: {missing}")

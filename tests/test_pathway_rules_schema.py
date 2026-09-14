"""Tests for the HydroKG pathway-rule schema design."""

import csv
import json
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "rules"
    / "hydrokg_pathway_rules_v1.json"
)
SEMANTIC_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "schema"
    / "hydrokg_semantic_layer_v1.json"
)
DEVICE_TABLE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "hydrokg_r_centered_device_table.csv"
)

REQUIRED_TOP_LEVEL_KEYS = {
    "rule_set_name",
    "rule_set_version",
    "status",
    "description",
    "source_tables",
    "rules",
}
REQUIRED_RULE_FIELDS = {
    "rule_id",
    "rule_name",
    "rule_type",
    "description",
    "conditions",
    "activates_pathway",
    "warning_flags",
    "design_variables",
    "required_reporting_items",
    "interpretation_note",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_device_table_columns() -> set[str]:
    with DEVICE_TABLE_PATH.open(encoding="utf-8", newline="") as handle:
        return set(next(csv.reader(handle)))


def semantic_concepts(concept_type: str) -> set[str]:
    schema = load_json(SEMANTIC_SCHEMA_PATH)
    return set(schema["concept_types"][concept_type]["concepts"])


def test_pathway_rules_load_as_json() -> None:
    rules = load_json(RULES_PATH)

    assert isinstance(rules, dict)


def test_required_top_level_keys_exist() -> None:
    rules = load_json(RULES_PATH)

    assert REQUIRED_TOP_LEVEL_KEYS <= rules.keys()


def test_every_rule_has_required_fields() -> None:
    rules = load_json(RULES_PATH)["rules"]

    assert rules
    for rule in rules:
        assert REQUIRED_RULE_FIELDS <= rule.keys(), rule.get("rule_id")


def test_physical_rules_activate_semantic_pathways() -> None:
    pathways = semantic_concepts("Pathway")

    for rule in load_json(RULES_PATH)["rules"]:
        if rule["rule_type"] == "descriptive_pathway":
            assert rule["activates_pathway"] in pathways, rule["rule_id"]


def test_warning_only_rules_do_not_activate_pathways() -> None:
    rules = load_json(RULES_PATH)["rules"]
    warning_rules = [
        rule for rule in rules if rule["rule_type"] == "warning_only"
    ]

    assert warning_rules
    for rule in warning_rules:
        assert rule["activates_pathway"] is None, rule["rule_id"]


def test_warning_flags_exist_in_semantic_layer() -> None:
    warning_flags = semantic_concepts("WarningFlag")

    for rule in load_json(RULES_PATH)["rules"]:
        assert set(rule["warning_flags"]) <= warning_flags, rule["rule_id"]


def test_design_variables_exist_in_semantic_layer() -> None:
    design_variables = semantic_concepts("DesignVariable")

    for rule in load_json(RULES_PATH)["rules"]:
        assert set(rule["design_variables"]) <= design_variables, rule["rule_id"]


def test_reporting_items_exist_in_semantic_layer() -> None:
    reporting_items = semantic_concepts("ReportingItem")

    for rule in load_json(RULES_PATH)["rules"]:
        assert (
            set(rule["required_reporting_items"]) <= reporting_items
        ), rule["rule_id"]


def test_condition_fields_exist_in_r_centered_device_table() -> None:
    device_columns = load_device_table_columns()

    for rule in load_json(RULES_PATH)["rules"]:
        for clause in rule["conditions"]["clauses"]:
            assert clause["field"] in device_columns, rule["rule_id"]


def test_rule_ids_are_unique() -> None:
    rules = load_json(RULES_PATH)["rules"]
    rule_ids = [rule["rule_id"] for rule in rules]

    assert len(rule_ids) == len(set(rule_ids))

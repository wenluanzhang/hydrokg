"""Tests for the HydroKG device-rule evidence-provenance ledger."""

import json
from pathlib import Path

from hydrokg.reasoning.evidence_provenance import (
    build_evidence_provenance,
    load_csv,
    load_json,
    write_evidence_provenance,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "raw"
    / "hydrovoltaic_ml_curated_159_seed.csv"
)
DEVICE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "hydrokg_r_centered_device_table.csv"
)
MATCHES_PATH = (
    REPOSITORY_ROOT
    / "results"
    / "tables"
    / "hydrokg_device_pathway_matches.csv"
)
RULES_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "rules"
    / "hydrokg_pathway_rules_v1.json"
)
REPORTING_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "reporting"
    / "hydrokg_reporting_fields_v1.json"
)
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "evidence"
    / "hydrokg_evidence_schema_v1.json"
)


def build_evidence_tables():
    matches = load_csv(MATCHES_PATH)
    evidence = build_evidence_provenance(
        matches=matches,
        seed_table=load_csv(SEED_PATH),
        device_table=load_csv(DEVICE_PATH),
        rule_set=load_json(RULES_PATH),
        reporting_metadata=load_json(REPORTING_PATH),
        evidence_schema=load_json(SCHEMA_PATH),
    )
    return matches, evidence


def test_evidence_ledger_has_exactly_245_rows() -> None:
    _, evidence = build_evidence_tables()

    assert len(evidence) == 245


def test_evidence_ids_are_unique_and_deterministic() -> None:
    _, first = build_evidence_tables()
    _, second = build_evidence_tables()

    assert first["evidence_record_id"].is_unique
    assert first["evidence_record_id"].equals(
        second["evidence_record_id"]
    )
    for column in (
        "warning_flags_json",
        "matched_context_json",
        "source_fields_json",
        "source_values_json",
        "source_provenance_categories_json",
        "context_evidence_types_json",
    ):
        assert first[column].equals(second[column])


def test_every_device_rule_match_appears_once() -> None:
    matches, evidence = build_evidence_tables()
    match_pairs = list(
        matches.loc[:, ["device_record_id", "rule_id"]].itertuples(
            index=False,
            name=None,
        )
    )
    evidence_pairs = list(
        evidence.loc[:, ["device_record_id", "rule_id"]].itertuples(
            index=False,
            name=None,
        )
    )

    assert len(evidence_pairs) == len(set(evidence_pairs))
    assert sorted(evidence_pairs) == sorted(match_pairs)


def test_physical_pathways_use_physics_informed() -> None:
    _, evidence = build_evidence_tables()
    physical = evidence.loc[
        evidence["rule_type"].eq("descriptive_pathway")
    ]

    assert physical["inference_evidence_type"].eq(
        "physics_informed"
    ).all()
    assert physical["evidence_role"].eq("pathway_inference").all()


def test_missing_reporting_warnings_use_dataset_association() -> None:
    _, evidence = build_evidence_tables()
    missing_rules = {
        "rule_missing_r_reporting_gap_v1",
        "rule_missing_humidity_reporting_gap_v1",
    }
    selected = evidence.loc[evidence["rule_id"].isin(missing_rules)]

    assert selected["inference_evidence_type"].eq(
        "dataset_association"
    ).all()


def test_electrochemical_warning_uses_physics_informed() -> None:
    _, evidence = build_evidence_tables()
    selected = evidence.loc[
        evidence["rule_id"].eq("rule_electrochemical_confounding_v1")
    ]

    assert selected["inference_evidence_type"].eq(
        "physics_informed"
    ).all()


def test_warning_only_rows_have_no_pathway() -> None:
    _, evidence = build_evidence_tables()
    warning_only = evidence.loc[evidence["rule_type"].eq("warning_only")]

    assert warning_only["activated_pathway"].eq("").all()
    assert warning_only["evidence_role"].eq("warning_basis").all()


def test_no_automatic_experimental_validation() -> None:
    _, evidence = build_evidence_tables()
    evidence_types = set(evidence["inference_evidence_type"])
    for value in evidence["context_evidence_types_json"]:
        evidence_types.update(json.loads(value))

    assert evidence["validation_status"].eq("not_assessed").all()
    assert evidence["manual_review_required"].all()
    assert "experimentally_validated" not in evidence_types
    assert "expert_hypothesis" not in evidence_types


def test_missing_context_is_serialized_explicitly() -> None:
    _, evidence = build_evidence_tables()
    missing_humidity = evidence.loc[
        evidence["rule_id"].eq(
            "rule_missing_humidity_reporting_gap_v1"
        )
    ]

    assert missing_humidity["source_values_json"].map(
        lambda value: json.loads(value)["rh_percent"] == "<missing>"
    ).all()


def test_evidence_output_can_be_written(tmp_path: Path) -> None:
    _, evidence = build_evidence_tables()
    path = write_evidence_provenance(evidence, tmp_path / "tables")

    assert path.evidence.is_file()

"""Build a non-scoring evidence-provenance ledger for rule matches."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

EVIDENCE_FILENAME = "hydrokg_device_rule_evidence.csv"
EXPECTED_MATCH_COUNT = 245
MISSING_VALUE = "<missing>"

EVIDENCE_COLUMNS = (
    "evidence_record_id",
    "device_record_id",
    "paper_doi",
    "rule_id",
    "rule_type",
    "activated_pathway",
    "warning_flags_json",
    "matched_context_json",
    "source_fields_json",
    "source_values_json",
    "source_provenance_categories_json",
    "context_evidence_types_json",
    "inference_evidence_type",
    "evidence_role",
    "validation_status",
    "manual_review_required",
    "evidence_note",
    "limitation_note",
)
MATCH_COLUMNS = (
    "device_record_id",
    "paper_doi",
    "rule_id",
    "rule_type",
    "activated_pathway",
    "warning_flags_json",
)
DEVICE_COLUMNS = (
    "device_record_id",
    "paper_doi",
)
ALLOWED_CONTEXT_EVIDENCE_TYPES = {
    "dataset_association",
    "literature_reported",
}
FORBIDDEN_AUTOMATIC_EVIDENCE_TYPES = {
    "expert_hypothesis",
    "experimentally_validated",
}


@dataclass(frozen=True)
class EvidenceOutputPath:
    """Path written by :func:`write_evidence_provenance`."""

    evidence: Path


def load_csv(path: Path | str) -> pd.DataFrame:
    """Load a CSV input table."""
    return pd.read_csv(path)


def load_json(path: Path | str) -> dict[str, Any]:
    """Load a JSON configuration file."""
    with Path(path).open(encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("JSON configuration must contain an object")
    return document


def attach_seed_rows(
    seed_table: pd.DataFrame,
    device_table: pd.DataFrame,
) -> pd.DataFrame:
    """Attach deterministic device IDs to row-aligned seed records."""
    _require_columns(seed_table, ("paper_doi",), "seed table")
    _require_columns(device_table, DEVICE_COLUMNS, "device table")
    if len(seed_table) != len(device_table):
        raise ValueError("Seed and device tables must contain the same rows")

    seed_dois = seed_table["paper_doi"].fillna("").astype(str)
    device_dois = device_table["paper_doi"].fillna("").astype(str)
    if not seed_dois.reset_index(drop=True).equals(
        device_dois.reset_index(drop=True)
    ):
        raise ValueError("Seed and device tables are not row-aligned by DOI")

    attached = seed_table.copy()
    attached.insert(
        0,
        "device_record_id",
        device_table["device_record_id"].to_numpy(),
    )
    return attached


def build_evidence_provenance(
    matches: pd.DataFrame,
    seed_table: pd.DataFrame,
    device_table: pd.DataFrame,
    rule_set: dict[str, Any],
    reporting_metadata: dict[str, Any],
    evidence_schema: dict[str, Any],
) -> pd.DataFrame:
    """Build exactly one evidence row for every device-rule match."""
    _require_columns(matches, MATCH_COLUMNS, "device-rule matches")
    _require_columns(device_table, DEVICE_COLUMNS, "device table")
    if len(matches) != EXPECTED_MATCH_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_MATCH_COUNT} device-rule matches; "
            f"found {len(matches)}"
        )

    seed_by_device = attach_seed_rows(seed_table, device_table).set_index(
        "device_record_id"
    )
    device_by_id = device_table.set_index("device_record_id")
    if not seed_by_device.index.is_unique:
        raise ValueError("Seed device IDs must be unique")
    if not device_by_id.index.is_unique:
        raise ValueError("Processed device IDs must be unique")
    rules = _rules_by_id(rule_set)
    provenance = _field_provenance_map(
        reporting_metadata,
        evidence_schema,
    )
    context_mapping = evidence_schema["context_evidence_mapping"]

    rows = []
    for match in matches.to_dict(orient="records"):
        device_id = match["device_record_id"]
        rule_id = match["rule_id"]
        rule = rules[rule_id]
        condition_fields = [
            clause["field"] for clause in rule["conditions"]["clauses"]
        ]
        source_values = {}
        matched_context = []
        source_categories = []
        context_evidence_types = []

        for clause in rule["conditions"]["clauses"]:
            field = clause["field"]
            category = provenance[field]
            value, source_kind = _source_value(
                field,
                device_id,
                seed_by_device,
                device_by_id,
                category,
            )
            serialized_value = _json_value(value)
            evidence_type = context_mapping[category]
            source_values[field] = serialized_value
            source_categories.append(category)
            context_evidence_types.append(evidence_type)
            matched_context.append(
                {
                    "field": field,
                    "operator": clause["operator"],
                    "expected": _json_value(clause.get("value")),
                    "actual": serialized_value,
                    "source_kind": source_kind,
                }
            )

        inference_type = _inference_evidence_type(
            rule,
            evidence_schema,
        )
        role = (
            "pathway_inference"
            if rule["rule_type"] == "descriptive_pathway"
            else "warning_basis"
        )
        activated_pathway = rule.get("activates_pathway") or ""
        if rule["rule_type"] == "warning_only":
            activated_pathway = ""

        rows.append(
            {
                "evidence_record_id": _evidence_id(device_id, rule_id),
                "device_record_id": device_id,
                "paper_doi": match["paper_doi"],
                "rule_id": rule_id,
                "rule_type": rule["rule_type"],
                "activated_pathway": activated_pathway,
                "warning_flags_json": _canonical_json(
                    rule.get("warning_flags", [])
                ),
                "matched_context_json": _canonical_json(matched_context),
                "source_fields_json": _canonical_json(condition_fields),
                "source_values_json": _canonical_json(source_values),
                "source_provenance_categories_json": _canonical_json(
                    source_categories
                ),
                "context_evidence_types_json": _canonical_json(
                    context_evidence_types
                ),
                "inference_evidence_type": inference_type,
                "evidence_role": role,
                "validation_status": "not_assessed",
                "manual_review_required": True,
                "evidence_note": _evidence_note(rule, inference_type),
                "limitation_note": _limitation_note(rule),
            }
        )

    evidence = pd.DataFrame(rows, columns=EVIDENCE_COLUMNS)
    _validate_evidence_output(evidence)
    return evidence


def write_evidence_provenance(
    evidence: pd.DataFrame,
    output_directory: Path | str,
) -> EvidenceOutputPath:
    """Write the device-rule evidence ledger."""
    _require_columns(evidence, EVIDENCE_COLUMNS, "evidence ledger")
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    path = EvidenceOutputPath(
        evidence=output_directory / EVIDENCE_FILENAME
    )
    evidence.loc[:, EVIDENCE_COLUMNS].to_csv(path.evidence, index=False)
    return path


def _rules_by_id(rule_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules = rule_set.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Rule set must contain a rules list")
    indexed = {rule["rule_id"]: rule for rule in rules}
    if len(indexed) != len(rules):
        raise ValueError("Rule IDs must be unique")
    return indexed


def _field_provenance_map(
    reporting_metadata: dict[str, Any],
    evidence_schema: dict[str, Any],
) -> dict[str, str]:
    configured = {
        definition["field"]: definition["provenance_category"]
        for definition in reporting_metadata["fields"]
    }
    configured.update(
        evidence_schema["unconfigured_condition_field_provenance"]
    )
    return configured


def _source_value(
    field: str,
    device_id: str,
    seed_by_device: pd.DataFrame,
    device_by_id: pd.DataFrame,
    provenance_category: str,
) -> tuple[Any, str]:
    if field in device_by_id.columns:
        value = device_by_id.at[device_id, field]
        if provenance_category in {"analyst_derived", "derived_numeric"}:
            return value, "derived_field"
        if field in seed_by_device.columns:
            return value, "seed_field"
        return value, "derived_field"
    if field in seed_by_device.columns:
        return seed_by_device.at[device_id, field], "seed_field"
    raise ValueError(f"Rule condition field is unavailable: {field}")


def _inference_evidence_type(
    rule: dict[str, Any],
    evidence_schema: dict[str, Any],
) -> str:
    mapping = evidence_schema["inference_evidence_mapping"]
    if rule["rule_type"] == "descriptive_pathway":
        return mapping["descriptive_pathway"]
    return mapping[rule["rule_id"]]


def _evidence_id(device_id: str, rule_id: str) -> str:
    digest = hashlib.sha256(
        f"{device_id}|{rule_id}".encode("utf-8")
    ).hexdigest()[:20]
    return f"evidence_{digest}"


def _json_value(value: Any) -> Any:
    if _is_missing(value):
        return MISSING_VALUE
    if isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        return value
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _is_missing(value: Any) -> bool:
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _evidence_note(
    rule: dict[str, Any],
    inference_type: str,
) -> str:
    if rule["rule_type"] == "descriptive_pathway":
        return (
            "Matched device context supports a physics-informed pathway "
            "inference; no causal or experimental validation is assigned."
        )
    if inference_type == "dataset_association":
        return (
            "Matched missing-data context supports a reporting warning "
            "as a dataset association."
        )
    return (
        "Matched electrode or redox context supports a physics-informed "
        "need for electrochemical controls, not demonstrated confounding."
    )


def _limitation_note(rule: dict[str, Any]) -> str:
    return (
        f"{rule['interpretation_note']} Evidence strength is not scored, "
        "validation is not assessed, and manual review is required."
    )


def _validate_evidence_output(evidence: pd.DataFrame) -> None:
    if len(evidence) != EXPECTED_MATCH_COUNT:
        raise ValueError("Evidence ledger row count changed unexpectedly")
    if not evidence["evidence_record_id"].is_unique:
        raise ValueError("Evidence record IDs must be unique")
    if evidence.loc[
        evidence["rule_type"].eq("warning_only"),
        "activated_pathway",
    ].astype(str).str.strip().ne("").any():
        raise ValueError("Warning-only evidence cannot activate a pathway")
    used_types = set(evidence["inference_evidence_type"])
    for value in evidence["context_evidence_types_json"]:
        used_types.update(json.loads(value))
    if used_types & FORBIDDEN_AUTOMATIC_EVIDENCE_TYPES:
        raise ValueError("Automatic validation evidence types are forbidden")
    if not used_types <= (
        ALLOWED_CONTEXT_EVIDENCE_TYPES | {"physics_informed"}
    ):
        raise ValueError("Unexpected evidence type in generated ledger")


def _require_columns(
    table: pd.DataFrame,
    required_columns: tuple[str, ...],
    table_name: str,
) -> None:
    missing = sorted(set(required_columns) - set(table.columns))
    if missing:
        raise ValueError(
            f"{table_name} is missing required columns: {', '.join(missing)}"
        )

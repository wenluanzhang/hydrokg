"""Build the HydroKG device-rule evidence-provenance ledger."""

from __future__ import annotations

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
REPORTING_METADATA_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "reporting"
    / "hydrokg_reporting_fields_v1.json"
)
EVIDENCE_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "evidence"
    / "hydrokg_evidence_schema_v1.json"
)
RESULTS_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"


def main() -> int:
    """Build and write the evidence-provenance ledger."""
    evidence = build_evidence_provenance(
        matches=load_csv(MATCHES_PATH),
        seed_table=load_csv(SEED_PATH),
        device_table=load_csv(DEVICE_PATH),
        rule_set=load_json(RULES_PATH),
        reporting_metadata=load_json(REPORTING_METADATA_PATH),
        evidence_schema=load_json(EVIDENCE_SCHEMA_PATH),
    )
    path = write_evidence_provenance(evidence, RESULTS_DIRECTORY)

    print(f"Evidence rows: {len(evidence)}")
    print(
        "Unique evidence IDs: "
        f"{evidence['evidence_record_id'].nunique()}"
    )
    print(f"Wrote: {path.evidence.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

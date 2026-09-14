"""Apply declarative pathway rules to HydroKG device contexts."""

from __future__ import annotations

from pathlib import Path

from hydrokg.reasoning.pathway_search import (
    build_pathway_activation_counts,
    build_warning_flag_counts,
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
RESULTS_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"


def main() -> int:
    """Apply pathway rules and write match and summary tables."""
    device_table = load_device_table(DEVICE_TABLE_PATH)
    rule_set = load_pathway_rules(RULES_PATH)
    matches = find_pathway_matches(device_table, rule_set)
    pathway_counts = build_pathway_activation_counts(
        matches,
        len(device_table),
    )
    warning_counts = build_warning_flag_counts(matches, len(device_table))
    paths = write_pathway_outputs(
        matches,
        pathway_counts,
        warning_counts,
        RESULTS_DIRECTORY,
    )

    print(f"Devices: {len(device_table)}")
    print(f"Device-rule matches: {len(matches)}")
    for path in (
        paths.device_pathway_matches,
        paths.pathway_activation_counts,
        paths.warning_flag_counts,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

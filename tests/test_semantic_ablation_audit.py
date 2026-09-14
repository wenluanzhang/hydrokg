"""Tests for the semantic-layer ablation audit."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TABLES_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "37_run_semantic_ablation_audit.py"
BASE_NODES_PATH = REPOSITORY_ROOT / "data" / "processed" / "hydrokg_nodes.csv"
BASE_EDGES_PATH = REPOSITORY_ROOT / "data" / "processed" / "hydrokg_edges.csv"
SEMANTIC_NODES_PATH = TABLES_DIRECTORY / "hydrokg_semantic_nodes.csv"
SEMANTIC_EDGES_PATH = TABLES_DIRECTORY / "hydrokg_semantic_edges.csv"
CONFIG_PATH = REPOSITORY_ROOT / "configs" / "queries" / "hydrokg_graph_queries_v1.json"
OUTPUT_PATH = TABLES_DIRECTORY / "hydrokg_semantic_ablation_audit.csv"
SOURCE_PATHS = (
    BASE_NODES_PATH,
    BASE_EDGES_PATH,
    SEMANTIC_NODES_PATH,
    SEMANTIC_EDGES_PATH,
    CONFIG_PATH,
)
EXPECTED_STAGE_NAMES = (
    "base_graph",
    "performance_semantics",
    "pathway_semantics",
    "warning_semantics",
    "design_reporting_semantics",
)
EXPECTED_SUPPORTED_COUNTS = (2, 4, 4, 4, 4)
EXPECTED_CANDIDATE_COUNTS = (10, 6, 6, 6, 6)
EXPECTED_FINAL_DEVICES = (
    "device_record_069",
    "device_record_071",
    "device_record_104",
    "device_record_155",
    "device_record_158",
    "device_record_159",
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "semantic_ablation_audit",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load semantic ablation audit script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_csv(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def file_hash(path: Path) -> str:
    for _ in range(10):
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except PermissionError:
            time.sleep(0.2)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    return {path.name: file_hash(path) for path in paths}


def run_script(tmp_path: Path) -> Any:
    """Run the audit entry point with every generated path redirected.

    ``REPOSITORY_ROOT`` is used by ``main()`` only to render the written
    path, so redirecting it exercises the real CLI path without touching the
    frozen publication tables.
    """

    module = load_module()
    module.OUTPUT_PATH = tmp_path / OUTPUT_PATH.name
    module.REPOSITORY_ROOT = tmp_path
    assert module.main() == 0
    return module


def build_rows():
    module = load_module()
    return module.run_ablation_audit(
        load_csv(BASE_NODES_PATH),
        load_csv(BASE_EDGES_PATH),
        load_csv(SEMANTIC_NODES_PATH),
        load_csv(SEMANTIC_EDGES_PATH),
        json.loads(CONFIG_PATH.read_text(encoding="utf-8")),
    )


def output_rows(tmp_path: Path) -> tuple[dict[str, str], ...]:
    module = run_script(tmp_path)
    return load_csv(module.OUTPUT_PATH)


def test_stage_ordering_is_fixed() -> None:
    rows = build_rows()

    assert tuple(row.stage_name for row in rows) == EXPECTED_STAGE_NAMES
    assert tuple(row.stage_index for row in rows) == (1, 2, 3, 4, 5)


def test_supported_constraint_count_never_decreases() -> None:
    counts = [row.supported_constraint_count for row in build_rows()]

    assert counts == sorted(counts)
    assert tuple(counts) == EXPECTED_SUPPORTED_COUNTS


def test_candidate_count_never_increases() -> None:
    counts = [row.candidate_device_count for row in build_rows()]

    assert tuple(counts) == EXPECTED_CANDIDATE_COUNTS
    assert all(left >= right for left, right in zip(counts, counts[1:]))


def test_final_devices_match_canonical_six_query_results() -> None:
    final = build_rows()[-1]

    assert final.candidate_device_ids == EXPECTED_FINAL_DEVICES
    assert final.supported_constraint_count == 4
    assert final.total_constraint_count == 4


def test_context_fields_appear_only_when_layer_is_available() -> None:
    rows = build_rows()

    for row in rows[:3]:
        assert row.candidate_devices_with_warning_count == 0
        assert row.reachable_warning_flags == ()
        assert row.reachable_design_variables == ()
        assert row.reachable_reporting_items == ()
    assert rows[3].candidate_devices_with_warning_count == 4
    assert rows[3].reachable_warning_flags == (
        "electrochemical_control_needed_warning",
        "incomplete_reporting_warning",
        "missing_humidity_warning",
    )
    assert rows[3].reachable_design_variables == ()
    assert rows[3].reachable_reporting_items == ()
    assert rows[4].reachable_design_variables == (
        "electrode_spacing",
        "electrolyte_concentration",
        "film_thickness",
        "ionic_conductivity",
    )
    assert rows[4].reachable_reporting_items == (
        "device_area",
        "electrode_spacing",
        "electrolyte_concentration",
        "electrolyte_identity",
        "film_thickness",
        "humidity",
        "internal_resistance",
        "power_density",
    )


def test_output_columns_and_json_serialization(tmp_path: Path) -> None:
    rows = output_rows(tmp_path)

    assert len(rows) == 5
    assert tuple(rows[0]) == load_module().OUTPUT_COLUMNS
    for row in rows:
        for column in (
            "added_node_types_json",
            "added_relation_types_json",
            "candidate_device_ids_json",
            "reachable_warning_flags_json",
            "reachable_design_variables_json",
            "reachable_reporting_items_json",
        ):
            assert isinstance(json.loads(row[column]), list)


def test_deterministic_output(tmp_path: Path, capsys: Any) -> None:
    first = run_script(tmp_path / "first")
    first_stdout = capsys.readouterr().out
    first_hash = file_hash(first.OUTPUT_PATH)
    second = run_script(tmp_path / "second")
    second_stdout = capsys.readouterr().out
    second_hash = file_hash(second.OUTPUT_PATH)

    assert first_stdout == second_stdout
    assert first_hash == second_hash


def test_input_files_are_unchanged(tmp_path: Path) -> None:
    before = file_hashes(SOURCE_PATHS)
    run_script(tmp_path)
    after = file_hashes(SOURCE_PATHS)

    assert before == after

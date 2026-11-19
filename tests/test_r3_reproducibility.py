"""Regression checks for the two R3 reproductions."""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from shutil import copyfile

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/reproduce_r3_checks.py"
SPEC = spec_from_file_location("reproduce_r3_checks", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checks = module_from_spec(SPEC)
SPEC.loader.exec_module(checks)

SIX = (
    "device_record_069", "device_record_071", "device_record_104",
    "device_record_155", "device_record_158", "device_record_159",
)
FIVE = (
    "device_record_069", "device_record_071", "device_record_104",
    "device_record_158", "device_record_159",
)
CUTOFFS = {"0.70": "2.7875", "0.75": "3.640625", "0.80": "5.685"}


@pytest.fixture(scope="module")
def flat_seed():
    return checks.load_flat_seed(ROOT)


@pytest.fixture(scope="module")
def outputs():
    return checks.reproduce(ROOT)


def test_frozen_shape_and_original_row_ids(flat_seed):
    with (ROOT / checks.SEED).open(encoding="utf-8-sig", newline="") as handle:
        raw = list(csv.DictReader(handle))
    assert len(raw) == 159
    assert all(len(row) == 52 for row in raw)
    assert flat_seed.shape == (159, 52)
    assert tuple(flat_seed.index) == tuple(
        f"device_record_{i:03d}" for i in range(1, 160)
    )
    assert list(flat_seed["paper_doi"]) == [row["paper_doi"] for row in raw]


def test_full_seed_linear_quantiles(flat_seed):
    with (ROOT / checks.SEED).open(encoding="utf-8-sig", newline="") as handle:
        raw = list(csv.DictReader(handle))
    power = sorted(Decimal(row["estimated_power_density_uW_cm2"]) for row in raw)
    assert len(power) == 159
    assert sum(bool(row["power_density_uW_cm2"]) for row in raw) == 108
    actual = checks.power_cutoffs(flat_seed)
    for quantile, expected in CUTOFFS.items():
        position = (len(power) - 1) * Decimal(quantile)
        lo = int(position)
        linear = power[lo] + (position - lo) * (power[lo + 1] - power[lo])
        assert linear == Decimal(expected)
        assert actual[float(quantile)] == pytest.approx(float(linear), abs=1e-12, rel=0)


def test_all_nine_sensitivity_cells_and_exact_membership(outputs):
    sensitivity, _ = outputs
    expected = [
        (ceiling, quantile, cutoff, FIVE if ceiling == "0.05" else SIX)
        for ceiling in ("0.05", "0.10", "0.20")
        for quantile, cutoff in CUTOFFS.items()
    ]
    assert len(sensitivity) == len(expected)
    for row, (ceiling, quantile, cutoff, ids) in zip(sensitivity, expected):
        assert row["resistance_ceiling_Mohm"] == ceiling
        assert row["power_quantile"] == quantile
        assert row["power_cutoff_uW_cm2"] == cutoff
        assert int(row["matched_count"]) == len(ids)
        assert tuple(json.loads(row["matched_device_ids_json"])) == ids
        assert json.loads(row["added_device_ids_json"]) == []
        removed = ["device_record_155"] if ids == FIVE else []
        assert json.loads(row["removed_device_ids_json"]) == removed


def test_inclusive_resistance_and_power_boundaries(flat_seed):
    assert flat_seed.loc["device_record_069", "internal_resistance_Mohm"] == 0.05
    assert flat_seed.loc["device_record_155", "internal_resistance_Mohm"] == 0.10
    assert flat_seed.loc["device_record_069", "estimated_power_density_uW_cm2"] == 20
    assert checks.flat_stages(flat_seed, 0.05, 20)[-1] == FIVE
    assert checks.flat_stages(flat_seed, 0.10, 20)[-1] == SIX


@pytest.mark.parametrize("column", [
    "internal_resistance_Mohm", "estimated_power_density_uW_cm2",
])
@pytest.mark.parametrize("invalid", ["", "unavailable"])
def test_missing_or_nonnumeric_values_do_not_qualify(column, invalid, monkeypatch):
    raw = pd.read_csv(ROOT / checks.SEED, dtype=str)
    raw.loc[103, column] = invalid
    monkeypatch.setattr(checks, "load_seed_csv", lambda _: raw)
    seed = checks.load_flat_seed(ROOT)
    assert pd.isna(seed.loc["device_record_104", column])
    assert checks.flat_stages(seed, 0.10, 3.640625)[-1] == tuple(
        device_id for device_id in SIX if device_id != "device_record_104"
    )


def test_flat_and_graph_parity_against_frozen_trace(flat_seed, outputs):
    stages = checks.flat_stages(flat_seed, 0.10, 3.640625)
    with (ROOT / checks.TABLES / "hydrokg_query_execution_trace.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        frozen = tuple(
            tuple(json.loads(row["candidate_device_ids_json"]))
            for row in csv.DictReader(handle)
        )
    assert len(stages) == 4
    assert tuple(map(len, stages)) == (30, 10, 6, 6)
    assert stages == frozen
    assert stages[-1] == SIX
    _, comparison = outputs
    for column in ("flat_table_match", "graph_match"):
        assert tuple(
            row["device_record_id"] for row in comparison if row[column] == "true"
        ) == SIX


def test_trace_rejects_wrong_id_even_if_count_agrees(monkeypatch):
    read_rows = checks.read_rows

    def bad_trace(path):
        rows = read_rows(path)
        if path.name == "hydrokg_query_execution_trace.csv":
            key = "candidate_device_ids_json"
            rows[1][key] = rows[1][key].replace(
                "device_record_052", "device_record_053"
            )
        return rows

    monkeypatch.setattr(checks, "read_rows", bad_trace)
    with pytest.raises(ValueError, match="differs at stage 2"):
        checks.reproduce(ROOT)


def test_humidity_warning_and_actual_graph_witnesses(outputs):
    _, comparison = outputs
    by_id = {row["device_record_id"]: row for row in comparison}
    assert [key for key, row in by_id.items()
            if row["humidity_reporting_follow_up"] == "true"] == ["device_record_104"]
    row = by_id["device_record_104"]
    assert json.loads(row["seed_descriptors_json"])["rh_percent"] is None
    assert "humidity" in json.loads(row["pathway_reporting_items_json"])
    assert row["humidity_requirement_edge_id"] == "semantic_edge_f07741e79dcdb43d"
    assert row["pathway_activation_edge_id"] == "semantic_edge_06842d7147d84f1a"
    assert json.loads(row["warning_provenance_json"])["missing_humidity_warning"] == {
        "edge_id": "semantic_edge_de465f0264a47a4e",
        "rule_id": "rule_missing_humidity_reporting_gap_v1",
    }
    assert "incomplete_reporting_warning" in json.loads(row["warning_provenance_json"])


def test_electrode_control_follow_up_and_rule_provenance(outputs):
    _, comparison = outputs
    hits = {
        row["device_record_id"]: row for row in comparison
        if row["electrode_control_follow_up"] == "true"
    }
    assert set(hits) == {
        "device_record_104", "device_record_155",
        "device_record_158", "device_record_159",
    }
    for row in hits.values():
        descriptors = json.loads(row["seed_descriptors_json"])
        assert descriptors["metal_electrode"] == 1
        assert descriptors["auxiliary_redox_present"] == 0
        evidence = json.loads(row["warning_provenance_json"])
        assert (
            evidence["electrochemical_control_needed_warning"]["rule_id"]
            == "rule_electrochemical_confounding_v1"
        )


def test_seed_doi_and_incoming_paper_provenance(flat_seed, outputs):
    _, comparison = outputs
    tables = ROOT / checks.TABLES
    edges = {row["edge_id"]: row for row in
             checks.read_rows(tables / "hydrokg_integrated_edges.csv")}
    nodes = {row["node_id"]: row for row in
             checks.read_rows(tables / "hydrokg_integrated_nodes.csv")}
    assert tuple(row["paper_doi"] for row in comparison) == (
        "10.1039/C9EE00252A", "10.1002/adfm.202308620", "10.1002/adma.202312209",
        "10.1002/advs.202300750", "10.1002/adma.202103897", "10.1039/D3EE00843F",
    )
    for row in comparison:
        doi = row["paper_doi"]
        edge = edges[row["paper_reports_edge_id"]]
        paper = nodes[edge["source_id"]]
        assert edge["edge_type"] == "reports"
        assert edge["target_id"] == row["device_record_id"]
        assert paper["node_type"] == "Paper"
        assert doi == paper["label"] == edge["source_value"]
        assert doi == flat_seed.loc[row["device_record_id"], "paper_doi"]


def test_deterministic_csv_regeneration(tmp_path):
    inputs = (
        checks.SEED,
        Path("configs/queries/hydrokg_graph_queries_v1.json"),
        *(checks.TABLES / filename for filename in (
            "hydrokg_integrated_nodes.csv", "hydrokg_integrated_edges.csv",
            "hydrokg_query_execution_trace.csv", "hydrokg_query_device_matches.csv",
            "hydrokg_query_paths.csv", "hydrokg_query_pathway_requirements.csv",
        )),
    )
    for relative in inputs:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(ROOT / relative, target)
    outputs = [checks.TABLES / name for name in (checks.SENSITIVITY, checks.COMPARISON)]
    checks.main(tmp_path)
    first = [(tmp_path / path).read_bytes() for path in outputs]
    checks.main(tmp_path)
    assert first == [(tmp_path / path).read_bytes() for path in outputs]
    assert first == [(ROOT / path).read_bytes() for path in outputs]
    assert all((ROOT / path).read_bytes() == (tmp_path / path).read_bytes()
               for path in inputs)

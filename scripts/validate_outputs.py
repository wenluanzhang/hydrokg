"""Validate the frozen HydroKG software and data release outputs."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "results" / "tables"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def require(condition: bool, label: str, failures: list[str]) -> None:
    if condition:
        print(f"PASS {label}")
    else:
        failures.append(label)
        print(f"FAIL {label}")


def require_rows(
    path: Path, expected: int, label: str, failures: list[str]
) -> list[dict[str, str]]:
    if not path.is_file():
        require(False, f"{label}: missing {path.relative_to(ROOT)}", failures)
        return []
    rows = read_rows(path)
    require(len(rows) == expected, f"{label}: {expected} rows", failures)
    return rows


def endpoints_resolve(
    nodes: list[dict[str, str]], edges: list[dict[str, str]]
) -> bool:
    node_ids = {row["node_id"] for row in nodes}
    return all(
        edge["source_id"] in node_ids and edge["target_id"] in node_ids
        for edge in edges
    )


def nonempty_count(rows: list[dict[str, str]], field: str) -> int:
    return sum(row.get(field, "").strip().lower() not in {"", "na", "nan"} for row in rows)


def main() -> int:
    failures: list[str] = []

    seed_path = ROOT / "data" / "raw" / "hydrovoltaic_ml_curated_159_seed.csv"
    seed = require_rows(seed_path, 159, "curated dataset", failures)
    if seed:
        require(len(seed[0]) == 52, "curated dataset: 52 fields", failures)
        require(nonempty_count(seed, "power_density_uW_cm2") == 108,
                "source-reported power density: 108/159", failures)
        require(nonempty_count(seed, "internal_resistance_Mohm") == 112,
                "internal resistance: 112/159", failures)
        require(nonempty_count(seed, "rh_percent") == 126,
                "relative humidity: 126/159", failures)

    base_nodes = require_rows(
        ROOT / "data" / "processed" / "hydrokg_nodes.csv",
        581,
        "base graph nodes",
        failures,
    )
    base_edges = require_rows(
        ROOT / "data" / "processed" / "hydrokg_edges.csv",
        1777,
        "base graph edges",
        failures,
    )
    if base_nodes and base_edges:
        require(endpoints_resolve(base_nodes, base_edges),
                "base graph endpoints resolve", failures)

    integrated_nodes = require_rows(
        TABLES / "hydrokg_integrated_nodes.csv",
        614,
        "integrated nodes",
        failures,
    )
    integrated_edges = require_rows(
        TABLES / "hydrokg_integrated_edges.csv",
        2447,
        "integrated links",
        failures,
    )
    if integrated_nodes and integrated_edges:
        require(endpoints_resolve(integrated_nodes, integrated_edges),
                "integrated graph endpoints resolve", failures)

    routes = require_rows(
        TABLES / "hydrokg_query_low_r_route_summary.csv",
        13,
        "low-R material/structure routes",
        failures,
    )
    if routes:
        low_r_ids = {
            device_id
            for row in routes
            for device_id in json.loads(row["device_ids_json"])
        }
        require(len(low_r_ids) == 55, "low-R query: 55 records", failures)
        expected_routes = {
            ("biomass", "porous"): (16, 7),
            ("carbon", "porous"): (12, 3),
            ("polymer", "film"): (6, 6),
        }
        actual_routes = {
            (row["material_class"], row["structure_class"]): (
                int(row["matched_device_count"]),
                int(row["high_power_device_count"]),
            )
            for row in routes
        }
        require(all(actual_routes.get(key) == value for key, value in expected_routes.items()),
                "low-R representative route counts", failures)

    nacl = require_rows(
        TABLES / "hydrokg_query_nacl_primary_na_device_matches.csv",
        20,
        "NaCl/Na+ query records",
        failures,
    )
    device_rows = read_rows(
        ROOT / "data" / "processed" / "hydrokg_r_centered_device_table.csv"
    )
    if nacl and device_rows:
        contexts = {
            row["device_record_id"]: (row["material_class"], row["structure_class"])
            for row in device_rows
        }
        matched_contexts = [contexts[row["device_record_id"]] for row in nacl]
        require(len({item[0] for item in matched_contexts}) == 7,
                "NaCl/Na+ query: 7 material classes", failures)
        require(len({item[1] for item in matched_contexts}) == 2,
                "NaCl/Na+ query: 2 structure classes", failures)

    matches = require_rows(
        TABLES / "hydrokg_query_device_matches.csv",
        6,
        "four-criterion query records",
        failures,
    )
    expected_ids = [
        "device_record_069",
        "device_record_071",
        "device_record_104",
        "device_record_155",
        "device_record_158",
        "device_record_159",
    ]
    if matches:
        require([row["device_record_id"] for row in matches] == expected_ids,
                "four-criterion query membership", failures)
    trace = read_rows(TABLES / "hydrokg_query_execution_trace.csv")
    require([int(row["candidate_device_count"]) for row in trace] == [30, 10, 6, 6],
            "four-criterion query progression: 30 -> 10 -> 6 -> 6", failures)

    if failures:
        print("\nHydroKG release validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nHydroKG v1.0.0 software/data release validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

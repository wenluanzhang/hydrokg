"""Reproduce the R3 threshold and canonical selection checks."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from math import isclose
from pathlib import Path

import pandas as pd

from hydrokg.analysis.r_centered import create_device_record_ids, load_seed_csv
from hydrokg.query.graph_query import (
    IntegratedGraph,
    load_graph_query_config,
    load_integrated_graph,
    run_graph_query,
    run_pathway_requirement_query,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = Path("data/raw/hydrovoltaic_ml_curated_159_seed.csv")
TABLES = Path("results/tables")
SENSITIVITY = "hydrokg_threshold_sensitivity.csv"
COMPARISON = "hydrokg_flat_table_graph_comparison.csv"

RESISTANCE = "internal_resistance_Mohm"
POWER = "estimated_power_density_uW_cm2"
CEILINGS = (0.05, 0.10, 0.20)
QUANTILES = (0.70, 0.75, 0.80)
CANONICAL_IDS = tuple(
    f"device_record_{suffix}" for suffix in ("069", "071", "104", "155", "158", "159")
)
TRACE_COUNTS = (30, 10, 6, 6)
CANONICAL_QUERY = "canonical_polymer_film_low_r_high_power"
PATHWAY_QUERY = "pathway_design_and_reporting_requirements"
FILM_PATHWAY = "film_based_ion_concentration_gradient_pathway"
HUMIDITY_WARNING = "missing_humidity_warning"
ELECTRODE_WARNING = "electrochemical_control_needed_warning"
DESCRIPTORS = (
    "material_class", "structure_class", "device_structure", "primary_mobile_ion",
    "inorganic_electrolyte_type", "top_electrode", "bottom_electrode", "rh_percent",
    "metal_electrode", "auxiliary_redox_present",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_rows(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return tuple(csv.DictReader(handle))


def as_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load_flat_seed(root: Path) -> pd.DataFrame:
    seed = load_seed_csv(root / SEED)
    require(seed.shape == (159, 52), "Expected the frozen 159-by-52 seed.")
    seed.index = pd.Index(create_device_record_ids(len(seed)), name="device_record_id")
    for column in (RESISTANCE, POWER):
        seed[column] = pd.to_numeric(seed[column], errors="coerce")
    return seed


def power_cutoffs(seed: pd.DataFrame) -> dict[float, float]:
    return seed[POWER].quantile(list(QUANTILES), interpolation="linear").to_dict()


def flat_stages(
    seed: pd.DataFrame, ceiling: float, cutoff: float
) -> tuple[tuple[str, ...], ...]:
    """Apply the four criteria to seed columns in their reported order."""
    material = seed["material_class"].eq("polymer")
    structure = material & seed["structure_class"].eq("film")
    resistance = structure & seed[RESISTANCE].le(ceiling)
    power = resistance & seed[POWER].ge(cutoff)
    return tuple(
        tuple(seed.index[mask.fillna(False)])
        for mask in (material, structure, resistance, power)
    )


def sensitivity_rows(
    seed: pd.DataFrame, cutoffs: dict[float, float], canonical_ids: tuple[str, ...]
) -> tuple[dict[str, str], ...]:
    rows = []
    canonical = set(canonical_ids)
    for ceiling in CEILINGS:
        for quantile, cutoff in cutoffs.items():
            ids = flat_stages(seed, ceiling, cutoff)[-1]
            added = sorted(set(ids) - canonical)
            removed = sorted(canonical - set(ids))
            expected_removed = ["device_record_155"] if ceiling == 0.05 else []
            require(
                not added and removed == expected_removed,
                f"R1 sensitivity mismatch at R={ceiling}, Q={quantile}: {ids}",
            )
            rows.append({
                "resistance_ceiling_Mohm": f"{ceiling:.2f}",
                "power_quantile": f"{quantile:.2f}",
                "power_cutoff_uW_cm2": format(cutoff, ".12g"),
                "matched_count": str(len(ids)),
                "matched_device_ids_json": as_json(ids),
                "added_device_ids_json": as_json(added),
                "removed_device_ids_json": as_json(removed),
            })
    return tuple(rows)


def comparison_rows(
    seed: pd.DataFrame,
    flat_ids: tuple[str, ...],
    graph: IntegratedGraph,
    matches: tuple[dict[str, str], ...],
    pathway: dict[str, str],
) -> tuple[dict[str, str], ...]:
    """Join matched records to stored requirement, warning, and provenance edges."""
    nodes = {row["node_id"]: row for row in graph.nodes}
    pathway_id = next(
        key for key, node in nodes.items()
        if node["node_type"] == "Pathway" and node["label"] == FILM_PATHWAY
    )
    outgoing = defaultdict(list)
    papers = {}
    for edge in graph.edges:
        outgoing[edge["source_id"], edge["edge_type"]].append(edge)
        if edge["edge_type"] == "reports":
            papers[edge["target_id"]] = edge

    reporting_edges = {
        nodes[edge["target_id"]]["label"]: edge
        for edge in outgoing[pathway_id, "pathway_requires_reporting_item"]
    }
    require(
        sorted(reporting_edges) == json.loads(pathway["reporting_items_json"]),
        "Film pathway reporting requirements disagree with stored edges.",
    )

    graph_by_id = {row["device_record_id"]: row for row in matches}
    rows = []
    for device_id in flat_ids:
        match = graph_by_id[device_id]
        source = seed.loc[device_id].to_dict()
        paper = papers[device_id]
        doi = match["paper_doi"]
        require(
            doi == source["paper_doi"] == nodes[paper["source_id"]]["label"]
            == paper["source_value"],
            f"DOI provenance mismatch for {device_id}.",
        )
        activation = next(
            edge for edge in outgoing[device_id, "device_activates_pathway"]
            if edge["target_id"] == pathway_id
        )
        require(
            device_id in json.loads(pathway["device_ids_json"]),
            f"Missing film pathway membership for {device_id}.",
        )
        warnings = {
            nodes[edge["target_id"]]["label"]: {
                "edge_id": edge["edge_id"], "rule_id": edge["source_value"],
            }
            for edge in outgoing[device_id, "device_has_warning_flag"]
        }
        require(
            sorted(warnings) == json.loads(match["warning_flags_json"]),
            f"Warning edge mismatch for {device_id}.",
        )
        humidity_follow_up = (
            "humidity" in reporting_edges and HUMIDITY_WARNING in warnings
        )
        if humidity_follow_up:
            require(pd.isna(source["rh_percent"]), f"RH is present for {device_id}.")
        rows.append({
            "device_record_id": device_id,
            "flat_table_match": "true",
            "graph_match": "true",
            "paper_doi": doi,
            "paper_reports_edge_id": paper["edge_id"],
            RESISTANCE: str(source[RESISTANCE]),
            POWER: str(source[POWER]),
            "seed_descriptors_json": as_json({
                field: None if pd.isna(source[field]) else source[field]
                for field in DESCRIPTORS
            }),
            "pathway": pathway["pathway"],
            "pathway_activation_edge_id": activation["edge_id"],
            "pathway_rule_id": activation["source_value"],
            "pathway_reporting_items_json": pathway["reporting_items_json"],
            "humidity_requirement_edge_id": (
                reporting_edges["humidity"]["edge_id"] if humidity_follow_up else ""
            ),
            "warning_provenance_json": as_json(warnings),
            "humidity_reporting_follow_up": "true" if humidity_follow_up else "false",
            "electrode_control_follow_up": (
                "true" if ELECTRODE_WARNING in warnings else "false"
            ),
        })

    for column, expected in (
        ("humidity_reporting_follow_up", ("device_record_104",)),
        ("electrode_control_follow_up", CANONICAL_IDS[2:]),
    ):
        actual = tuple(row["device_record_id"] for row in rows if row[column] == "true")
        require(actual == expected, f"R1 follow-up mismatch for {column}: {actual}")
    return tuple(rows)


def reproduce(
    root: Path,
) -> tuple[tuple[dict[str, str], ...], tuple[dict[str, str], ...]]:
    seed = load_flat_seed(root)
    cutoffs = power_cutoffs(seed)
    for quantile, expected in zip(QUANTILES, (2.7875, 3.640625, 5.685)):
        require(
            isclose(cutoffs[quantile], expected, rel_tol=0, abs_tol=1e-12),
            f"R1 power cutoff mismatch at Q={quantile}: {cutoffs[quantile]}",
        )
    flat = flat_stages(seed, 0.10, cutoffs[0.75])
    require(flat[-1] == CANONICAL_IDS, f"R1 flat-table membership mismatch: {flat[-1]}")
    sensitivity = sensitivity_rows(seed, cutoffs, flat[-1])

    tables = root / TABLES
    graph = load_integrated_graph(
        tables / "hydrokg_integrated_nodes.csv", tables / "hydrokg_integrated_edges.csv"
    )
    config = load_graph_query_config(
        root / "configs/queries/hydrokg_graph_queries_v1.json"
    )
    queries = {query["query_id"]: query for query in config["queries"]}
    query = queries[CANONICAL_QUERY]
    trace = read_rows(tables / "hydrokg_query_execution_trace.csv")
    concepts = query["required_concepts"]
    canonical = run_graph_query(graph, query)
    require(len(trace) == len(concepts) == len(flat), "Expected four query stages.")
    for index, (saved, concept, flat_ids, count) in enumerate(
        zip(trace, concepts, flat, TRACE_COUNTS), start=1
    ):
        # Each prefix is executed by the same graph engine as the full query.
        result = canonical if index == len(concepts) else run_graph_query(
            graph, dict(query, required_concepts=concepts[:index])
        )
        graph_ids = tuple(row["device_record_id"] for row in result.device_matches)
        saved_ids = tuple(json.loads(saved["candidate_device_ids_json"]))
        require(
            graph_ids == flat_ids == saved_ids
            and len(graph_ids) == count == int(saved["candidate_device_count"])
            and concept["relation_type"] == saved["relation_type"]
            and index == int(saved["step_index"]),
            f"Flat, graph, or saved trace differs at stage {index}.",
        )

    saved_matches = read_rows(tables / "hydrokg_query_device_matches.csv")
    require(
        canonical.device_matches == saved_matches,
        "The canonical graph matches differ from the frozen CSV.",
    )
    require(
        canonical.paths == read_rows(tables / "hydrokg_query_paths.csv"),
        "The canonical selection paths differ from the frozen CSV.",
    )
    requirements = run_pathway_requirement_query(graph, queries[PATHWAY_QUERY])
    require(
        requirements.requirements
        == read_rows(tables / "hydrokg_query_pathway_requirements.csv"),
        "Graph pathway requirements differ from the frozen CSV.",
    )
    pathway = next(
        row for row in requirements.requirements if row["pathway"] == FILM_PATHWAY
    )
    comparison = comparison_rows(
        seed, flat[-1], graph, canonical.device_matches, pathway
    )
    return sensitivity, comparison


def main(root: Path = ROOT) -> None:
    sensitivity, comparison = reproduce(root)
    for filename, rows in ((SENSITIVITY, sensitivity), (COMPARISON, comparison)):
        path = root / TABLES / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {path.relative_to(root).as_posix()} ({len(rows)} rows)")
    print("Verified flat-table and graph trace: 30 -> 10 -> 6 -> 6")


if __name__ == "__main__":
    main()

"""Run configured graph-native queries over integrated HydroKG tables."""

from __future__ import annotations

from pathlib import Path

from hydrokg.query.graph_query import (
    NACL_DEVICE_MATCHES_FILENAME,
    NACL_QUERY_PATHS_FILENAME,
    load_graph_query_config,
    load_integrated_graph,
    run_graph_query,
    run_high_power_warning_query,
    run_material_structure_route_query,
    run_pathway_requirement_query,
    write_graph_query_outputs,
    write_high_power_warning_outputs,
    write_material_structure_route_outputs,
    write_pathway_requirement_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIRECTORY = REPOSITORY_ROOT / "results" / "tables"
INTEGRATED_NODES_PATH = RESULTS_DIRECTORY / "hydrokg_integrated_nodes.csv"
INTEGRATED_EDGES_PATH = RESULTS_DIRECTORY / "hydrokg_integrated_edges.csv"
QUERY_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "queries"
    / "hydrokg_graph_queries_v1.json"
)


def main() -> int:
    """Run configured graph queries and write match and path tables."""
    graph = load_integrated_graph(
        INTEGRATED_NODES_PATH,
        INTEGRATED_EDGES_PATH,
    )
    config = load_graph_query_config(QUERY_CONFIG_PATH)
    queries = {
        query["query_id"]: query for query in config["queries"]
    }
    polymer_query = queries["canonical_polymer_film_low_r_high_power"]
    polymer_outputs = run_graph_query(graph, polymer_query)
    polymer_paths = write_graph_query_outputs(
        polymer_outputs,
        RESULTS_DIRECTORY,
    )

    nacl_query = queries["exact_nacl_primary_na_context"]
    nacl_outputs = run_graph_query(graph, nacl_query)
    nacl_paths = write_graph_query_outputs(
        nacl_outputs,
        RESULTS_DIRECTORY,
        device_matches_filename=NACL_DEVICE_MATCHES_FILENAME,
        paths_filename=NACL_QUERY_PATHS_FILENAME,
    )

    route_query = queries["low_r_material_structure_routes"]
    route_outputs = run_material_structure_route_query(graph, route_query)
    route_paths = write_material_structure_route_outputs(
        route_outputs,
        RESULTS_DIRECTORY,
    )

    warning_query = queries["high_power_warning_contexts"]
    warning_outputs = run_high_power_warning_query(graph, warning_query)
    warning_paths = write_high_power_warning_outputs(
        warning_outputs,
        RESULTS_DIRECTORY,
    )

    pathway_query = queries["pathway_design_and_reporting_requirements"]
    pathway_outputs = run_pathway_requirement_query(graph, pathway_query)
    pathway_paths = write_pathway_requirement_outputs(
        pathway_outputs,
        RESULTS_DIRECTORY,
    )

    print(f"Query: {polymer_query['query_id']}")
    print(f"Matched devices: {len(polymer_outputs.device_matches)}")
    for row in polymer_outputs.device_matches:
        print(f"  {row['device_record_id']}")
    print(f"Query proof-path rows (reproducibility detail): {len(polymer_outputs.paths)}")
    print(f"Query: {nacl_query['query_id']}")
    print(f"Matched devices: {len(nacl_outputs.device_matches)}")
    print(f"Query: {route_query['query_id']}")
    print(f"Matched devices: {len(route_outputs.routes)}")
    print(f"Distinct routes: {len(route_outputs.summaries)}")
    print(f"Query: {warning_query['query_id']}")
    print(f"Matched devices: {len(warning_outputs.contexts)}")
    profile_counts: dict[str, int] = {}
    for row in warning_outputs.contexts:
        profile = row["warning_profile"]
        profile_counts[profile] = profile_counts.get(profile, 0) + 1
    print("Warning profiles:")
    for profile in (
        "no_warning",
        "reporting_warning_only",
        "electrochemical_warning_only",
        "mixed_warning",
    ):
        print(f"  {profile}: {profile_counts.get(profile, 0)}")
    print("Warning summary:")
    for row in warning_outputs.summaries:
        print(
            f"  {row['warning_cohort']}: "
            f"matched={row['matched_device_count']}, "
            f"low_R={row['low_R_device_count']}, "
            f"pathway={row['pathway_device_count']}"
        )
    print(f"Query: {pathway_query['query_id']}")
    print(f"Pathways: {len(pathway_outputs.requirements)}")
    print(f"Shared concepts: {len(pathway_outputs.shared_concepts)}")
    print("Inputs:")
    print(
        "  "
        + INTEGRATED_NODES_PATH.relative_to(REPOSITORY_ROOT).as_posix()
    )
    print(
        "  "
        + INTEGRATED_EDGES_PATH.relative_to(REPOSITORY_ROOT).as_posix()
    )
    for path in (
        polymer_paths.device_matches,
        polymer_paths.paths,
        nacl_paths.device_matches,
        nacl_paths.paths,
        route_paths.routes,
        route_paths.summaries,
        warning_paths.contexts,
        warning_paths.summaries,
        pathway_paths.requirements,
        pathway_paths.shared_concepts,
    ):
        print(f"Wrote: {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

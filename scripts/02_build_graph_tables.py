"""Build HydroKG v1 node and edge CSV tables."""

from __future__ import annotations

from pathlib import Path

from hydrokg.graph.tables import (
    build_graph_tables,
    load_schema,
    write_graph_tables,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPOSITORY_ROOT / "configs" / "schema" / "hydrokg_schema_v1.json"
SEED_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "raw"
    / "hydrovoltaic_ml_curated_159_seed.csv"
)
OUTPUT_DIRECTORY = REPOSITORY_ROOT / "data" / "processed"


def main() -> int:
    """Build and write graph tables."""
    tables = build_graph_tables(SEED_PATH, load_schema(SCHEMA_PATH))
    paths = write_graph_tables(tables, OUTPUT_DIRECTORY)

    print(f"Nodes: {len(tables.nodes)}")
    print(f"Edges: {len(tables.edges)}")
    print(f"Wrote: {paths.nodes.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"Wrote: {paths.edges.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Show the frozen HydroKG representation and query outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "results" / "tables"


def read_rows(name: str) -> list[dict[str, str]]:
    with (TABLES / name).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    nodes = read_rows("hydrokg_integrated_nodes.csv")
    edges = read_rows("hydrokg_integrated_edges.csv")
    matches = read_rows("hydrokg_query_device_matches.csv")
    low_r_routes = read_rows("hydrokg_query_low_r_route_summary.csv")
    nacl_matches = read_rows("hydrokg_query_nacl_primary_na_device_matches.csv")

    print("HydroKG representation")
    print(f"- nodes: {len(nodes)}")
    print(f"- links: {len(edges)}")
    print(f"- low-R records/routes: 55/{len(low_r_routes)}")
    print(f"- NaCl/Na+ records: {len(nacl_matches)}")

    print("\nFour-criterion query matches")
    for row in matches:
        concepts = json.loads(row["matched_concepts_json"])
        print(
            f"- {row['device_record_id']}: "
            f"{concepts['MaterialClass']} / {concepts['StructureClass']} / "
            f"{concepts['RBin']} / {concepts['PowerBin']} / {row['paper_doi']}"
        )

    print("\nInterpretation boundary")
    print("- links encode curated or rule-derived context; they do not establish causality")
    print("- query membership does not experimentally validate a mechanism")


if __name__ == "__main__":
    main()

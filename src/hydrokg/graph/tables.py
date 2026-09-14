"""Build flat HydroKG node and edge tables from the seed CSV."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

NODE_COLUMNS = (
    "node_id",
    "node_type",
    "label",
    "source_column",
    "source_value",
    "properties_json",
)
EDGE_COLUMNS = (
    "edge_id",
    "source_id",
    "target_id",
    "edge_type",
    "source_column",
    "source_value",
    "properties_json",
)
NODE_FILENAME = "hydrokg_nodes.csv"
EDGE_FILENAME = "hydrokg_edges.csv"


@dataclass(frozen=True)
class GraphTables:
    """In-memory node and edge table rows."""

    nodes: tuple[dict[str, str], ...]
    edges: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class GraphTablePaths:
    """Paths written by :func:`write_graph_tables`."""

    nodes: Path
    edges: Path


def load_schema(path: Path | str) -> dict[str, Any]:
    """Load a HydroKG schema mapping from JSON."""
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_seed_csv(path: Path | str) -> tuple[dict[str, str | None], ...]:
    """Load seed CSV rows."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return tuple(csv.DictReader(handle))


def build_graph_tables(
    seed_csv_path: Path | str,
    schema: Mapping[str, Any],
) -> GraphTables:
    """Build deterministic node and edge rows according to a schema mapping."""
    rows = load_seed_csv(seed_csv_path)
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    concept_ids: dict[tuple[str, str], str] = {}
    node_type_counts: dict[str, int] = {}

    device_attribute_types = _device_attribute_types(schema)
    paper_attribute_types = schema["node_types"]["Paper"]["attributes"]

    for row_number, row in enumerate(rows, start=1):
        device_id = f"device_record_{row_number:03d}"
        nodes.append(
            _node_row(
                node_id=device_id,
                node_type="DeviceRecord",
                label=device_id,
                source_column="row_number",
                source_value=str(row_number),
                properties=_typed_properties(row, device_attribute_types),
            )
        )

        for node_type, definition in schema["node_types"].items():
            if node_type == "DeviceRecord":
                continue
            for source_column in definition.get("identity_columns", ()):
                source_value = _trimmed(row.get(source_column))
                if not source_value:
                    continue
                key = (node_type, source_value)
                if key in concept_ids:
                    continue

                node_type_counts[node_type] = (
                    node_type_counts.get(node_type, 0) + 1
                )
                node_id = (
                    f"{_snake_case(node_type)}_"
                    f"{node_type_counts[node_type]:03d}"
                )
                concept_ids[key] = node_id
                properties: dict[str, Any] = {}
                if node_type == "Paper":
                    properties = _typed_properties(row, paper_attribute_types)
                elif node_type == "Electrolyte":
                    properties = {"electrolyte_category": source_column}

                nodes.append(
                    _node_row(
                        node_id=node_id,
                        node_type=node_type,
                        label=source_value,
                        source_column=source_column,
                        source_value=source_value,
                        properties=properties,
                    )
                )

    for row_number, row in enumerate(rows, start=1):
        device_id = f"device_record_{row_number:03d}"
        for edge_type, definition in schema["edge_types"].items():
            if edge_type == "has_secondary_mobile_ion" and not _is_true(
                row.get("secondary_ion_present")
            ):
                continue

            concept_node_type = (
                definition["source_node"]
                if edge_type == "reports"
                else definition["target_node"]
            )
            for source_column in definition["source_columns"]:
                source_value = _trimmed(row.get(source_column))
                if not source_value:
                    continue

                concept_id = concept_ids[(concept_node_type, source_value)]
                if edge_type == "reports":
                    source_id = concept_id
                    target_id = device_id
                else:
                    source_id = device_id
                    target_id = concept_id

                edges.append(
                    {
                        "edge_id": f"edge_{len(edges) + 1:06d}",
                        "source_id": source_id,
                        "target_id": target_id,
                        "edge_type": edge_type,
                        "source_column": source_column,
                        "source_value": source_value,
                        "properties_json": "{}",
                    }
                )

    return GraphTables(nodes=tuple(nodes), edges=tuple(edges))


def write_graph_tables(
    tables: GraphTables,
    output_directory: Path | str,
) -> GraphTablePaths:
    """Write node and edge tables to an output directory."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    node_path = output_directory / NODE_FILENAME
    edge_path = output_directory / EDGE_FILENAME

    _write_csv(node_path, NODE_COLUMNS, tables.nodes)
    _write_csv(edge_path, EDGE_COLUMNS, tables.edges)
    return GraphTablePaths(nodes=node_path, edges=edge_path)


def _device_attribute_types(
    schema: Mapping[str, Any],
) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for group in schema["node_types"]["DeviceRecord"]["attributes"].values():
        attributes.update(group)
    return attributes


def _typed_properties(
    row: Mapping[str, str | None],
    attribute_types: Mapping[str, str],
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for column, value_type in attribute_types.items():
        value = _trimmed(row.get(column))
        if not value:
            continue
        properties[column] = _coerce_value(value, value_type)
    return properties


def _coerce_value(value: str, value_type: str) -> Any:
    if value_type == "boolean":
        return _is_true(value)
    if value_type == "integer":
        return int(float(value))
    if value_type == "number":
        return float(value)
    return value


def _node_row(
    *,
    node_id: str,
    node_type: str,
    label: str,
    source_column: str,
    source_value: str,
    properties: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "label": label,
        "source_column": source_column,
        "source_value": source_value,
        "properties_json": json.dumps(
            properties,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ),
    }


def _trimmed(value: str | None) -> str:
    return value.strip() if value else ""


def _is_true(value: str | None) -> bool:
    return _trimmed(value).lower() in {"1", "true", "yes"}


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

"""Build focused device subsets and their connected concept summaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DEVICES_FILENAME = "hydrokg_low_r_high_power_devices.csv"
CONCEPT_COUNTS_FILENAME = "hydrokg_low_r_high_power_concept_counts.csv"
PATHWAY_SUMMARY_FILENAME = "hydrokg_low_r_high_power_pathway_summary.csv"

DEVICE_OUTPUT_COLUMNS = (
    "device_record_id",
    "paper_doi",
    "ref_year",
    "material_class",
    "structure_class",
    "ion_type",
    "primary_mobile_ion",
    "dominant_mechanism",
    "mechanism_simple",
    "internal_resistance_Mohm",
    "estimated_power_density_uW_cm2",
    "r_bin",
    "low_R_flag",
    "high_power_flag",
    "auxiliary_redox_present",
    "metal_electrode",
)
CONCEPT_COUNT_COLUMNS = (
    "node_type",
    "label",
    "count",
    "fraction_of_selected_devices",
)
PATHWAY_GROUP_COLUMNS = (
    "material_class",
    "structure_class",
    "dominant_mechanism",
)
PATHWAY_SUMMARY_COLUMNS = (
    *PATHWAY_GROUP_COLUMNS,
    "device_count",
    "median_internal_resistance_Mohm",
    "median_estimated_power_density_uW_cm2",
)
NON_CONCEPT_NODE_TYPES = frozenset({"DeviceRecord", "Paper"})


@dataclass(frozen=True)
class SubsetOutputPaths:
    """Paths written by :func:`write_low_r_high_power_outputs`."""

    devices: Path
    concept_counts: Path
    pathway_summary: Path


def load_r_centered_device_table(path: Path | str) -> pd.DataFrame:
    """Load the processed R-centered device table."""
    table = pd.read_csv(path)
    _require_columns(
        table,
        (*DEVICE_OUTPUT_COLUMNS, "low_R_flag", "high_power_flag"),
        "R-centered device table",
    )
    for column in ("low_R_flag", "high_power_flag"):
        table[column] = _to_boolean(table[column])
    return table


def load_graph_nodes(path: Path | str) -> pd.DataFrame:
    """Load the processed graph node table."""
    nodes = pd.read_csv(path)
    _require_columns(nodes, ("node_id", "node_type", "label"), "node table")
    return nodes


def load_graph_edges(path: Path | str) -> pd.DataFrame:
    """Load the processed graph edge table."""
    edges = pd.read_csv(path)
    _require_columns(edges, ("source_id", "target_id"), "edge table")
    return edges


def select_low_r_high_power_devices(
    device_table: pd.DataFrame,
) -> pd.DataFrame:
    """Select devices flagged as both low resistance and high power."""
    _require_columns(
        device_table,
        DEVICE_OUTPUT_COLUMNS,
        "R-centered device table",
    )
    low_r = _to_boolean(device_table["low_R_flag"])
    high_power = _to_boolean(device_table["high_power_flag"])
    return (
        device_table.loc[low_r & high_power, DEVICE_OUTPUT_COLUMNS]
        .copy()
        .reset_index(drop=True)
    )


def get_connected_concept_nodes(
    selected_devices: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
) -> pd.DataFrame:
    """Return concept nodes directly connected to selected DeviceRecords."""
    _require_columns(
        selected_devices,
        ("device_record_id",),
        "selected device table",
    )
    _require_columns(nodes, ("node_id", "node_type", "label"), "node table")
    _require_columns(edges, ("source_id", "target_id"), "edge table")

    selected_ids = set(selected_devices["device_record_id"].dropna())
    outgoing = edges.loc[
        edges["source_id"].isin(selected_ids),
        ["source_id", "target_id"],
    ].rename(
        columns={"source_id": "device_record_id", "target_id": "node_id"}
    )
    incoming = edges.loc[
        edges["target_id"].isin(selected_ids),
        ["target_id", "source_id"],
    ].rename(
        columns={"target_id": "device_record_id", "source_id": "node_id"}
    )
    connections = pd.concat([outgoing, incoming], ignore_index=True)
    connections = connections.drop_duplicates(
        subset=["device_record_id", "node_id"]
    )

    concepts = connections.merge(
        nodes.loc[:, ["node_id", "node_type", "label"]],
        on="node_id",
        how="inner",
        validate="many_to_one",
    )
    concepts = concepts.loc[
        ~concepts["node_type"].isin(NON_CONCEPT_NODE_TYPES)
    ]
    return concepts.sort_values(
        ["device_record_id", "node_type", "label", "node_id"],
        kind="stable",
    ).reset_index(drop=True)


def build_concept_counts(
    selected_devices: pd.DataFrame,
    connected_concepts: pd.DataFrame,
) -> pd.DataFrame:
    """Count selected devices connected to each concept node."""
    _require_columns(
        selected_devices,
        ("device_record_id",),
        "selected device table",
    )
    _require_columns(
        connected_concepts,
        ("device_record_id", "node_type", "label"),
        "connected concept table",
    )

    selected_count = selected_devices["device_record_id"].nunique()
    counts = (
        connected_concepts.drop_duplicates(
            subset=["device_record_id", "node_type", "label"]
        )
        .groupby(["node_type", "label"], sort=True, dropna=False)
        .size()
        .rename("count")
        .reset_index()
    )
    counts["fraction_of_selected_devices"] = (
        counts["count"] / selected_count if selected_count else 0.0
    )
    return counts.loc[:, CONCEPT_COUNT_COLUMNS]


def build_pathway_summary(selected_devices: pd.DataFrame) -> pd.DataFrame:
    """Summarize selected devices by material, structure, and mechanism."""
    _require_columns(
        selected_devices,
        (
            "device_record_id",
            *PATHWAY_GROUP_COLUMNS,
            "internal_resistance_Mohm",
            "estimated_power_density_uW_cm2",
        ),
        "selected device table",
    )
    summary = (
        selected_devices.groupby(
            list(PATHWAY_GROUP_COLUMNS),
            sort=True,
            dropna=False,
        )
        .agg(
            device_count=("device_record_id", "nunique"),
            median_internal_resistance_Mohm=(
                "internal_resistance_Mohm",
                "median",
            ),
            median_estimated_power_density_uW_cm2=(
                "estimated_power_density_uW_cm2",
                "median",
            ),
        )
        .reset_index()
    )
    return summary.loc[:, PATHWAY_SUMMARY_COLUMNS]


def write_low_r_high_power_outputs(
    selected_devices: pd.DataFrame,
    concept_counts: pd.DataFrame,
    pathway_summary: pd.DataFrame,
    output_directory: Path | str,
) -> SubsetOutputPaths:
    """Write all low-R/high-power subset result tables."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = SubsetOutputPaths(
        devices=output_directory / DEVICES_FILENAME,
        concept_counts=output_directory / CONCEPT_COUNTS_FILENAME,
        pathway_summary=output_directory / PATHWAY_SUMMARY_FILENAME,
    )
    selected_devices.loc[:, DEVICE_OUTPUT_COLUMNS].to_csv(
        paths.devices,
        index=False,
    )
    concept_counts.loc[:, CONCEPT_COUNT_COLUMNS].to_csv(
        paths.concept_counts,
        index=False,
    )
    pathway_summary.loc[:, PATHWAY_SUMMARY_COLUMNS].to_csv(
        paths.pathway_summary,
        index=False,
    )
    return paths


def _require_columns(
    table: pd.DataFrame,
    required_columns: tuple[str, ...],
    table_name: str,
) -> None:
    missing_columns = sorted(set(required_columns) - set(table.columns))
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"{table_name} is missing required columns: {missing}")


def _to_boolean(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False)
    normalized = values.astype("string").str.strip().str.lower()
    return normalized.isin(("1", "true", "yes"))

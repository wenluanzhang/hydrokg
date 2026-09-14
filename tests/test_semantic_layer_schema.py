"""Tests for the HydroKG R-centered semantic-layer design."""

import json
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "configs"
    / "schema"
    / "hydrokg_semantic_layer_v1.json"
)

REQUIRED_CONCEPT_TYPES = {
    "RBin",
    "PowerBin",
    "Pathway",
    "WarningFlag",
    "DesignVariable",
    "ReportingItem",
}
REQUIRED_RELATION_TYPES = {
    "device_has_r_bin",
    "device_has_power_bin",
    "device_activates_pathway",
    "device_has_warning_flag",
    "pathway_targets_r_bin",
    "pathway_targets_power_bin",
    "pathway_uses_design_variable",
    "pathway_has_warning_flag",
    "pathway_requires_reporting_item",
}
REQUIRED_R_BINS = {"missing_R", "low_R", "high_R"}
REQUIRED_POWER_BINS = {
    "high_power",
    "non_high_power",
    "missing_power",
}
EXPECTED_PATHWAYS = {
    "connected_pore_ion_transport_pathway",
    "hydrated_network_ionic_conduction_pathway",
    "biomass_fiber_capillary_pathway",
    "film_based_ion_concentration_gradient_pathway",
}


def load_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_semantic_layer_schema_loads_as_json() -> None:
    schema = load_schema()

    assert isinstance(schema, dict)


def test_required_semantic_concept_types_exist() -> None:
    schema = load_schema()

    assert REQUIRED_CONCEPT_TYPES <= set(schema["concept_types"])


def test_required_relation_types_exist() -> None:
    schema = load_schema()

    assert REQUIRED_RELATION_TYPES <= set(schema["relation_types"])


def test_relation_endpoints_refer_to_defined_types() -> None:
    schema = load_schema()
    valid_types = set(schema["concept_types"]) | {"DeviceRecord"}

    for relation_name, relation in schema["relation_types"].items():
        assert relation["source_type"] in valid_types, relation_name
        assert relation["target_type"] in valid_types, relation_name


def test_required_r_bin_concepts_are_present() -> None:
    schema = load_schema()
    concepts = schema["concept_types"]["RBin"]["concepts"]

    assert REQUIRED_R_BINS <= set(concepts)


def test_required_power_bin_concepts_are_present() -> None:
    schema = load_schema()
    concepts = schema["concept_types"]["PowerBin"]["concepts"]

    assert REQUIRED_POWER_BINS <= set(concepts)


def test_pathway_concepts_are_only_physical_hypotheses() -> None:
    schema = load_schema()
    concepts = schema["concept_types"]["Pathway"]["concepts"]

    assert set(concepts) == EXPECTED_PATHWAYS


def test_electrochemical_control_warning_is_present() -> None:
    schema = load_schema()
    concepts = schema["concept_types"]["WarningFlag"]["concepts"]

    assert "electrochemical_control_needed_warning" in concepts
    assert "electrochemical_confounding_warning" not in concepts

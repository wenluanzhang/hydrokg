"""Tests for HydroKG Stage 5A figure-ready statistics."""

from pathlib import Path

from hydrokg.analysis.figure_stats import (
    build_r_bin_by_material_structure_counts,
    load_r_centered_device_table,
    summarize_power_by_material_structure,
    summarize_r_by_material_class,
    summarize_r_by_structure_class,
    write_figure_statistics_outputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEVICE_TABLE_PATH = (
    REPOSITORY_ROOT
    / "data"
    / "processed"
    / "hydrokg_r_centered_device_table.csv"
)


def build_figure_statistics():
    device_table = load_r_centered_device_table(DEVICE_TABLE_PATH)
    return (
        summarize_r_by_material_class(device_table),
        summarize_r_by_structure_class(device_table),
        summarize_power_by_material_structure(device_table),
        build_r_bin_by_material_structure_counts(device_table),
    )


def test_material_class_summary_is_not_empty() -> None:
    material_summary, _, _, _ = build_figure_statistics()

    assert not material_summary.empty


def test_structure_class_summary_is_not_empty() -> None:
    _, structure_summary, _, _ = build_figure_statistics()

    assert not structure_summary.empty


def test_material_structure_summary_is_not_empty() -> None:
    _, _, power_summary, _ = build_figure_statistics()

    assert not power_summary.empty


def test_r_bin_material_structure_counts_sum_to_159() -> None:
    _, _, _, r_bin_counts = build_figure_statistics()

    assert int(r_bin_counts["device_count"].sum()) == 159


def test_low_r_high_power_count_is_not_greater_than_low_r_count() -> None:
    _, _, power_summary, _ = build_figure_statistics()

    assert (
        power_summary["low_R_high_power_count"]
        <= power_summary["low_R_count"]
    ).all()


def test_r_reported_count_is_not_greater_than_device_count() -> None:
    material_summary, structure_summary, power_summary, _ = (
        build_figure_statistics()
    )

    for summary in (
        material_summary,
        structure_summary,
        power_summary,
    ):
        assert (
            summary["r_reported_count"] <= summary["device_count"]
        ).all()


def test_figure_statistics_outputs_can_be_written(tmp_path: Path) -> None:
    material_summary, structure_summary, power_summary, r_bin_counts = (
        build_figure_statistics()
    )
    paths = write_figure_statistics_outputs(
        material_summary,
        structure_summary,
        power_summary,
        r_bin_counts,
        tmp_path / "tables",
    )

    assert paths.material_summary.is_file()
    assert paths.structure_summary.is_file()
    assert paths.power_summary.is_file()
    assert paths.r_bin_counts.is_file()

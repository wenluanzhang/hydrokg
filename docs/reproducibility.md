# Reproducibility

Run all commands from the repository root. Python 3.10 or later is required.
The supported workflow reproduces HydroKG data and software products only. No
TeX distribution, `latexmk`, `pdflatex`, or BibTeX is required, and manuscript,
Supporting Information, and publication-figure generation are intentionally out
of scope for this repository.

All retained workflow steps are deterministic and read the frozen input under
`data/raw/`. Steps that write results write them under `data/processed/` or
`results/tables/`.

## A. Install the environment

Using a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Conda users may instead run `conda env create -f environment.yml` and activate
the resulting `hydrokg` environment.

## B. Validate the frozen input

```bash
python scripts/01_validate_data.py
```

This checks the frozen curated dataset: 159 device records, 52 fields, and the
source-reporting completeness of the reported performance fields
(108/159 power density, 112/159 internal resistance, 126/159 relative humidity).

## C. Rebuild the base graph

```bash
python scripts/02_build_graph_tables.py
python scripts/03_summarize_graph_tables.py
python scripts/04_audit_graph_content.py
```

This reproduces the 581-node / 1777-edge DeviceRecord-centered base graph,
its node and relation type counts, and its integrity summary. All edge
endpoints resolve to declared nodes.

## D. Build the rule-derived, semantic, and query contexts

```bash
python scripts/05_build_r_centered_device_table.py
python scripts/06_analyze_low_r_high_power.py
python scripts/07_analyze_reporting_completeness.py
python scripts/08_build_figure_ready_statistics.py
python scripts/09_apply_pathway_rules.py
python scripts/13_build_evidence_provenance.py
python scripts/16_materialize_semantic_graph.py
```

These steps build the R-centered device table, the low-resistance and reporting
completeness subsets, the material/structure and resistance-bin statistics, the
deterministic pathway-rule applications, the evidence-provenance ledger, and the
materialized semantic layer. The integrated representation contains 614 nodes
and 2447 links, and all endpoints resolve.

The evidence-provenance step records how deterministic rules were applied to the
frozen records; it does not add an adjudication layer or validate a mechanism.

## E. Run the relational queries

```bash
python scripts/17_run_graph_queries.py
python scripts/37_run_semantic_ablation_audit.py
```

`scripts/17_run_graph_queries.py` executes the four supported query families
against the integrated representation: the four-criterion polymer/film context
query, the NaCl/Na+ primary-ionic query, the low-resistance material/structure
route query, and the high-power warning-context and pathway-requirement queries.
Their frozen outputs are written into `results/tables/`.

`scripts/37_run_semantic_ablation_audit.py` re-derives the canonical query
membership stage by stage over the released semantic layers and records the
result in `results/tables/hydrokg_semantic_ablation_audit.csv`. It is a
deterministic check that the released rule-derived context is sufficient for the
reported query membership; it does not extend the graph.

### Reproduce the R3 threshold and selection checks

Use the Python and pandas environment from section A. The checks read the frozen
seed at `data/raw/hydrovoltaic_ml_curated_159_seed.csv`, the canonical definition
in `configs/queries/hydrokg_graph_queries_v1.json`, and the released integrated
graph and query CSVs in `results/tables/`. Run from the repository root.

```bash
python scripts/reproduce_r3_checks.py
```

- `results/tables/hydrokg_threshold_sensitivity.csv` reports the estimated-power
  cutoffs, exact membership and differences from the canonical six for the nine
  tested combinations. The power quantiles use the full seed and linear
  interpolation. Both resistance and power comparisons include their boundaries.
- `results/tables/hydrokg_flat_table_graph_comparison.csv` records matching IDs
  independently selected from the seed and the graph. The script checks all
  four stages against the frozen trace (`30 -> 10 -> 6 -> 6`). The comparison
  joins the released graph evidence to the matched seed rows for reporting and
  electrode-control follow-up. It records individual edge witnesses from the
  previously in-memory inspection separately from the saved selection paths.

The grid measures membership at the tested thresholds. Selection parity shows
equivalent membership. The warning and requirement fields identify reporting
and control questions for source follow-up. Missing values express gaps in the
curated seed, and source-paper inspection and experimental validation remain open.

## F. Validate the frozen outputs

```bash
python scripts/validate_outputs.py
```

This validates the released HydroKG invariants: dataset size and field count,
source-reporting counts, base and integrated graph sizes with endpoint
resolution, low-resistance route counts and representative routes, NaCl/Na+
query record and context counts, the four-criterion query membership and its
30 -> 10 -> 6 -> 6 progression. It does not check for manuscript, Supporting
Information, or publication-figure files.

## G. Run the demo

```bash
python scripts/demo_hydrokg_query.py
```

The demo prints the frozen integrated graph size, the low-resistance record and
route counts, the NaCl/Na+ record count, the four-criterion query membership
with source DOIs, and the interpretation boundaries that apply to query results.

## H. Run the test suite

```bash
python -m pytest
```

The test suite is portable, deterministic, and read-only with respect to the
frozen release artifacts: tests that exercise generator write paths redirect
their output into pytest's temporary directory, so a full run leaves the frozen
tables byte-identical.

## Alternative: inspect the frozen outputs only

Every retained result table in `results/tables/` and the base graph tables in
`data/processed/` are versioned. Steps C to E therefore only need to be rerun to
verify reproducibility; inspection and validation (steps F and G) work directly
from the frozen files.

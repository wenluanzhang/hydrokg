# HydroKG

HydroKG combines a frozen literature-derived dataset of 159 hydrovoltaic device
records and 52 curated fields with a relational knowledge graph. It supports
cross-cutting comparison of material, structure, ionic, performance, and
reporting contexts while retaining links to record-level source DOI provenance.

This repository is a data and research-software repository. It distributes the
curated dataset, the HydroKG graph construction and relational-query workflows,
and the frozen machine-readable outputs needed to inspect and validate the
released representation.

## Associated manuscript

**HydroKG: A Knowledge Graph for Relational Exploration of Curated
Hydrovoltaic Device Records**

Wenluan Zhang, Runru Tristan Liu, and Yumin Huang.

This repository provides the curated data, HydroKG graph construction,
relational-query workflows, and reproducibility resources supporting the study.
The manuscript itself is not distributed through this repository.

## Repository contents

- `data/raw/`: frozen 159-record, 52-field curated dataset.
- `data/processed/`: reproducibly generated base-graph and device tables.
- `results/tables/`: frozen machine-readable graph, query, and validation outputs.
- `configs/`: schemas, controlled vocabularies, query definitions, and pathway rules.
- `scripts/`: supported data, graph, and query workflow entry points.
- `src/hydrokg/`: reusable workflow implementation.
- `tests/`: automated tests for the released HydroKG software and data.
- `docs/`: provenance, reproducibility, and interpretation guidance.

Manuscript sources, Supporting Information, and publication figure or table
assets are maintained separately and are not part of this repository.

## Quick start

Python 3.10 or later is required.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python scripts/validate_outputs.py
python scripts/demo_hydrokg_query.py
```

## Reproduce the HydroKG workflow

The supported workflow validates the frozen input, rebuilds the base graph,
materializes the rule-derived and semantic contexts, runs the relational
queries, and validates the frozen outputs. Exact commands are listed in
[`docs/reproducibility.md`](docs/reproducibility.md).

No LaTeX installation is required. Figure generation and manuscript/SI
rendering are not part of this repository's workflow.

## Data provenance

The dataset was curated and harmonized from the hydrovoltaic literature.
Record-level DOI provenance is retained where available. Source articles and
article PDFs are not redistributed; access and reuse of those publications
remain governed by their publishers and authors. See
[`docs/data_provenance.md`](docs/data_provenance.md).

## Interpretation boundaries

Graph links encode curated, normalized, or rule-derived relationships. They do
not establish causality or validate a physical mechanism. Missing reporting is
unavailable information, not negative evidence. See
[`docs/interpretation_boundaries.md`](docs/interpretation_boundaries.md).

## Citation

Citation metadata is provided in [`CITATION.cff`](CITATION.cff). Do not infer a
manuscript DOI or publication status from this repository.

## License

Repository code is provided under the [MIT License](LICENSE). This license does
not relicense source articles, article content, or other publisher-owned
material. No separate dataset license is asserted by this release preparation.

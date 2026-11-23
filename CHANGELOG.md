# Changelog

Release notes per implementation step. TopoMarket identifies releases by step number and semantic
version; no release dates or schedules are published in repository content.

## v0.8.0 - Step 8: Package and rehearse the public release

- Offline `topomarket release-check` command: version consistency, repository hygiene, packaged
  JSON resources, dependency lock, synthetic-fixture determinism, public-mode smoke commands and
  the committed synthetic showcase fixture.
- Clean-checkout release workflow building sdist/wheel, running `twine check`, retaining the test
  report and release artifacts.
- Dependency lock (`requirements.lock`), release runbook (`docs/RELEASING.md`) and a synthetic-only
  public walkthrough (`docs/WALKTHROUGH.md`) with a committed reproducible showcase fixture.
- License and data-source notices reviewed; README status updated for the completed release.
- No private data, credentials, ledgers or release dates are committed.

## v0.7.0 - Step 7: Interactive research dashboard

- Four-screen Streamlit dashboard (Overview, Topology, Validation, Data) over one persistent
  selection with blind replay safety, keyboard equivalents, accessible tokens/table alternatives/
  reduced motion and cached-performance benchmarks.
- Plain-text dashboard fallback without Streamlit; optional `[ui]` extra.

## v0.6.0 - Step 6: Chronological evaluation and warning evidence

- Labels/breach episodes, early/post-onset/false/missed alert matching, frozen alert policies with
  calibrated percentile cutoffs, out-of-sample evaluation metrics, paired moving-block bootstrap,
  controls/ablations, evidence wording and an append-only private ledger.

## v0.5.0 - Step 5: Industry explorer

- 60x12 industry cloud with robust scaling/PCA/Rips persistence, deterministic correlation-distance
  Mapper graph with overlapping volatility intervals, measurements, tooltips and a combined payload
  CLI.

## v0.4.0 - Step 4: Persistent homology and anomaly score

- Causal delay-embedding/Vietoris-Rips score with midrank percentile normalization, frozen
  configuration registry, warm-up/gap states, deterministic CSV export and the `topology` CLI.

## v0.3.0 - Step 3: Update and recovery

- Fixed-source HTTPS refresh with conditional GET/staging/validation, atomic immutable snapshots,
  revisions, single-writer lock, last-good recovery and the `refresh`/`sources` CLI.

## v0.2.0 - Step 2: Seed import

- Local seed adapters (OpenIntro, FRED, Cboe, Kenneth French, OFR), raw hash registry, parser
  reports, normalized tables (`sp500_daily`, `industries_daily`, `tda_daily`) and spec-aligned
  synthetic demo schema.

## v0.1.0 - Step 1: Runnable scaffold

- Python package/CLI, Streamlit shell, demo/private profiles, deterministic synthetic fixtures,
  snapshot manifest helpers, CI and security scanning.

# v1.1 acceptance evidence

Evidence for the TopoMarket v1.1 acceptance-review release (epic
[#48](https://github.com/SergeyGer/TopoMarket/issues/48)). The v1.1 work packages and their
acceptance gates are in [docs/UPGRADE_v1.1.md](UPGRADE_v1.1.md); the v1.0 evidence remains in
[docs/ACCEPTANCE_v1.0.md](ACCEPTANCE_v1.0.md) and the v1.0 report is retained as
[docs/reports/evaluation-v1.0-baseline.json](reports/evaluation-v1.0-baseline.json).

Environment: Python 3.12.3, project `.venv`, Playwright Chromium headless at 1440x900 and 390x844,
synthetic `showcase/` fixture (snapshot `showcase-synthetic`, seed 4242, 5,673 sessions
2005-01-03..2026-09-30). Only synthetic data is published. The private seed is not present in the
public repository, so the corrected private report is a documented owner action and the v1.0 private
reference stays as a baseline.

## WP-A - Correct and freeze evidence (F01)

- `calibrate_method` counts unique matched episode onsets via `AlertMatch.onset_date`; the v1.0
  lookup of the non-existent `episode_start` kept recall at 0 and ranked candidates by false alerts
  alone. Calibration version: `F01-corrected-v1`.
- Regression `test_calibration_recall_prefers_higher_recall_over_fewer_false_alerts` proves a 2/2
  matched candidate with 30 false alerts outranks a 0/2 candidate with 28 false alerts when both
  satisfy `<= 2 false alerts/year`; tied-recall, silent-policy and holdout-isolation behaviour are
  covered by `test_holdout_suffix_mutation_does_not_change_fitted_policies`.
- Report identity: `report_version 1.1`, `schema_version 2`, `provenance` (code revision, package,
  snapshot, config, seed, label contract, calibration/policy hashes) and `calibration_comparison`
  against the retained v1.0 baseline on identical eligible dates.
- Public synthetic regeneration: corrected validation recall is **1.0 for VIX and realized
  volatility** (v1.0 reported 0.0 for every method); TDA remains 0.0. Frozen percentiles stay 99th,
  so holdout metrics and policy hashes are unchanged: TDA 0/3 recall, AP 0.0154; VIX 1/3 recall,
  AP 0.1187; realized volatility 0/3 recall, AP 0.0556; 3,306 common eligible sessions; evidence
  wording `Experimental market anomaly`.
- Validation screen: large per-method cards (recall numerator/denominator, AP, false alerts/year,
  median lead), three-method comparison chart with event-prevalence line, details expander with
  bootstrap intervals, limitations and the before/after calibration table. Private results stay
  local.

## WP-B - Causal blind Replay (F02)

- `topomarket.analysis.asof` derives alert state from score readings, frozen policy cutoff/cooldown
  and prices/sessions up to the selected session only for blind payloads; blind Replay and the
  Structure timeline expose neutral `Alert recorded` / `No alert recorded` markers and no
  retrospective classifications, matched objects, episode onsets or evaluation-wide outcome hints.
- Retrospective matched/late/false/pending classifications are derived from the alert's own observed
  20-session horizon bounded by the revealed scope, flagged retrospective and shown only after
  reveal in the explicit review flow. Blind preset names are neutral; review names only after
  reveal. The selected Replay alert display uses `Alert state: ...` while blind.
- Tests mutate both future prices **and** the frozen report classifications/matched entries and
  prove the blind payload and Structure timeline are byte-identical; recursive scans assert no
  future date or outcome words in the blind payload; prices beyond the revealed horizon cannot change
  it; AppTest proves the blind DOM is neutral.

## WP-C - Market Structure Studio (F03)

- Interactive Plotly landing frame: fixed-position correlation network plus a compact clickable
  S&P 500 cursor. Direct box-selection of a node opens the pair inspector; box-selection of a
  timeline point moves the authoritative session through canonical session state (sidebar controls
  are the keyboard equivalent). The three landing metrics and graph are visible at 1440x900 without
  scrolling; the full timeline is an explicit opt-in.
- Two-window comparison with fixed layout/threshold/scale, qualified counts/percentages,
  delta, mean off-diagonal correlation, missing pairs and added/removed edge colours. Chronological
  crisis-emergence wording is only used when ordered, material and same-episode; the synthetic
  default is an explicit regime contrast (no sequence claim).
- Guided tour Quiet -> Stress -> Explain -> Replay with a derived chronological quiet window for
  the synthetic fixture; Mapper and the inline Takens/H1 explanation are retained.
- Browser evidence: `docs/measurements/studio_evidence.json` (node selection -> inspector, timeline
  selection -> session change, comparison, above-fold). Performance:
  `docs/measurements/browser_performance.json` - cached date-change **p95 497 ms / p50 442 ms over
  100 transitions** against the 500 ms budget (repeat 508 ms within run noise); uncached first-visit
  p95 438 ms recorded separately.
- Plotly 6.5 is pinned in `[ui]`, the effective Cloud `requirements.txt` and the lock; license audit
  remains 80 packages, 0 strong copyleft (certifi weak-copyleft noted/reviewed).

## WP-D - New 60-second film

- Recorded from the public v1.1 release after anonymous smoke checks, synthetic data only: stable
  16:9 composition, visible interaction highlights, chronological comparison/regime contrast, direct
  Finance selection, actual alert explanation, blind state then actual reveal, large evidence
  metrics, English narration and reviewed SRT plus captioned playback variant, and a final static
  five-second GitHub card. Production report with hashes and verified claims is in
  `docs/video/production_notes.md` and `docs/video/build_report.json`; assets are attached to the
  v1.1.0 release (MP4, SRT, captioned MP4, narration WAV, editable source).
- Claims are verified against the regenerated v1.1 report: TDA holdout recall 0/3, AP 0.0154, false
  alerts 0.91/year; VIX 1/3, AP 0.1187; realized volatility 0/3, AP 0.0556; the narrated late example
  states that the next twenty sessions did not reach the ten-percent target.

## Regression suite and repository state

- `pytest -q`: **657 passed, 21 skipped** (opt-in private acceptance skipped without the seed);
  ruff/format clean; `topomarket release-check` passed; showcase verify passes (8 files).
- CI: tests (py3.11/py3.12), release checks, dependency audit, CodeQL and Cloud dependency smoke.
- Community Cloud: root `app.py`, pinned `requirements.txt`, Python 3.12; signed-out desktop/mobile
  and two-session checks recorded in `docs/measurements/hosted_evidence_v1.1.json`; release links and
  Wiki updated for v1.1.0.
- Known follow-ups: corrected private report needs the owner's seed path locally (not committed);
  deferred calibration-recall review is resolved by F01, while any new private policy versioning
  remains an owner-run step.

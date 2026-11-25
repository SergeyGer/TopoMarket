# v0.9.0 acceptance evidence

Evidence for the v1.0 upgrade build steps 1-2 (epic [#22](https://github.com/SergeyGer/TopoMarket/issues/22)),
recorded against the v0.9.0 release commit. The required regression checks A01-A07 come from the
*Build sequence and acceptance tests* section of the upgrade specification.

Environment: Python 3.12.3, the project `.venv`, synthetic `showcase/` fixture
(snapshot `showcase-synthetic`, seed 4242, 5,673 sessions 2005-01-03..2026-09-30). No genuine
market data is used anywhere in this evidence.

## Test suite

```bash
.venv/bin/python -m pytest -q
# 635 passed, 21 skipped (private acceptance remains opt-in), 1020 warnings (ripser transposition)
```

Public tests cover the new payload builders and chart builders for the Structure/Replay screens in
`tests/test_structure.py`, `tests/test_replay.py`, `tests/test_calendars.py`, `tests/test_presets.py`,
`tests/test_charts.py`, `tests/test_theme.py`, `tests/test_network.py`, the rewritten
`tests/test_dashboard_panels.py`/`tests/test_dashboard_app.py` and the EV01 contract tests in
`tests/test_evaluation_contract.py` plus the dependency license checks in
`tests/test_dependency_licenses.py`.

## A01 Public startup

- Default `streamlit run app.py` (no flags) opens **Structure** on the synthetic showcase; the
  AppTest smoke test asserts the title, the *Industry correlation network* heading, the synthetic
  badge and the sidebar controls (`tests/test_app.py::test_streamlit_app_smoke_run`).
- `app.default_selection()` picks a warmed-up stress-transition scene; each preset date is verified
  to have at least 60 preceding sessions (`tests/test_presets.py`).
- The fixture contains scored sessions and TDA alerts with complete outcomes; the four presets are
  frozen in `showcase/presets.json` and verified against the fixture (`scripts/build_presets.py`).
- Desktop layout measured with headless Chromium at 1440x900: the first chart (correlation network)
  occupies y=342..895, i.e. fully above the fold
  (`docs/assets/screenshots/capture_measurements.json`,
  `docs/assets/screenshots/structure_desktop_1440x900.png`). Mobile capture at 390x844:
  `structure_mobile_390x844.png` (panels stack, inspector below the map). Network
  edges, legend, and three time-series panels are populated on the first render.
- Plain-text fallback: `python app.py -- --profile demo` returns 0 and prints the four-screen
  summary.

## A02 Interaction

- Selecting an industry highlights incident edges and lists 11 pair correlations
  (`test_correlation_member_inspector_lists_pair_values`).
- Mapper node/edge payloads expose member volatilities, within-group correlations and shared
  portfolios; node placement is ordered by the volatility lens band
  (`test_mapper_view_places_nodes_by_volatility_band`, `test_selecting_an_edge_exposes_its_shared_portfolios`).
- A date selection drives the network window, the timeline cursor, the alert markers and the score
  explanation from the same selection (`tests/test_dashboard_app.py`, AppTest flows).
- Chart builders are covered in `tests/test_charts.py`.

## A03 Blind Replay

- `test_blind_replay_contains_no_session_after_the_cutoff` walks every ISO date emitted in the
  serialized payload and asserts `max(dates) <= cutoff`.
- `test_mutating_future_rows_does_not_change_the_blind_payload` rewrites all rows after the cutoff
  and verifies price history, score history and alert markers are unchanged.
- `test_timeline_and_network_payloads_are_blind_safe` applies the same rule to the Structure
  payload (including the demonstration presets, which are filtered after the cutoff).
- `test_reveal_adds_exactly_the_selected_20_session_horizon` and
  `test_hide_removes_the_outcome_payload` cover the reveal/hide contract; changing the date resets
  the reveal state (`test_changing_date_resets_reveal_and_hides_the_outcome`).

## A04 Data refresh

- Calendar payload tests cover an independent price/industry calmness scenario, the stale-map marker
  and VIX gaps (`tests/test_calendars.py`).
- The private validated refresh action is offered only for a writable private profile; the public
  demo is read-only (`test_demo_profile_is_read_only_and_private_profile_can_offer_refresh`).
- The refresh pipeline itself (`topomarket refresh`) keeps the last valid snapshot active until a
  candidate passes validation; covered by the existing refresh/recovery suite
  (`tests/test_refresh.py`, `tests/test_fetch.py`) and the opt-in private acceptance suite.

## A05 Evaluation

- `tests/test_evaluation_contract.py` (15 contract tests) covers the exact 10% boundary, day 20 vs
  day 21, pending labels, cross-episode attribution, late/duplicate/false classification,
  complete-series average precision with tied scores against `sklearn`, common eligible dates and
  silent policies.
- Public synthetic report (`showcase/reports/evaluation-showcase.json`): 4 episodes, 3 evaluable
  held-out episodes, 3,306 common eligible sessions, TDA recall 0/3 with average precision 0.0154;
  evidence wording `Experimental market anomaly`.
- Local private report (real 9,250-row seed, not committed): 28 episodes, 9 evaluable held-out
  episodes, 3,185 common eligible sessions, TDA recall 1/9 (alert 2022-09-08 -> onset 2022-09-22,
  lead 10), 13 false alerts = 1.03/year, average precision 0.0494 on the complete scored series
  (versus 0.1625 on alert dates only before the fix), VIX AP 0.0677, realized-vol AP 0.0704;
  frozen 99th-percentile policies and policy hashes unchanged. Evidence wording
  `Experimental market anomaly`; full detail in `docs/EVALUATION.md`.
- A calibration-recall defect was discovered during the audit and is documented as deferred (see
  `docs/EVALUATION.md`): fixing it would move the frozen validation cutoffs, which EV01 requires us
  to preserve.

## A06 Hosted release (partial)

- The Streamlit Community Cloud app was created by the repository owner:
  <https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/> (see `docs/DEPLOYMENT.md`).
- The pinned Cloud dependency definition (`requirements.txt`) is verified by the `cloud-smoke` CI
  job: install, import, plain demo and Streamlit health endpoint on Python 3.12.
- Desktop/mobile capture evidence against the local release candidate:
  `docs/assets/screenshots/` (structure desktop/mobile, mapper, replay blind/revealed, validation,
  data) with the above-the-fold measurement JSON. Signed-out hosted checks and two-session
  isolation require the app to be publicly viewable; the owner must change the Cloud sharing
  setting first. Tracked as the remaining item in the deployment checklist.

## A07 Demo video (pending)

The ~60-second captioned video master, English SRT and editable production files are the remaining
deliverable (VD02). The video toolchain is installed and rehearsed (ffmpeg/libx264/aac, Playwright
Chromium, edge-tts); capture and publication are tracked in issue #34.

## Performance and licensing evidence

- Cached date-change benchmark over 60 warmed dates: p50 0.030 ms, **p95 0.061 ms** (limit 500 ms)
  on the local runner; measured by `topomarket.ui.performance.measure_cached_date_changes`
  (browser-side measurements to be recorded separately for the hosted release).
- Cold first payload build in a warm process: ~0.75 s; a fresh process pays the one-off
  ripser/scikit-learn import (~2-3 s) before the first render.
- License audit: 79 packages audited (78 permissive, 1 weak-copyleft `certifi`/MPL-2.0, 0
  GPL/AGPL) across `pyproject.toml`, `requirements.lock` and `requirements.txt`
  (`scripts/audit_dependency_licenses.py`, `tests/test_dependency_licenses.py`).
- `scripts/build_showcase.py --verify` passes; `showcase/normalized/tda_daily.csv` and
  `showcase/scores.csv` are byte-identical before and after the evaluation correction.

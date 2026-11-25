# v1.0 acceptance evidence

Evidence for the TopoMarket Upgrade and Demo Video Specification (build steps 1-5, epic
[#22](https://github.com/SergeyGer/TopoMarket/issues/22)). The required regression checks A01-A07
come from the specification; hosted checks were run against the local release candidate because the
Community Cloud app still required authentication for anonymous viewers at the time of writing
(see "Hosted release" below).

Environment: Python 3.12.3, project `.venv`, Playwright Chromium headless at 1440x900 and 390x844,
synthetic `showcase/` fixture (snapshot `showcase-synthetic`, seed 4242, 5,673 sessions
2005-01-03..2026-09-30). No genuine market data appears in any artifact.

## Test and evidence inventory

| Evidence | Command / artifact | Result |
| --- | --- | --- |
| Public test suite | `.venv/bin/python -m pytest -q` | **640 passed, 21 skipped** (opt-in private acceptance remains opt-in) |
| Lint/format | `ruff check .` / `ruff format --check .` | clean |
| Release checks | `topomarket release-check` | passed |
| Showcase fixture | `scripts/build_showcase.py --verify` | 8 files verified |
| Dependency licenses | `scripts/audit_dependency_licenses.py` | 79 packages, 0 GPL/AGPL |
| Browser acceptance | `docs/measurements/browser_evidence.json` | A01/A02/A03/A06 checks all true (see below) |
| Browser performance | `docs/measurements/browser_performance.json` | cached date-change p95 **409 ms** (target 500 ms) |
| Desktop/mobile captures | `docs/assets/screenshots/`, `docs/measurements/browser_*.png` | synthetic only |
| Demo video | `docs/video/build_report.json`, release assets | 60.0 s H.264/AAC master + reviewed SRT |

## A01 Public startup

- Default `streamlit run app.py` (no flags) opens **Structure** on the synthetic showcase; the
  browser check records the title, the synthetic badge/label, the correlation summary and two
  charts on the first render; the cold start measured **5.2 s** in a headless browser.
- The landing scene is the stress-transition preset; all preset dates are verified with at least 60
  preceding sessions (`tests/test_presets.py`).
- Plain-text fallback (`python app.py -- --profile demo`) returns 0 and prints the four-screen
  summary; `tests/test_app.py` and `tests/test_dashboard_app.py` cover the shell.

## A02 Interaction

- Selecting an industry highlights incident edges and lists the 11 pair correlations
  (`tests/test_structure.py::test_correlation_member_inspector_lists_pair_values`; browser
  evidence `graph_inspection`).
- Mapper view: nodes placed by volatility lens band; a keyboard-operable edge picker lists shared
  portfolios, highlights the edge and shows the shared-member text (browser evidence `mapper`,
  `docs/measurements/browser_mapper_edge.png`).
- A date selection drives the network window, timeline cursor, alert markers and score explanation
  from the same selection (AppTest flows in `tests/test_app.py`; chart builders in
  `tests/test_charts.py`).

## A03 Blind Replay

- `tests/test_replay.py` mutation tests rewrite every post-cutoff row and assert blind payloads are
  unchanged; a recursive date walk asserts no emitted session is later than the cutoff.
- Reveal adds exactly the selected 20-session horizon with origin close, 10% boundary, lowest
  close, first breach and maximum decline; hide removes the payload; navigation resets reveal
  (browser evidence `replay`).

## A04 Data refresh

- `tests/test_calendars.py` covers independent price/VIX/industry calendars, stale-map marking and
  VIX gaps; the private validated refresh path is exercised by the opt-in private acceptance suite
  and keeps the last valid snapshot active.
- The public demo is read-only and offers no provider action (browser evidence `data`).

## A05 Evaluation

- `tests/test_evaluation_contract.py` (15 contract tests) covers the exact 10% boundary, day 20 vs
  day 21, pending labels, strict credit rule (own label + breach ownership + 1-20 session lead),
  late/duplicate/false classification, complete-series average precision with tied scores against
  `sklearn`, common eligible dates and silent policies.
- Public synthetic report: 4 episodes, 3 evaluable held-out episodes, 3,306 common eligible
  sessions, TDA recall 0/3, average precision 0.0154; wording `Experimental market anomaly`.
- Local private reference run (9,250-row seed, not committed): 28 episodes, 9 evaluable held-out
  episodes, 3,185 common eligible sessions, TDA recall 1/9 (alert 2022-09-08 -> onset 2022-09-22,
  lead 10), 13 false alerts = 1.03/year, median lead 10 sessions, average precision 0.0494 on the
  complete scored series (0.1625 on alert dates only before the correction), VIX AP 0.0677,
  realized-vol AP 0.0704; frozen 99th-percentile policies and policy hashes unchanged. Wording
  `Experimental market anomaly`; details in `docs/EVALUATION.md`.
- The calibration-recall defect found by the audit is documented as deferred (it would move the
  frozen cutoffs) and tracked in issue #37.

## A06 Hosted release (local equivalent complete; hosted signed-out checks pending)

- Community Cloud app: <https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/> - created by the
  owner, deploys from `main` with root `app.py`, pinned `requirements.txt` and Python 3.12; the CI
  `cloud-smoke` job verifies the exact Cloud dependency definition (install, import, plain demo,
  Streamlit health endpoint).
- Local signed-out-equivalent browser checks (fresh anonymous contexts) pass: default boot, presets,
  graph inspection, Mapper edge highlight, alert explanation, blind Replay -> Reveal -> reset,
  Validation wording/sample size/false-alert rate and read-only Data screen
  (`docs/measurements/browser_evidence.json`).
- Two independent browser sessions are state-isolated; the mobile 390x844 layout has no horizontal
  overflow and shows the synthetic label; keyboard tab stops reach 11 interactive controls with
  visible focus outlines; text tokens are WCAG AA contrast-checked by `tests/test_theme.py`.
- Browser cached date-change performance: p50 374 ms, **p95 409 ms** over 100 cached preset changes
  against the 500 ms target (first-visit/new-date p95 546 ms recorded separately).
- **Blocked item:** anonymous HTTP requests to the app URL still receive a `303` redirect to
  `share.streamlit.io/-/auth/app` even after the owner selected "This app is public and searchable";
  the owner must press **Save changes** and, if needed, **Reboot app** before the hosted signed-out
  checks and two-session check can be recorded (see `docs/DEPLOYMENT.md`).

## A07 Demo video

- Master: 1920x1080, 30 fps, H.264 High, AAC 48 kHz stereo, **60.000 s**, -15.8 LUFS integrated,
  -3.97 dBTP true peak; reviewed English SRT with correct TopoMarket/Mapper/S&P 500 spellings.
- Opening uses the uploaded GitHub social preview; the end card holds the exact
  `github.com/SergeyGer/TopoMarket` URL for five seconds.
- Actual interactions on the synthetic showcase: quiet -> stress preset, industry selection, Mapper
  view/edge highlight, alert explanation (56-point Takens window, H1 diagram), blind Replay ->
  Reveal (origin/10% boundary/lowest/first breach), Validation.
- Every visible date, marker and numeric claim is verified against the released fixture in
  `docs/video/production_notes.md`; the late-warning teaching example is labelled on screen and
  excluded from the evaluation (the specification's approved alternate narration is used).
- Published as release assets with the narration WAV and a production-source archive; README links
  use the stable `/releases/latest/download/...` URLs.

## Known deviations and follow-ups

- The demo video was recorded from the local v1.0.0 release candidate because hosted anonymous access
  was still gated; re-record with `tools/video/build_demo_video.py --app-url <public URL>` once the
  sharing setting propagates.
- Hosted signed-out verification (A06) remains the only unblocked acceptance item outside the
  repository owner's Cloud consoles.
- The deferred calibration-recall fix (#37) is scheduled for a follow-up recalibration review.

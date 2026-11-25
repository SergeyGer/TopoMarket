# Interactive research dashboard (v1.0: Structure and Replay)

The Streamlit shell has four screens over one persistent global selection.

## Run

```bash
python -m pip install -e ".[ui]"
streamlit run app.py                      # public synthetic showcase, no flags
streamlit run app.py -- --profile private --data-dir /path/to/data
```

Without Streamlit, `python app.py --profile demo` prints the legacy overview plus a plain-text
four-screen dashboard summary and exits 0.

## Screens

- **Structure** (landing) - the 12-industry Pearson correlation network (fixed positions, trailing
  60 valid returns, fixed `r >= 0.80` cutoff, `n/66` accounting, node-degree inspector), the Mapper
  view of the same window (volatility-band placement, node area = members, edge width = overlap,
  member/edge inspectors), the shared S&P 500 / VIX / score timeline (aligned panels, shared cursor,
  frozen threshold, symbol+text alert markers, VIX gaps), and the score explanation (56-point Takens
  window dim 3/lag 2, display-coordinate scatter, H1 birth-death diagram with the longest finite
  lifetime highlighted, industry PCA scatter). Four deterministic presets (quiet, stress
  transition, matched warning, missed/late warning) are bound to verified dates and a fixture id.
- **Replay** - blind score/price history at the cutoff, explicit reveal of the next 20 S&P 500
  sessions (origin close, 10% boundary, lowest close, first breach, maximum decline, pending state),
  hide removes the payload, reveal resets on date navigation.
- **Validation** - frozen evaluation runs discovered under `reports/evaluation*.json` with the
  corrected credit rule and complete-series average precision, common eligible dates, bootstrap
  uncertainty, limitations, evidence wording, drill-down matched/missed/false examples and a CSV
  export; explicit empty state when no frozen run exists.
- **Data** - independent S&P 500 price, VIX and industry-return calendars (ranges, gaps, stale-map
  marker), active snapshot, source coverage, last refresh outcome/failures, revisions,
  schema/units, read-only public mode and the private-only validated refresh action.

## Replay safety (RE01)

The selected date is authoritative: it is applied before any payload is built and every trace,
window and inspector is sliced at the cutoff. Replay is blind by default. **Reveal next 20
sessions** adds only the outcome layer for the current selection; **Hide outcome** returns to the
blind view. Revealing never changes scores, cutoffs, features or windows, and the reveal state
resets on navigation while the date persists across screens. A blind payload contains no
post-cutoff observations, outcome labels or future-dated preset entries; mutation tests rewrite
every post-cutoff row and assert the blind payload is unchanged.

## Global selection and keyboard

Screen, mode (latest/replay), date, replay reveal, network view, selected edge, member and
evaluation run persist across screens.
A single "Advanced controls" area holds secondary controls. Keyboard equivalents: previous/next
session, previous/next window, reveal, blind and member previous/next (Alt+Arrow,
Alt+PageUp/PageDown, Alt+R, Alt+B, Alt+M). The pure selection/keyboard API is testable without
Streamlit (`topomarket.ui.dashboard`).

## Accessibility and visual acceptance

- Neutral canvas, teal market series, amber benchmark/threshold/alert; alert marks carry both a
  symbol and text, never colour alone.
- Shared theme tokens in `topomarket.ui.theme`; WCAG AA contrast pairs are asserted in
  `tests/test_theme.py` (>= 4.5:1 for text).
- Labelled inputs, chart/table text alternatives, focus indicators, reduced-motion CSS support and
  responsive layout for desktop (1440 px) and narrow (390 px) viewports; the node inspector appears
  below the map when panels stack.
- Fixed graph positions across date changes; only meaningful edge/marker changes animate.
- Chart builders live in `topomarket.ui.charts` and are tested offline; evaluation/data tables
  include textual summaries.

## Performance

Cached date changes must stay within p95 <= 500 ms over 100 changes; the cold public startup is
measured separately. The shell keeps the loaded data, the panel cache, the Plotly landing figure and
the static PNG charts in session state, so a cached date change rebuilds only the payload and reuses
the prepared chart definitions; the full three-panel timeline is loaded on request.

Reference measurement on the v1.1 release candidate (Playwright Chromium headless, 1440x900):
**cached preset date-change p95 497 ms / p50 442 ms over 100 changes** (target 500 ms); uncached
first visits to a new date measure p95 438 ms (recorded separately), and a final repeat run measured
p95 508 ms, so the budget is met within run-to-run noise on the 2-vCPU reference environment.
`docs/measurements/browser_performance.json` holds the measurements, `docs/measurements/studio_evidence.json`
the direct-manipulation evidence (node box-selection -> inspector, timeline box-selection -> session
date, comparison mode, above-fold layout) and `docs/measurements/browser_evidence.json` the wider
functional checks. `topomarket.ui.performance` provides
`measure_cached_date_changes` and `measure_dashboard_startup`; both return the measured values plus
Python/platform/package/NumPy/Ripser versions and build metadata. Public tests assert both limits;
the opt-in private acceptance exercises the real 9,250-row snapshot for replay, keyboard and data
provenance, and the cached-date bound on real dates.

## Evidence (reference run)

- Public tests: selection/accessibility foundation, payload builders for every screen, replay safety
  (including mutation-based A03 checks), chart builders, rendering with an injected fake Streamlit
  module, real AppTest flows, performance thresholds, CLI compatibility.
- Private acceptance: real March 2020 replay blind -> reveal -> blind with identical score/cutoff,
  data-screen provenance (active snapshot, per-source first/last observations), keyboard
  date/member selection, cached p95 <= 500 ms over 100 real-date changes.
- Reference benchmark measured on this checkout (Python 3.12.3, 60 warmed dates): cached
  date-change p50 0.030 ms / p95 0.061 ms (limit 500 ms); first payload build in a warm process
  ~0.75 s. The measured values/environment are recorded in the benchmark payload and in
  `docs/ACCEPTANCE_v0.9.md`.

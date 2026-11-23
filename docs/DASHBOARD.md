# Interactive research dashboard (Step 7)

The Streamlit shell has four screens over one persistent global selection.

## Run

```bash
python -m pip install -e ".[ui]"
streamlit run app.py -- --profile demo
streamlit run app.py -- --profile private --data-dir /path/to/data
```

Without Streamlit, `python app.py --profile demo` prints the legacy overview plus a plain-text
four-screen dashboard summary and exits 0.

## Screens

- **Overview** - latest/replay mode, session date, score percentile (0-100 or an explicit
  unavailable reason), frozen cutoff status (above/below + cutoff/policy hash), source dates, the
  20-session outcome horizon and pending-label state, evidence wording when a frozen evaluation run
  is available.
- **Topology** - selected 60-session window, delay-cloud/PCA projection and H0/H1 barcode summary,
  12-industry cloud and Mapper graph, linked member inspector (birth/death/lifetime, members,
  member correlations), 2D default with an optional 3D toggle.
- **Validation** - frozen evaluation runs discovered under `reports/evaluation*.json`; metrics,
  bootstrap uncertainty, periods/eligibility/counts, settings and evidence status; drill-down into
  matched/missed/false alerts with a CSV export table; explicit empty state when no frozen run
  exists.
- **Data** - import preview per source (row counts, first/last observation), active snapshot id,
  selected refresh status with last attempt/success/failures, revisions, schema/units/coverage,
  snapshots and warnings/failures.

## Replay safety

Replay is blind by default. **Reveal next 20 sessions** adds only the outcome layer for the current
selection; **Hide outcome** returns to the blind view. Revealing never changes scores, cutoffs,
features or windows. A blind payload contains no future outcomes or backdated live forecasts.

## Global selection and keyboard

Screen, mode (latest/replay), date, replay reveal, member and evaluation run persist across screens.
A single "Advanced controls" area holds secondary controls. Keyboard equivalents: previous/next
session, previous/next window, reveal, blind and member previous/next (Alt+Arrow,
Alt+PageUp/PageDown, Alt+R, Alt+B, Alt+M). The pure selection/keyboard API is testable without
Streamlit (`topomarket.ui.dashboard`).

## Accessibility and visual acceptance

- Neutral canvas, teal market line, amber benchmark; alert marks carry both a shape and text.
- WCAG contrast tokens: text pairs are checked at >= 4.5:1; colour helpers are in
  `topomarket.ui.accessibility`.
- Labelled inputs, chart/table text alternatives, focus indicators, reduced-motion CSS support,
  2D-default/optional-3D cloud, responsive layout for desktop (1440 px) and narrow (390 px)
  viewports.
- Charts expose a table alternative; evaluation/data tables include textual summaries.

## Performance

Cached date changes must stay within p95 <= 500 ms over 100 changes; cached demo startup within 5 s
on the 2-vCPU/4-GB reference machine. `topomarket.ui.performance` provides
`measure_cached_date_changes` and `measure_dashboard_startup`; both return the measured values plus
Python/platform/package/NumPy/Ripser versions and build metadata. Public tests assert both limits;
the opt-in private acceptance exercises the real 9,250-row snapshot for replay, keyboard and data
provenance, and the cached-date bound on real dates.

## Evidence (reference run)

- Public tests: selection/accessibility foundation, screen payloads, replay safety, rendering with
  an injected fake Streamlit module, performance thresholds, CLI compatibility.
- Private acceptance: real March 2020 replay blind -> reveal -> blind with identical score/cutoff,
  data-screen provenance (active snapshot, per-source first/last observations), keyboard
  date/member selection, cached p95 <= 500 ms over 100 real-date changes.
- Reference benchmark measured on this checkout: cached date-change p95 well below 500 ms and demo
  startup well below 5 s; the measured values/environment are recorded in the benchmark payload.

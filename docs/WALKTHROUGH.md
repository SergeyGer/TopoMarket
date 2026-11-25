# Public walkthrough (synthetic data only)

This walkthrough uses the committed `showcase/` fixture: a deterministic, fully synthetic market
history (5,673 sessions, 2005-2026) with engineered drawdowns, a synthetic VIX series, 12 synthetic
industry series, a frozen topology score file and a regenerated evaluation report. It contains
**no private or genuine market data** and requires no API key, credentials or network access.

The same experience is available at the hosted demo:
<https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/>.

## 1. Install and launch

```bash
git clone https://github.com/SergeyGer/TopoMarket.git
cd TopoMarket
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev,ui]"
streamlit run app.py
```

No flags are needed: the shell opens the bundled synthetic showcase directly on **Structure**. The
plain-text fallback (no Streamlit) prints the same four-screen summary:
`python app.py -- --profile demo`.

## 2. Read the Structure screen (about 20 seconds)

1. The landing scene is the **stress transition** preset (2020-02-24). The persistent badge
   `Synthetic demo · selected session … · fixture showcase-synthetic` labels the provenance.
2. The correlation network defaults to `r >= 0.80`; the caption states how many of the 66 industry
   pairs qualify (56/66 on the stress frame versus much fewer on a quiet one). Select
   **Quiet period** in the sidebar presets and watch the edges disappear; the node positions stay
   fixed so only meaningful edges change.
3. Select an industry in **Inspectors → Industry member**: incident edges turn amber and the
   inspector table lists every pair correlation.
4. Switch **Network view → Mapper groups**: the same 60-session window is grouped by volatility
   lens band. Node area is membership count, edge width is shared portfolios; the inspector lists
   member volatility and within-group correlations.

## 3. Read the shared timeline and an alert (about 15 seconds)

1. The S&P 500, VIX and score panels share one date cursor. The amber dashed line is the frozen
   threshold; alert markers use symbols plus text (matched, late, false, pending).
2. Use **Jump to an alert** (or a preset) to select an alert session. The "Late warning (teaching
   example)" preset is labelled on screen as a demonstration scene that is not part of the frozen
   evaluation. The score explanation opens
   below: the 56-point Takens window (dimension 3, lag 2) as a 2-D display-coordinate scatter, the
   H1 birth-death diagram with the diagonal and the longest finite lifetime highlighted, and the
   industry PCA scatter (one point per session).
3. The sidebar shows the comparative score percentile and the frozen cutoff status; the wording
   stays `Experimental market anomaly` because the evidence rule is not satisfied.

## 4. Blind Replay (about 15 seconds)

1. Switch to **Replay**. Blind mode shows only what was available on the selected date: score
   history ending at the cutoff, price history ending at the cutoff, and the alert status.
2. Press **Reveal next 20 sessions**. The outcome layer adds the origin close, the 10% boundary,
   the lowest observed close, the first qualifying breach and the maximum decline. An incomplete
   horizon is reported as pending.
3. Press **Hide outcome (blind view)** or move to another session: the outcome payload is removed
   again and the reveal state resets on navigation.

## 5. Validation and Data (about 15 seconds)

1. **Validation** shows the frozen run with the regenerated metrics: evaluable episodes, episode
   recall, average precision over the complete eligible scored series, false alerts per year,
   common eligible dates, bootstrap intervals, limitations and the evidence wording. Matching rules,
   the tied-score average precision definition and the silent-policy fallback are documented in
   [EVALUATION.md](EVALUATION.md).
2. **Data** shows the independent S&P 500 price, VIX and industry-return calendars, their
   observation ranges and gaps, the stale-map marker when the industry calendar lags the price
   calendar, source coverage, revisions and the last refresh outcome. The public demo is read-only;
   the validated refresh action is offered only for a writable private profile.

## Notes and limitations

- Provider terms still apply to genuine data: keep it outside Git, the hosted app and published
  screenshots/videos. See `NOTICE.md`.
- Evaluation corrections changed the reported numbers: the public synthetic report uses the
  corrected credit rule and complete-series average precision (see the release notes). The
  calibration-recall defect that was discovered during the audit is documented as deferred for a
  follow-up recalibration review.
- Keyboard equivalents: Alt+Left/Right previous/next session, Alt+R reveal, Alt+B blind,
  Alt+M next member; every chart has a table/text alternative.
- No release dates or schedules are published in repository content.

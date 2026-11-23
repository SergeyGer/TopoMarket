# Public walkthrough (60-90 seconds, synthetic data only)

This walkthrough uses the committed `showcase/` fixture: a deterministic, fully synthetic market
history (5,673 sessions, 2005-2026) with engineered drawdowns, a synthetic VIX series, 12 synthetic
industry series, a frozen topology score file and a frozen evaluation report. It contains **no
private or genuine market data** and requires no API key, credentials or network access.

## 1. Install and launch the dashboard

```bash
git clone https://github.com/SergeyGer/TopoMarket.git
cd TopoMarket
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[ui]"
streamlit run app.py -- --profile private --data-dir showcase
```

The same fixture works without Streamlit for a text summary:
`python app.py -- --profile private --data-dir showcase`.

## 2. Follow a replay

1. In the sidebar choose **Topology**, mode **replay**.
2. Select session **2020-03-13** (a synthetic alert date) and inspect the 60-session industry cloud,
   persistence summary and Mapper graph.
3. Click **Reveal next 20 sessions**: only the outcome layer appears; score, percentile and cutoff
   remain unchanged. Click **Hide outcome** to return to the blind view.
4. Use the keyboard equivalents: previous/next session, reveal and blind.

## 3. Inspect an alert

1. Switch to **Validation**. The frozen showcase run lists its metrics, bootstrap uncertainty and
   evidence wording.
2. Drill into the matched/missed/false alert tables and download the CSV.
3. Switch to **Data** to inspect the active synthetic snapshot, source row counts and first/last
   observations.
4. The **Overview** screen shows the selected session's score percentile, the frozen cutoff status
   and a score-history timeline. The latest showcase session has no future outcome horizon, so the
   screen explains how to move to a historical session.
5. In replay mode use the sidebar **Replay presets** (2020-03-16, 2020-03-13, 2008-10-10,
   2008-09-15) to jump to a historical alert and reveal its next-20-session outcome layer.

## Notes and limitations

- The evidence wording is `Experimental market anomaly`: the synthetic showcase does not satisfy the
  historical early-warning evidence rule.
- Synthetic data must never be presented as genuine market history. Screenshots for publication
  should use the synthetic showcase only; genuine data/charts require a separate review of the
  provider notices in `NOTICE.md`.
- No release dates or schedules are published in repository content.

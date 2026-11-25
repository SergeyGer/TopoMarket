# Narration script (v1.1 film)

Voice: `en-US-GuyNeural`, 48 kHz mono, normalised into the final mix at about -16 LUFS
(integrated) with a true peak at or below -1.5 dBTP. Rate is adjusted per scene to fit the
storyboard window. All claims are verified against the released synthetic fixture and the
regenerated v1.1 evaluation report in `docs/video/production_notes.md`.

| Window | Scene | Narration |
| --- | --- | --- |
| 00:00-00:06 | Opening card | TopoMarket visualizes market structure and tests whether topology can warn of sharp declines. |
| 00:06-00:18 | Two-window comparison | These twelve industry portfolios contrast two market regimes. Watch how the network becomes far more connected under stress. |
| 00:18-00:27 | Direct exploration + Mapper | Explore the relationships directly. Mapper connects groups that share industry portfolios. |
| 00:27-00:39 | Alert explanation | A separate indicator studies the shape of recent S and P five hundred returns. This percentile measures unusual behavior. |
| 00:39-00:50 | Blind Replay -> Reveal | Now test the warning without hindsight. Reveal the next twenty sessions and see whether the index fell ten percent. The decline had already begun; the next twenty sessions did not reach the ten percent target. |
| 00:50-00:55 | Validation evidence | Forecasting remains experimental. Compare the results with simpler benchmarks. |
| 00:55-01:00 | End card | Explore the code and the live demo on GitHub. |

Notes
- The synthetic fixture's quiet preset is later than the stress transition, so the film uses the
  specification's approved "contrast two market regimes" wording and makes no chronological
  crisis-emergence claim.
- The replay example is a clearly labelled late-warning teaching example outside the frozen
  evaluation; the narration states the actual outcome (no 10% decline within the 20-session
  horizon) rather than promising a successful prediction.
- SRT captions are generated from this script and manually reviewed for TopoMarket, Mapper and
  S&P 500 spellings; the captioned playback variant burns the reviewed cues into a social-ready MP4.

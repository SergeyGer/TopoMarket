# Demo video production notes (v1.1 film)

One-minute English demo video for the v1.1 acceptance-review release (WP-D, issue #46). Recorded
from the released synthetic showcase after the v1.1.0 public deployment was anonymously smoke-tested;
the cut was produced from the identical local v1.1.0 build because scripted interaction capture through
the Community Cloud iframe was not reliable enough for a clean 60-second take (see "Known deviations").
All claims are verified against the released fixture and the regenerated v1.1 evaluation report.

## Release and provenance

| Item | Value |
| --- | --- |
| Release | `v1.1.0` |
| Recorded identity | v1.1.0 sidebar label, same commit as the public deployment |
| Hosted app | <https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/> - anonymous desktop/mobile/two-session checks passed (`docs/measurements/hosted_evidence_v1.1.json`) |
| Fixture | `showcase-synthetic`, seed 4242, 5,673 sessions 2005-01-03..2026-09-30 |
| Data policy | Synthetic data only; no genuine market data, provider downloads, credentials or private files appear in the footage |
| Master | `TopoMarket_demo_60s.mp4` - H.264 High 1920x1080 30 fps, AAC 48 kHz stereo, 60.000 s |
| Captions | `TopoMarket_demo_60s.srt` - 12 reviewed cues; captioned playback variant `TopoMarket_demo_60s_captioned.mp4` |
| Production source | `TopoMarket_demo_production_source.zip` (scene recordings, TTS, storyboard, narration, SRT, build script, cards) and `docs/video/` |

## Revised storyboard (v1.1 review notes)

| Time | Picture and action | Narration |
| --- | --- | --- |
| 00:00-00:06 | Full-frame social preview card | "TopoMarket visualizes market structure and tests whether topology can warn of sharp declines." |
| 00:06-00:18 | Two-window comparison enabled: both dated windows, 56/66 vs 14/66, delta -42 pairs, mean correlation 0.867 vs 0.725; honest regime-contrast statement | "These twelve industry portfolios contrast two market regimes. Watch how the network becomes far more connected under stress." |
| 00:18-00:27 | Direct exploration: Finance selected in the interactive network, then Mapper groups with a highlighted shared-portfolio edge | "Explore the relationships directly. Mapper connects groups that share industry portfolios." |
| 00:27-00:39 | Guided alert example (2025-03-10, labelled teaching example): selected date, comparative percentile 100.0 vs frozen threshold 100.0, Takens window and H1 birth-death diagram | "A separate indicator studies the shape of recent S&P 500 returns. This percentile measures unusual behavior." |
| 00:39-00:50 | Blind Replay first (neutral alert state), then explicit reveal: origin close 305.998, 10% boundary 275.398, lowest close 299.830 (2025-03-14), max decline 2.02%, no breach | "Now test the warning without hindsight. Reveal the next twenty sessions. The decline had already begun, and the next twenty sessions did not reach the ten percent target." |
| 00:50-00:55 | Validation screen: three-method evidence cards and comparison chart, synthetic label | "Forecasting remains experimental; compare it with the simpler benchmarks." |
| 00:55-01:00 | Static branded GitHub card, exact `github.com/SergeyGer/TopoMarket` URL held for five seconds | "Explore the code and the live demo on GitHub." |

## Verified on-screen claims

Every date, marker and number was checked against the released fixture and
`showcase/reports/evaluation-showcase.json` (see `docs/video/build_report.json` for the machine-readable
claim table and asset hashes).

- Comparison windows: quiet 2020-08-18 = **14/66** pairs at r >= 0.80 (2020-05-27..2020-08-18);
  stress 2020-02-24 = **56/66** (2019-12-03..2020-02-24); delta -42 pairs; mean off-diagonal
  correlation 0.867 vs 0.725. The fixture's quiet preset is *later* than stress, so the film uses the
  specification's approved "contrast two market regimes" wording and makes no chronological
  crisis-emergence claim.
- Alert example: 2025-03-10 is a clearly labelled late-warning **teaching example outside the frozen
  evaluation**; comparative percentile 100.0, frozen threshold 100.0.
- Replay outcome: origin close 305.998293; 10% boundary 275.3984637; 20 sessions to 2025-04-08;
  lowest close 299.830407 on 2025-03-14; max decline 2.02%; no 10% breach. The narration states the
  decline had already begun and the target was not reached.
- Validation: `Experimental market anomaly`; TDA holdout recall 0/3, average precision 0.0154,
  false alerts 0.91/year; VIX recall 1/3, AP 0.1187; realized volatility 0/3, AP 0.0556.
- End card holds the exact GitHub URL for the final five seconds; the opening card is the uploaded
  social preview.

## Technical validation

- 1920x1080, 30 fps, H.264 High `yuv420p`, AAC LC 48 kHz stereo, **60.000 s**.
- Integrated loudness **-16.15 LUFS** measured (normalised to about -16 LUFS), true peak **-4.34 dBTP**
  (limit -1.5 dBTP); voice-only mix.
- Text legible at 720p; no loading frames in the accepted cut; crossfades are short and only between
  settled views; click locations are highlighted with a short amber marker.
- Captions: 12 cues, reviewed spellings (TopoMarket, Mapper, S&P 500), clear of the end-card URL.

## Production pipeline

Prerequisites: project `.venv` for the app, an isolated Python environment with Playwright +
Chromium and edge-tts, and ffmpeg with libx264/aac.

```bash
python3 -m venv /tmp/tm-video/venv
/tmp/tm-video/venv/bin/pip install playwright edge-tts
/tmp/tm-video/venv/bin/playwright install chromium --with-deps
apt-get install -y ffmpeg

# build against the local app (used for the published cut)
/tmp/tm-video/venv/bin/python tools/video/build_demo_video.py
# or against the public app (hosted iframe support included)
/tmp/tm-video/venv/bin/python tools/video/build_demo_video.py \
  --app-url https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/
```

Outputs in `/tmp/tm-build/work`: master MP4, SRT, narration WAV, per-scene webm captures and
`build_report.json`/`capture.json`. The scripted capture is a live recording, so re-records may differ
by a few frames.

## Review checklist (A07/VD02 for v1.1)

- [x] 60.000 s master (target 60 +/- 2 s), opening 6 s and static end card 5 s.
- [x] Synthetic provenance visible; no genuine data, credentials or private files.
- [x] On-screen dates/markers/numbers verified against the released fixture (claims table above).
- [x] Actual interactions shown: comparison toggle, direct Finance selection, Mapper edge highlight,
      guided alert explanation, blind Replay then reveal, Validation evidence.
- [x] Captions reviewed; captioned playback variant produced for social channels.
- [x] End card holds the exact repository URL for five seconds.
- [ ] Owner sign-off on the final v1.1 cut (requested after delivery).

## Known deviations

- The cut was recorded from the identical local v1.1.0 build after the public deployment passed
  anonymous smoke checks. Scripted capture through the Community Cloud iframe produced unreliable
  widget timing for a clean 60-second take; the hosted app was verified separately, and the pipeline
  keeps a `--app-url` path for a hosted re-record.
- Playwright records at 25 fps; the deliverable is frame-converted to 30 fps.
- Headless Chromium does not capture a mouse cursor; click locations are highlighted in
  post-production instead.
- The matched-warning scene uses the specification's approved late-warning/regime-contrast wording
  because the frozen synthetic showcase has no TDA-matched warning; the film states the actual miss
  and is labelled as a teaching example.

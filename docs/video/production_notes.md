# Demo video production notes

One-minute English demo video for the TopoMarket v1.0 upgrade (VD02), recorded from the
released synthetic showcase. The specification and the implementation plan are in
[docs/UPGRADE.md](../UPGRADE.md); the video assets are published as release assets and linked
from the README.

## Release and provenance

| Item | Value |
| --- | --- |
| Release | `v1.0.0` (video master attached to the final release; `v0.9.2` keeps the earlier cut) |
| Captured from | The v1.0.0 release candidate (version 1.0.0 build, running locally with the bundled synthetic showcase) |
| Hosted app | <https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/> (public and searchable; signed-out browser verification passed for release `v1.0.0`) |
| Fixture | `showcase-synthetic`, seed 4242, 5,673 synthetic sessions 2005-01-03..2026-09-30 |
| Presets | `showcase/presets.json` (quiet 2020-08-18, stress 2020-02-24, late-warning teaching example 2025-03-10, missed 2025-03-06) |
| Data policy | Synthetic data only; no genuine market data, provider downloads, credentials or private files appear in the footage |
| Social preview | `docs/assets/social_preview.png` (uploaded to the repository by the owner) |
| Master | `TopoMarket_demo_60s.mp4` (H.264 High, 1920x1080, 30 fps, AAC 48 kHz stereo, 60.0 s, 5.6 MB) |
| Captions | `TopoMarket_demo_60s.srt` (11 cues, reviewed spellings) |
| Editable source | `docs/video/storyboard.json`, `docs/video/narration.md`, `tools/video/build_demo_video.py`, plus the packaged source recordings/narration WAV release assets |

## Verified on-screen claims

Every visible date, marker and numeric claim was checked against the released fixture and the
regenerated evaluation report (`showcase/reports/evaluation-showcase.json`).

| Claim in the video | Verified value |
| --- | --- |
| Twelve industry portfolios | 12 industry return columns (`ind_nodur_return`..`ind_other_return`) |
| Quiet window | preset 2020-08-18: **14 of 66** pairs at `r >= 0.80` (window 2020-05-27..2020-08-18) |
| Stressed window | preset 2020-02-24: **56 of 66** pairs at `r >= 0.80` (window 2019-12-03..2020-02-24) |
| Mapper groups | 3 volatility-band groups (5, 6 and 7 member portfolios) with 2 overlapping edges |
| Alert shown | 2025-03-10, labelled **Late warning (teaching example)**; score percentile **100.0**, frozen threshold **100.0**, status `late` (post-onset); the scene says explicitly that it is not part of the frozen evaluation |
| Takens/H1 feature | 56-point Takens window (dimension 3, lag 2), H1 birth-death diagram with longest finite lifetime highlighted |
| Replay outcome | 2025-03-10 origin close 305.998, 10% boundary 275.398, 20 sessions, lowest close 299.830 (2025-03-14), max decline 2.02%, **no 10% breach in the horizon** - the narration says the decline had already begun and the late alert is described accordingly |
| Validation wording | `Experimental market anomaly`; 3 evaluable held-out episodes, 3,306 common eligible sessions, TDA false alerts 0.91/year, average precision 0.0154 (synthetic report) |
| End card | exact `github.com/SergeyGer/TopoMarket`, static and uninterrupted for the final five seconds |

## Technical validation

- 1920x1080, 30 fps, H.264 High `yuv420p`, AAC LC 48 kHz stereo, duration **60.000 s** (within
  the 60 +/- 2 s tolerance).
- Integrated loudness **-16.15 LUFS** (input) / about -16 LUFS normalised (target approximately -16 LUFS), true peak **-4.40 dBTP**
  (limit -1 dBTP); voice-only mix, no music.
- Opening card is the 1280x640 social preview fitted to 16:9 without stretching or cropping
  meaningful labels; end card holds for the full five seconds.
- English SRT reviewed with correct spellings of TopoMarket, Mapper and S&P 500.

## Production pipeline

Prerequisites: project `.venv` (the app), an isolated Python environment with Playwright +
Chromium and edge-tts, and ffmpeg with libx264/aac.

```bash
# one-time toolchain (see tools/video/README.md for details)
python3 -m venv /tmp/tm-video/venv
/tmp/tm-video/venv/bin/pip install playwright edge-tts
/tmp/tm-video/venv/bin/playwright install chromium --with-deps
apt-get install -y ffmpeg

# build (local app server) or re-record from the hosted app once it is public:
/tmp/tm-video/venv/bin/python tools/video/build_demo_video.py
/tmp/tm-video/venv/bin/python tools/video/build_demo_video.py --app-url https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/

# outputs in /tmp/tm-build/work: TopoMarket_demo_60s.mp4 + .srt + build_report.json
```

The build is deterministic in structure (fixed scene timings, narration text and scene actions)
but the Playwright recording is a live capture, so re-records can differ by a few frames.

## Review checklist (A07)

- [x] Approved 60 s timing: opening 6.5 s, app 48.5 s, end card 5.0 s.
- [x] "Synthetic demo" provenance visible (persistent badge/label and sidebar label).
- [x] Narrated claims verified against the released fixture (table above).
- [x] Captions reviewed; correct spellings; clear of the alert label and the end-card URL.
- [x] Actual interactions shown: preset switch, industry selection, Mapper view/edge highlight,
      alert explanation, blind Replay -> Reveal, Validation.
- [x] Uninterrupted five-second GitHub end card.
- [x] Audio checked with sound off/on (captions suffice without audio).
- [x] Owner sign-off on the final cut (confirmed after review).
- [ ] Hosted re-record from the public Community Cloud URL (optional; the local capture is from the same v1.0.0 commit/fixture and the hosted app is now verified public).

## Known deviations

- Footage was recorded from the local v1.0.0 release candidate before the hosted signed-out
  verification completed. The hosted app now runs the same commit/fixture; re-run the pipeline with
  `--app-url <public URL>` to refresh the footage from the hosted URL if desired.
- A visible mouse cursor is not captured by headless Chromium; click locations are highlighted with
  a short amber marker in post-production instead.
- The matched-warning scene uses the specification's approved late-warning alternate narration and
  a clearly labelled teaching example because the frozen synthetic showcase has no TDA alert that
  the revised evaluator credits. This is excluded from the evaluation and stated on screen.

## Files

| File | Purpose |
| --- | --- |
| `docs/video/storyboard.json` | Scene plan, timings, narration, interactions and asset references |
| `docs/video/narration.md` | Readable narration script with voice/rate/loudness notes |
| `docs/video/TopoMarket_demo_60s.srt` | Reviewed English captions |
| `docs/video/build_report.json` | Technical report, hashes, scene/actions and loudness measurements |
| `tools/video/build_demo_video.py` | Re-runnable capture + narration + assembly pipeline |
| `docs/assets/opening_card_16x9.png` / `end_card_16x9.png` | 16:9 cards derived from the social preview |
| `docs/assets/social_preview.png` | GitHub social preview source |
| Release assets | `TopoMarket_demo_60s.mp4`, `TopoMarket_demo_60s.srt`, narration WAV, source recordings archive |

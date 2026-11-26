# Demo video production notes (v1.2 film)

60-second English film for the v1.2.0 release-audit follow-up. The public deployment was rebooted
and smoke-tested on release 1.2.0 before this cut; all 10 signed-out checks passed at
`2026-11-26T11:26:30Z` (`docs/measurements/hosted_evidence_v1.2.json`, cold start 7.93 s). The published cut
itself was recorded from the identical local v1.2.0 build because a scripted hosted-iframe attempt
stalled for more than 15 minutes in the Validation scene. The manifest retains the public URL, UTC
timestamp, visible version, fixture ID and release commit.

| Item | Value |
| --- | --- |
| Release | `v1.2.0` |
| Recorded identity | v1.2.0 sidebar; local build of release code `e40d742` (repo HEAD `ea93bf4` at capture) |
| Hosted app | <https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/> - all 10 signed-out checks passed, 0 failed; 25 static-asset 404/403 console messages, 0 page errors |
| Fixture | `showcase-synthetic`, seed 4242, 5,673 sessions 2005-01-03..2026-09-30 |
| Data policy | Synthetic data only; no genuine market data, credentials or private files in the footage |
| Master | `TopoMarket_demo_60s.mp4` - H.264 High 1920x1080 30 fps, AAC 48 kHz stereo, 60.000 s |
| Captions | `TopoMarket_demo_60s.srt` - 12 cues; captioned playback `TopoMarket_demo_60s_captioned.mp4` |
| Delivery bundle | `production_source.zip` (scene recordings, TTS, narration, SRT, storyboard, build script, cards, capture manifest) |

## Storyboard (fixed 6/13/8/12/10/6/5 seconds)

| Time | Picture and action | Narration |
| --- | --- | --- |
| 00:00-00:06 | Social preview opening card | "TopoMarket maps market structure and tests whether topology can warn of sharp declines." |
| 00:06-00:19 | Guided tour first stop: frozen retrospective pair 2008-08-29 29/66 (mean r 0.791) -> 2008-10-10 66/66 (mean r 0.911, +37/0), onset 2008-09-16, retrospective label, r >= 0.80 cutoff, comparison enabled | "Frozen retrospective: 29 of 66 pairs on 2008-08-29; 66 of 66 on 2008-10-10. Mean correlation rises from 0.791 to 0.911." |
| 00:19-00:27 | Finance selected in the interactive network (11 qualifying pairs), then Mapper groups overlap view with the selected Finance group highlighted | "Finance: eleven qualifying pairs. Mapper groups portfolios by shared structure." |
| 00:27-00:39 | 2025-03-10 late-warning teaching example: warning label, percentile 100.0, frozen threshold 100.0, Takens embedding (56 points) and H1 persistence diagram (longest lifetime 0.921) | "March 10, 2025: a late-warning teaching example at percentile 100. Takens and H1 show the S&P 500 return shape; the frozen threshold is 100." |
| 00:39-00:49 | Blind Replay with no outcome, then explicit reveal: origin close 305.998293, 10% boundary 275.3984637, lowest close 299.830407 (2025-03-14), first breach none, maximum decline 2.02%, target not reached | "Blind replay. Reveal: the index stayed above the 10% boundary, with a 2.02% maximum decline." |
| 00:49-00:55 | Validation evidence cards/chart: TDA 0/3 (AP 0.0154, 0.91 false alerts/year), VIX 1/3 (AP 0.1187), realized volatility 0/3 (AP 0.0556), experimental wording and limitations | "Experimental: TDA 0 of 3, VIX 1 of 3. Average precision is low." |
| 00:55-01:00 | Static end card holding the exact URL `github.com/SergeyGer/TopoMarket` for five seconds | "Explore the code and the live demo on GitHub." |

## Verified claims

Every spoken number and on-screen number was checked against the released fixture and
`showcase/reports/evaluation-showcase.json` (machine-readable table in `docs/video/build_report.json`).

- Frozen pair: **29/66** on 2008-08-29 (mean r 0.791036) -> **66/66** on 2008-10-10
  (mean r 0.910608); **+37 added, 0 removed**; onset 2008-09-16; labelled retrospective synthetic
  example; fixed r >= 0.80 cutoff; not a live prediction.
- Teaching example: 2025-03-10 is a **late-warning teaching example outside the frozen evaluation**;
  comparative percentile **100.0**, frozen threshold **100.0**; Takens 56 points, dimension 3, lag 2;
  H1 longest finite lifetime 0.921. The warning panel says "Teaching example (late warning)".
- Replay: blind state has no outcome; reveal shows origin **305.998293**, 10% boundary
  **275.3984637**, lowest close **299.830407** on 2025-03-14, first breach **none**, maximum decline
  **2.02%** (2.01566%), 20-session horizon; the 10% target was not reached. The narration states the
  index stayed above the boundary rather than promising a successful warning.
- Validation: `Experimental market anomaly`; TDA recall **0/3**, AP **0.0154**, false alerts
  **0.91/year**; VIX **1/3**, AP **0.1187**; realized volatility **0/3**, AP **0.0556**; event
  prevalence 0.013309. The film says average precision is low and does not claim a positive result.
- End card holds the exact URL `github.com/SergeyGer/TopoMarket` for the final five seconds.

## Technical validation

- 60.000 s master (target 60 +/- 0.1 s); 1920x1080, 30 fps, H.264 High `yuv420p`; AAC LC 48 kHz
  stereo.
- Integrated loudness **-16.16 LUFS** measured, true peak **-3.99 dBTP** (limit -1.5 dBTP), LRA 5.4;
  two-pass loudnorm, linear=true.
- 12 reviewed SRT cues; TopoMarket/Mapper/S&P 500 spellings verified; captions burned at 8 pt in the
  captioned copy; the end-card URL is clear of the caption.
- `ffmpeg blackdetect` found no black intervals; frames at every scene switch and the contact sheet
  (`/tmp/tm-build-v12/contact.png`) were reviewed. No blank/loading frames in the accepted cut.
- Captions and captioned playback verified at 60.000 s; frame review confirms the burned captions and
  end-card URL.
- The `tools/video/build_demo_video.py` pipeline uses dynamic anchors (recorded event timestamps) so
  hosted/local load variation cannot drift the edit; `--app-url` remains supported for a hosted
  re-record.

## Known deviation

The public app initially served release 1.1.0 and crashed on the 2025-03-10 teaching example with
`topomarket.topology.config.FrozenConfigurationError`. The owner rebooted Community Cloud; the app
then served release 1.2.0 and all signed-out checks passed. A scripted hosted-iframe capture was
attempted after that, but it stalled for more than 15 minutes in the Validation scene, so the final
cut was recorded from the identical local v1.2.0 build at repo HEAD `ea93bf4` (release code
`e40d742`). The public URL, UTC timestamp, visible version, fixture ID and commit are recorded in the
manifest; the hosted test evidence is `docs/measurements/hosted_evidence_v1.2.json`. Re-record with:

```bash
/tmp/tm-video/venv/bin/python tools/video/build_demo_video.py \
  --app-url https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/
```

## Review checklist

- [x] 60.000 s master; opening 6 s and static end card 5 s.
- [x] Synthetic provenance visible; no genuine data or credentials.
- [x] On-screen dates, numbers and labels agree with the released report (claims table above).
- [x] Actual interactions: guided first stop + comparison, Finance + Mapper, teaching example,
      blind Replay then reveal, Validation evidence.
- [x] Captions reviewed; captioned playback produced.
- [x] End card holds the exact URL for five seconds; caption clear of the URL.
- [x] Hosted signed-out smoke on 1.2.0 (10/10 checks) and local fallback documented.
- [ ] **Owner sign-off on the final v1.2 cut (pending).**

## Pipeline outputs

`/tmp/tm-build-v12/TopoMarket_demo_60s.mp4`, `TopoMarket_demo_60s.srt`,
`TopoMarket_demo_60s_captioned.mp4`, `narration.wav`, `production_source.zip`, `contact.png`,
`build_report.json`, `capture.json`.

## Owner actions before release

- [ ] Owner sign-off on the final v1.2 cut (requested after this delivery).
- [ ] Attach `TopoMarket_demo_60s.mp4`, `TopoMarket_demo_60s_captioned.mp4`,
      `TopoMarket_demo_60s.srt`, `narration.wav` and `production_source.zip` to the v1.2.0 release
      assets (the files are staged in `/tmp/tm-build-v12/`).

# Demo video production notes (v1.3 film)

60-second English film for the v1.3.0 release-audit remediation (issue #86). The intended source
was the public Streamlit deployment; it was stale/broken in three fresh signed-out sessions
(visible release 1.2.0, `AttributeError` instead of the dashboard), so the final cut was recorded
from the identical local v1.3 working tree. The public URL, UTC capture time, visible release,
fixture, code revision and the deviation are all recorded in `build_report.json`; the source is
never labelled as localhost. See `public_probe.json` for the three failed public attempts.

| Item | Value |
| --- | --- |
| Release | `v1.3.0` (remediation candidate; package version bump tracked as #87) |
| Visible app release | `1.2.0` (the checked-out package version at capture) |
| Capture environment | `local_build_fallback` |
| Public app | <https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/> |
| Capture UTC | `2026-11-26T14:04:50Z` |
| Fixture | `showcase-synthetic`, seed 4242, 5,673 sessions 2005-01-03..2026-09-30 |
| Code revision | `b119e7c5e54e` (clean `app.py`); builder sha256 `335a387a1b5004b5` |
| Master | `TopoMarket_demo_60s.mp4` - H.264 High 1920x1080 30 fps, AAC 48 kHz stereo, 60.000 s |
| Captions | `TopoMarket_demo_60s.srt` - 13 cues; captioned playback `TopoMarket_demo_60s_captioned.mp4` |
| Delivery bundle | `production_source.zip` (scene recordings, TTS, narration, SRT, storyboard, builder, cards, capture manifest, app snapshot/patch, public probe) |

## Deviation from the public deployment

Public deployment was stale/broken in three fresh signed-out browser sessions (2026-11-26T13:49:02Z..13:49:16Z). Each loaded the shell with visible release 1.2.0, fixture showcase-synthetic, then rendered AttributeError instead of the dashboard; Window A 2008-08-29 could not be reached. The final cut therefore records the identical local v1.3 build at code revision b119e7c5e54eac499056fe3d6e395710e4d83c20 (clean app.py) with the working-tree builder whose sha256 is fc9763bed32ef96b0cd87c94d8189d947c2e7592532b48e5870f3fe022f82ad3. The public URL, UTC, visible version, fixture and commit are retained; this is a documented deviation from the intended public capture, not a claim that the public app was recorded.

The public URL, UTC, visible version, fixture and commit are retained exactly as required. The
manifest source is `public_deployment` (intended) with a documented local fallback; do not read the
fallback as a claim that the public app was recorded.

## Storyboard (fixed 6/13/8/12/10/6/5 seconds)

| Time | Picture and action | Narration |
| --- | --- | --- |
| 00:00-00:06 | Social preview opening card | "TopoMarket maps market structure and tests whether topology can warn of sharp declines." |
| 00:06-00:19 | Corrected guided comparison: Window A 2008-08-29 29/66 first, Window B 2008-10-10 66/66 second, +37 added / 0 removed, Retrospective synthetic example | "Window A, 29 August 2008: 29 of 66 qualifying pairs. Window B, 10 October 2008: 66 of 66; 37 added, none removed. Retrospective synthetic example." |
| 00:19-00:27 | Finance selected (11 qualifying pairings), then Mapper groups with Finance in node-01 (7 members) and the node-01--node-02 edge highlighted: Consumer durables shared | "Finance has eleven qualifying pairings. Mapper places Finance with Manufacturing and Chemicals; Consumer durables is shared across groups." |
| 00:27-00:39 | 2025-03-10 recorded alert: percentile 100 vs frozen threshold 100; both the 56-point Takens embedding and the H1 persistence diagram with highlighted interval stay visible; no PCA scroll | "10 March 2025: a recorded alert at percentile 100, versus a frozen threshold of 100. The 56-point Takens embedding and the highlighted H1 interval show the shape of recent S&P 500 returns." |
| 00:39-00:49 | Blind Replay with no outcome, then explicit reveal: chart with 10% boundary, then outcome cards and the recorded-late-alert warning; 2.02% maximum decline | "Blind replay. Reveal: the index stayed above the 10% boundary; maximum decline, 2.02%. Recorded late alert, included in the evaluation, zero early-warning credit." |
| 00:49-00:55 | Two large figures headed "Synthetic holdout · 3 episodes": TDA 0/3 (AP 0.0154) and VIX 1/3 (AP 0.1187) | "Three episodes: TDA 0 of 3; VIX 1 of 3. Average precision is low." |
| 00:55-01:00 | Static end card holding the exact URL `github.com/SergeyGer/TopoMarket` for five seconds | "Explore the code and the live demo on GitHub." |

## Verified claims

- Guided pair: **Window A 2008-08-29, 29/66** (mean r 0.791036) -> **Window B 2008-10-10, 66/66**
  (mean r 0.910608); **+37 added, 0 removed**; onset 2008-09-16; label
  "Retrospective synthetic example"; no reversed shot.
- Mapper: Finance has **11 qualifying pairings**; Finance is in **node-01 (7 members)**; the
  **node-01--node-02** edge shares **Consumer durables**, Energy, Chemicals and Wholesale & retail;
  node-02 has **6 members**.
- Late alert: 2025-03-10 is a **recorded post-onset late alert inside the frozen evaluation**
  (episode onset 2025-03-06) with **zero early-warning credit**; percentile **100.0**, frozen
  threshold **100.0**; Takens 56 points, dimension 3, lag 2; H1 longest finite lifetime 0.921.
  Blind mode stays neutral until the reveal.
- Replay: blind state has no outcome; reveal shows origin **305.998293**, 10% boundary
  **275.3984637**, lowest close **299.830407** on 2025-03-14, first breach **none**, maximum decline
  **2.02%** (2.01566%), 20-session horizon; the 10% target was not reached.
- Validation: **TDA 0/3, AP 0.0154**; **VIX 1/3, AP 0.1187**; **3 episodes**, 3,306 eligible
  sessions; event prevalence 0.013309. The film says average precision is low and does not claim a
  positive result.
- End card holds the exact URL `github.com/SergeyGer/TopoMarket` for the final five seconds.

## Technical validation

- 60.000 s master (target 60 +/- 0.1 s); 1920x1080, 30 fps, H.264 High `yuv420p`; AAC LC 48 kHz
  stereo.
- Integrated loudness **-16.17 LUFS**, true peak
  **-4.4 dBTP** (limit -1.5 dBTP), LRA
  2.9; two-pass loudnorm, linear=true.
- 13 reviewed SRT cues; four audit checkpoints at 00:16, 00:30, 00:46 and
  00:52 resolve as follows:
  - 00:16 - Window B, 10 October 2008: 66 of 66; 37 added, none removed.
  - 00:30 - 10 March 2025: a recorded alert at percentile 100, versus a frozen threshold of 100.
  - 00:46 - Recorded late alert, included in the evaluation, zero early-warning credit.
  - 00:52 - Three episodes: TDA 0 of 3; VIX 1 of 3. Average precision is low.
- The end-card URL is clear of the final caption; the last cue ends at 00:58.600.
- `ffmpeg blackdetect` found 0 black interval(s); frames at
  every scene switch and the contact sheet (`contact.png`) were reviewed. No blank/loading frames in
  the accepted cut.
- Captions and captioned playback verified at 60.000 s; frame review confirms burned captions and
  the end-card URL.
- `tools/video/build_demo_video.py` is the actual checked-in builder used for this cut. It uses
  dynamic anchors (recorded event timestamps) so hosted/local load variation cannot drift the edit;
  `--app-url` remains supported for a hosted re-record.

## Scene and cue issues fixed in this cut

- **Guided comparison:** the captured A/B order is chronological (Window A 2008-08-29 29/66;
  Window B 2008-10-10 66/66; +37/0); no reversed frame is present.
- **Topology date sync:** after the preset click, Streamlit's sidebar slider lagged one render at
  2020-02-24. The capture now forces a Next/Previous cycle and a repeated preset click, waits for
  "Selected session: 2025-03-10", and only then scrolls; the sidebar reads 2025-03-10 throughout the
  Takens/H1 shot.
- **Mapper edge timing:** Finance and Mapper are separate edited scenes (3.5 s + 4.5 s), so the
  node-01--node-02 edge and Consumer durables detail hold through the shared-portfolio sentence.
- **Replay reveal:** blind Replay and reveal are separate scenes; the reveal scene starts once the
  outcome exists, avoiding the rerun's faded overlay and holding the 10% boundary and 2.02% cards
  through the late-alert sentence.
- **Tooltips:** Streamlit hover tooltips are hidden in capture; the previous topology shot showed a
  tooltip over the sidebar.
- **Caption checkpoints:** 00:16 now reads "Window B, 10 October 2008: 66 of 66; 37 added, none
  removed."; 00:30, 00:46 and 00:52 carry the percentile/late-alert/TDA-VIX wording.
- **End-card clearance:** the last cue ends at 00:58.600, leaving
  `github.com/SergeyGer/TopoMarket` clear; no caption is present at 00:59.5.

## Review checklist

- [x] 60.000 s master; opening 6 s and static end card 5 s.
- [x] Corrected A/B order and +37/0 held on screen; no reversed shot.
- [x] Both topology plots held during the Takens/H1 sentence; no PCA scroll.
- [x] Blind Replay then reveal; 2.02% and the 10% boundary visible; outcome enlarged.
- [x] Large "Synthetic holdout · 3 episodes" TDA 0/3 vs VIX 1/3 figures.
- [x] Synthetic provenance visible; no genuine data or credentials.
- [x] On-screen dates, numbers and labels agree with the released report.
- [x] Captions reviewed; captioned playback produced; four cue checks pass.
- [x] End card holds the exact URL for five seconds; caption clear of the URL.
- [x] Public deployment probed three times; local fallback documented with URL/UTC/version/fixture/commit.
- [ ] **Owner sign-off on the final v1.3 cut (pending).**
- [ ] Attach the final media to the v1.3.0 release (owner action).

## Pipeline outputs

`/tmp/tm-build-v13/TopoMarket_demo_60s.mp4`, `TopoMarket_demo_60s.srt`,
`TopoMarket_demo_60s_captioned.mp4`, `narration.wav`, `production_source.zip`, `contact.png`,
`build_report.json`, `capture.json`, `public_probe.json`.

## Owner actions before release

- [ ] Owner sign-off on the final v1.3 cut (requested after this delivery).
- [ ] Attach `TopoMarket_demo_60s.mp4`, `TopoMarket_demo_60s_captioned.mp4`,
      `TopoMarket_demo_60s.srt`, `narration.wav` and `production_source.zip` to the v1.3.0 release.
- [ ] Push/refresh the public Streamlit deployment at the selected v1.3 revision and publish the
      v1.3.0 GitHub release assets so the Pages player resolves.

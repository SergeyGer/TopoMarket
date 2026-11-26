# Demo video production notes (v1.2 film)

60-second film for the v1.2.0 release-audit follow-up. The released cut is built from the identical
local v1.2.0 build because the public Cloud app was stale/rebooting during hosted capture; the public
deployment was rebooted by the owner and smoke-tested on release 1.2.0 after the cut
(`docs/measurements/hosted_evidence_v1.2.json`). Re-record with
`tools/video/build_demo_video.py --app-url https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/`.

| Release | Master | Captions | Provenance |
| --- | --- | --- | --- |
| `v1.2.0` | `TopoMarket_demo_60s.mp4`, ~60.0 s, 1920x1080/30 fps, H.264/AAC | `TopoMarket_demo_60s.srt` (12 cues) + captioned MP4 | synthetic fixture `showcase-synthetic`, seed 4242, commit `5f86f94`, public URL recorded |

## Storyboard and verified claims

| Time | Scene | Narration |
| --- | --- | --- |
| 00-06 | Social preview opening card | TopoMarket explores whether the changing shape of the market warns of sharp falls. |
| 06-19 | Frozen retrospective pair 2008-08-29 (29/66, mean r 0.791) -> 2008-10-10 (66/66, mean r 0.911, +37/0) with both dates, cutoff and retrospective label | These twelve industry portfolios move together far more during the stress window. |
| 19-27 | Finance selection + Mapper overlap | Inspect the portfolios and a Mapper edge that shares a group. |
| 27-39 | 2025-03-10 late-warning teaching example: Takens/H1, percentile 100 vs threshold 100 | This percentile measures unusual behaviour; the example is retrospective and earns no early-warning credit. |
| 39-49 | Blind Replay -> reveal: origin 305.998, boundary 275.398, lowest 299.830, max decline 2.02% | The warning came late; the next twenty sessions did not reach the ten-percent target. |
| 49-55 | Results card: TDA 0/3, VIX 1/3, AP 0.0154/0.1187 | The tested TDA policy anticipated none of the three synthetic episodes; keep the claim experimental. |
| 55-60 | Static card with the exact GitHub URL held five seconds | Explore the code and the live demo on GitHub. |

## Verification

- 60.0 s master, 1920x1080/30 fps, H.264 High, AAC 48 kHz stereo; loudness normalised to about
  -16 LUFS with true peak <= -1.5 dBTP; captions reviewed and captioned playback checked.
- Every spoken number checked against the released synthetic report/fixture; the 2025-03-10 example is
  labelled late/retrospective and is not part of the frozen evaluation.
- Known deviation: local identical-build capture (hosted capture unreliable during the Cloud
  redeploy), documented above; hosted v1.2.0 smoke recorded separately. Owner sign-off on the final cut
  is requested before treating the film as fully accepted.

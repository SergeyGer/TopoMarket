# TopoMarket v1.3.0 acceptance evidence

Updated v1.2.0 release-audit remediation (26 November 2026). Decision: the research application is
accepted; this release corrects the guided demonstration, media/documentation and cross-platform
verification, and links one named revision to the tested code, hosted app, film and evaluation report.
Baseline: `main` at the first v1.3 remediation merge (`54af61a`), published tag `v1.2.0` (`ea93bf4`).

Plan and issue map: `docs/UPGRADE_v1.3.md` (epic #88, milestone **Release v1.3**).

## Release-audit dispositions

| Finding | Evidence |
| --- | --- |
| Guided comparison ran backwards | **Fixed** (#77, PR #91): Window A 2008-08-29 29/66, Window B 2008-10-10 66/66, +37/0; captions/cards/legend/edge colours/accessible table derive from the ordered result. AppTest asserts per-card dates/counts and sign. |
| Mapper opened the wrong group | **Fixed** (#78, PR #91): selected Mapper node id carried through state/persistence/cache; node-01 = 7 members, node-02 = 6 members; edge shows real shared portfolios; AppTest covers both. |
| 2025-03-10 described as outside the evaluation | **Fixed** (#79, PR #91): recorded post-onset late alert inside the frozen evaluation (episode onset 2025-03-06, zero early-warning credit, max decline 2.02% below the 10% target) in inspector/preset help/Replay/Structure reveal/film notes; blind mode neutral. |
| Watch links opened source / stale captions | **Fixed** (#80, PR #92): GitHub Pages player published at <https://sergeyger.github.io/TopoMarket/watch/index.html>; README/Wiki link the signed-out player; WebVTT/Markdown/inline transcripts generated from the reviewed SRT; playback+caption seek checks on desktop/mobile recorded in `docs/measurements/watch_playback_evidence.json`. |
| Public report had empty provenance | **Fixed** (#81, PR #92): report regenerated with import-manifest identity/digest, independent-calendar metadata, code revision and bootstrap v2; metrics unchanged (TDA 0/3 AP 0.0154, VIX 1/3 0.1187, realised vol 0/3 0.0556; 3,306 sessions). |
| README hero/citation/Wiki stale | **Fixed** (#82, PRs #89/#90): 2008 two-window hero with dates/counts and alt text, v1.2 citation; Wiki Home status merged into Roadmap, professional menu with Mathematics page, Methodology corrected to private TDA 0/9. |
| Mathematics formatting/boundary | **Fixed** (#83, PR #89): `\operatorname` macros replaced with KaTeX-allowed `\mathrm`; §5.1/§7.5 and boundary table state full-precision qualification with six-decimal display tags; network-builder boundary test. |
| Windows checkout failures | **Fixed** (#84, PR #93): host-native path normalisation, POSIX canonical JSON/report paths, LF-pinned checksummed fixtures, Windows profile env isolation, `.gitattributes`; CI `windows-latest` job green (683 passed, 21 skipped, release-check). |
| Stale timing / private receipt | **Delivered** (#85): fresh timing in `docs/measurements/browser_performance_v13.json` (commit, environment, cold start, cached p50/p95) and a sanitised private-suite receipt in `docs/measurements/private_acceptance_receipt_v13.json`. |
| Film reversed shot / PCA over narration / dense results / builder mismatch | See the film section below (#86). |

## Performance evidence (#85)

`docs/measurements/browser_performance_v13.json` records the fresh browser run on the v1.3 candidate:
Playwright Chromium headless 1440x900, commit `f40b1f3`, platform/Python/CPU, cold start (spawn to
first rendered app heading) and the 100 cached preset date changes separately. Final clean run:
**p95 497.6 ms / p50 421.2 ms** (target 500 ms, 0 failures); uncached 20 next-session changes
p95 487.0 ms. Direct-inspection controls are lazy (single compact selector) so the default rerun path
stays inside the timing budget while tap/edge targets remain available on demand.

## Private acceptance receipt (#85)

`docs/measurements/private_acceptance_receipt_v13.json` records the owner-seeded run: tested commit,
environment, totals, skip reasons and A7 status. No private data, seed, rows or file digests are
committed; detailed reports stay outside the repository under `~/TopoMarket-private-results/`.

## Hosted evidence

Hosted signed-out 10/10 evidence for v1.2.0 remains in `docs/measurements/hosted_evidence_v1.2.json`
(identity 1.2.0, landing/interactive chart, frozen pair, comparison, blind/reveal, Validation, Data,
mobile, two isolated sessions, cold start 7.93 s). v1.3.0 hosted smoke (including per-card chronology
and Mapper node checks) is recorded at release time.

## Release

- Published: <https://github.com/SergeyGer/TopoMarket/releases/tag/v1.3.0> (tag `v1.3.0`, main
  `c65a9ed`), 9 assets: hosted film MP4/SRT/captioned/narration/production source, wheel, sdist,
  test report, release-check report.
- Player: <https://sergeyger.github.io/TopoMarket/watch/index.html> (versioned v1.3.0 media links; the
  release assets are now attached so playback is unblocked).
- Git history: remediation merges #89-#95; historical v1.0-v1.2 tags/artefacts retained.

## Film and release gates

- [x] Corrected public-deployment film recorded from the fixed public app (source public_deployment,
      UTC 2026-11-26T14:31:34Z, visible release 1.2.0, fixture showcase-synthetic, commit 0baf9c2, no
      deviation); chronology, both topology plots through the Takens/H1 narration, 2.02%/10% reveal,
      large TDA 0/3 vs VIX 1/3 and end-card URL verified; checked-in builder secret-scan clean;
      assets attached to v1.3.0 (#86).
- [x] Captions/transcripts regenerated from the final narration; four cue checks at 00:16/00:30/00:46/
      00:52 verified against the frame content; watch page links versioned v1.3.0 assets (#86/#87).
- [x] v1.3.0 tagged and published with 9 assets; version bump/frozen artifacts, Linux (py3.11/3.12) and
      Windows CI, release checks, dependency audit, CodeQL and cloud smoke green (#87).
- [x] Owner film sign-off recorded on 26 November 2026 for the published v1.3.0 master
      (`803d51d61911497a99f2e83b653da0afee244c958d8cb31ea27d3ce4437c322a`); public YouTube version:
      <https://youtu.be/8Xyp-BDM88Q>.
- [x] Sanitised private-suite receipt on the selected v1.3.0 commit: **701 passed, 0 failed,
      0 skipped** (21:16) with the owner seed on `c65a9ed`; snapshot identity `5ca5aac2…`;
      aggregate only in `docs/measurements/private_acceptance_receipt_v13.json`, detailed
      logs/imports outside the repository.
- [x] Hosted v1.3.0 identity re-check after the owner reboot: signed-out smoke shows
      `release 1.3.0`, landing/interactive chart, chronological frozen pair and comparison, mobile
      without overflow, two isolated sessions; cold start 9.4 s in
      `docs/measurements/hosted_evidence_v1.3.json`.

## Known limitations / owner actions

- The private seed and detailed historical reports remain outside Git; the receipt is aggregate only.
- Performance is host-sensitive: the released measurement is the final clean run on an idle host; the
  p95 target is met with a small margin, so future UI additions must preserve the lazy-control path.
- The hosted player depends on GitHub Pages availability; the release MP4/SRT remain the durable
  fallback downloads.

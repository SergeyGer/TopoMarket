# TopoMarket v1.2.0 acceptance evidence

Release-audit follow-up (26 November 2026). Decision: accept the interactive market-structure
demonstration; keep the early-warning claim **experimental**. This release fixes evaluation integrity,
makes the Studio walkthrough trustworthy and gives the project a reader-first public face.

Candidate: the `v1.2.0` tag/commit (this document ships with it). Baseline: `v1.1.0` (`6907555`).
Plan and issue map: `docs/UPGRADE_v1.2.md` (epic #66, milestone **Release v1.2**).

## Release-audit package dispositions

| Package | v1.1 disposition | v1.2 evidence |
| --- | --- | --- |
| Calibration and evidence | Partly met | **Met**: R1 independent calendars (#55), R2 bootstrap multiplicity (#56), R3 CLI snapshot identity (#57); F01 calibration fix retained; versioned reports/policies/interval algorithm; private run recorded outside the repo. |
| Blind Replay | Core delivered | **Met**: blind state derives only from observations at/before the selected close; blind replay blocks the comparative view (#58); future/report mutation tests cover the complete rendered payload; inline reveal/hide keeps Structure mounted (#59). |
| Structure Studio | Partly met | **Met**: two dated interactive networks with a shared cursor and inspectable portfolios; real added/removed edge encoding (#58); single-tap node/edge/Mapper inspection (#59); frozen retrospective 2008 pair (#60); desktop/mobile layout and cached-date evidence recorded with the release. |
| Film and hosting | Partly met | **Met**: re-recorded 60-second film with hosted URL/UTC/version/fixture/commit manifest, WebVTT/SRT/captioned copy; public deployment signed-out smoke; watch page with captions/transcript (#62/#63). |
| Public documentation | Needs work | **Met**: reader-first README (~750 words), `docs/MATHEMATICS.md`, Wiki navigation, honest holdout wording (TDA 0/3, VIX 1/3), browser-playable watch page. |
| Private acceptance | 2 A7 failures | **Met**: A7 updated to the current 19,343-index-calendar/Structure-Replay contract (#64); baseline A7 2 failed / candidate A7 4 passed; full private suite green (recorded outside the repo). |

## Evaluation-integrity evidence

- **R1.** New `topomarket.data.signals` loads independent price/industry/VIX calendars with an explicit
  joint fallback for old snapshots. Acceptance tests append price/VIX sessions beyond industry coverage
  and mutate only industry data, asserting price scores and evaluation reports are byte-identical.
  Owner-seeded end-to-end run: 19,343 index rows 1950-01-03..2026-11-18, latest TDA score **2026-11-18**
  (baseline 9,250 rows, latest 2026-09-30), industry as-of 2026-09-30, VIX 2026-11-19, common eligible
  3,220 (baseline 3,185), snapshot ID `5ca5aac2…` vs empty baseline.
- **R2.** Blocks drawn with replacement, concatenated and trimmed to N, identical position weights for
  each method's frozen event indicators, exposure fixed at N; algorithm identity
  `moving_block_with_replacement_v2`; duplicate-block/absent-event/shared-draw tests; regenerated
  intervals versioned against the retained v1.1 report.
- **R3.** Active pointer -> refresh manifest -> import manifest/content digest resolution with conflict
  failures; identity/source/digest in report provenance and private ledger; direct-directory, digest
  fallback, conflict and CLI-report tests.

Private holdout before -> after (same owner seed, same code paths except this release's fixes):

| Method | Recall | False alerts / year | AP |
| --- | --- | --- | --- |
| TDA | 0/9 -> 0/9 | 1.582 -> 1.565 | 0.049399 -> 0.049203 |
| Realised volatility | 1/9 -> 1/9 | 1.029 -> 1.017 | 0.070399 -> 0.070358 |
| VIX | 0/9 -> 0/9 | 0.0791 -> 0.0783 | 0.067743 -> 0.067569 |

Frozen calibration percentiles are unchanged (TDA 97.5, realised volatility 85, VIX 95); the wording
stays `Experimental market anomaly`. Detailed private reports and the seed remain outside the repository
under `~/TopoMarket-private-results/`.

## Studio and visual evidence

- **U1** explicit tour start, no quiet-window mislabel; first stop is the frozen retrospective pair
  **2008-08-29 29/66 (mean r 0.791) -> 2008-10-10 66/66 (+37/-0, mean r 0.911)**, onset 2008-09-16,
  labelled retrospective synthetic example.
- **U2** blind replay has no comparative control and clears stale state; comparison is retrospective
  only after reveal; future-data and rendered-payload mutation invariance tests.
- **U3** removed edges amber+dashed, added edges positive+solid, kept quiet, legend + hover
  correlations; tests compare rendered styles to independently computed edge sets.
- **U4** 12 single-tap portfolio targets, edge inspector with exact Pearson r, direct Mapper group
  buttons; AppTest pointer-equivalent checks.
- **U5** inline Structure reveal/hide of origin close, 10% boundary, lowest close, first breach and
  maximum decline; network/date/threshold/H1 stay mounted; hide restores the blind payload.
- Layout/performance evidence: `docs/measurements/` (desktop/mobile screenshots, cached
  date-change timings) recorded with the release workflow.

## Mathematics and documentation

- `docs/MATHEMATICS.md` reference revision 1.0 with corrected definitions, units, worked examples
  (60->56, tied midrank 76.19, earliest score return 564, Mapper closed cover endpoints, exactly 0.80,
  day 20 vs 21, duplicate-block multiplicity) and 9 executable checks; correlation qualification uses
  the full-precision value, the six-decimal value is a display/provenance tag.
- README ~750 words with the reader-first first screen, honest holdout numbers and experimental
  caveat; `docs/watch/index.html` browser player with English WebVTT captions + transcript + downloads.

## Film evidence

- 60.000 s master, 1920x1080/30 fps, H.264/AAC, loudness about -16 LUFS, true peak <= -1.5 dBTP;
  recording manifest captures the public URL, UTC timestamp, visible release version, fixture ID and
  release commit; reviewed WebVTT/SRT captions, captioned playback copy and editable production source
  attached to the release.
- Scenes: opening card; 29/66 -> 66/66 retrospective pair; Finance + Mapper overlap; 2025-03-10
  late-warning teaching example with Takens/H1 and percentile 100/threshold 100; blind Replay ->
  reveal (origin 305.998, boundary 275.398, lowest 299.830, max decline 2.02%, target not reached);
  results card TDA 0/3 and VIX 1/3 (AP in details); static repository URL for five seconds.

## Release gates

- [ ] Public suite green (CI tests py3.11/3.12, release checks, dependency audit, CodeQL, cloud smoke)
      on the release candidate.
- [ ] Private suite with `TOPOMARKET_SEED_DIR` green on the same candidate (recorded outside the repo).
- [ ] Hosted signed-out smoke on the deployed release identity (`1.2.0`), desktop + mobile + two
      isolated sessions.
- [ ] Film/WebVTT playback and README/mobile entry points verified against the tag.
- [ ] Release assets attached; v1.0/v1.1 artifacts retained; no private data or credentials committed.

## Known limitations / owner actions

- The corrected private evaluation requires the owner seed locally; aggregate results above were
  produced with the supplied seed and are kept outside Git.
- The film is re-recorded from the deployed app where scripted capture succeeds; any fallback to the
  identical local build is documented in the production manifest/deviation note.
- `docs/MATHEMATICS.md` documents the isometric delay-coordinate orientation, the rounded-tag mean
  display and package-bound report/config identities until the version bump.

# TopoMarket v1.2 plan (release audit follow-up)

Plan for `TopoMarket_Release_Audit_and_Improvement_Specification_EN.docx` (26 November 2026).
Decision: accept the interactive market-structure demonstration, keep the early-warning claim
experimental, and ship one focused follow-up covering **evaluation integrity**, **a coherent visual
walkthrough** and **public documentation**. Improving the TDA score itself is out of scope.

Baseline: `main`/`v1.1.0` `6907555`, v1.0/v1.1 reports and film retained.

## Audit disposition (v1.1)

| Package | Disposition | Defects driving v1.2 |
| --- | --- | --- |
| Calibration & evidence | Partly met | standard CLI loses snapshot identity; tagged acceptance lists corrected private run as pending |
| Blind Replay | Core delivered | same Structure replay can show a later comparison window + retrospective episode wording |
| Structure Studio | Partly met | edge-change colours not rendered (all traces same colour); direct Mapper inspection and inline outcome flow missing |
| Film & hosting | Partly met | manifest points at localhost; main comparison runs opposite the spoken change |

Specialist findings: **R1** signals share the joint industry calendar (35 later index sessions have no
fresh TDA reading); **R2** bootstrap draws lose multiplicity via a set (1,972 distinct positions for
3,306 sessions); **R3** direct-directory CLI emits an empty snapshot id; application defects U1–U5;
visual before/after pair; film re-cut; mathematics reference; README/Wiki/watch page; private A7 tests.

## Work packages and issues

- [R1 · Independent signal calendars (#55)](https://github.com/SergeyGer/TopoMarket/issues/55), P0.
- [R2 · Bootstrap multiplicity (#56)](https://github.com/SergeyGer/TopoMarket/issues/56), P0.
- [R3 · CLI snapshot identity (#57)](https://github.com/SergeyGer/TopoMarket/issues/57), P0.
- [U1–U3 · Tour state, blind comparison, edge-change encoding (#58)](https://github.com/SergeyGer/TopoMarket/issues/58), P0/P1.
- [U4–U5 · Direct inspection, inline Reveal (#59)](https://github.com/SergeyGer/TopoMarket/issues/59), P1.
- [Visual before/after scene (#60)](https://github.com/SergeyGer/TopoMarket/issues/60), P1.
- [Mathematics reference (#61)](https://github.com/SergeyGer/TopoMarket/issues/61), P1.
- [README/Wiki/watch page (#62)](https://github.com/SergeyGer/TopoMarket/issues/62), P1.
- [New hosted film + watch page (#63)](https://github.com/SergeyGer/TopoMarket/issues/63), P1.
- [Private acceptance A7 tests (#64)](https://github.com/SergeyGer/TopoMarket/issues/64), P1 (owner seed).
- [Release v1.2.0 (#65)](https://github.com/SergeyGer/TopoMarket/issues/65); [epic (#66)](https://github.com/SergeyGer/TopoMarket/issues/66); milestone **Release v1.2**.

## Build order and gates (from the specification)

1. **Research engineer — R1–R3.** Version the changed score calendar and interval algorithm; retain
   v1.0/v1.1 artefacts. Gate: two input modes, independent-calendar and duplicate-block tests;
   before/after method counts, policy hashes and results on previous common dates and the extended
   cohort; local provenance and source hashes retained.
2. **Application engineer — U1–U5 + frozen increasing pair.** Gate: browser tests for blind
   future-data mutation, real edge-change styles, pointer/touch + keyboard equivalence, correct tour
   state and inline Reveal; desktop/mobile screenshots; two-session isolation.
3. **Maintainer — mathematics reference, README, Wiki, watch page.** Gate: links/anchors/equations
   render in GitHub and mobile; a new visitor can launch the app, watch the film, read the results and
   reproduce the worked example without development history.
4. **Release/media — deploy candidate, signed-out smoke, record new film, tag and attach verified
   assets.** Gate: hosted URL/commit/UTC/version/fixture in the manifest; scene values, runtime,
   loudness, hashes; video/WebVTT playback and README/mobile entry points verified against the tag.

Final sign-off requires the owner-seeded private suite and the public checks on the **same candidate**.

## Evidence contract

- Public synthetic figures for the public walkthrough; historical aggregates only where notices allow.
- Fix the teaching example: 2025-03-10 is present in the holdout (`alerts`/`post_onset_alerts`), the
  episode began 2025-03-06; keep it as a late teaching example with **zero early-warning credit** and
  test that preset wording agrees with the released alert record.
- Every comparison card shows profile, snapshot, holdout dates, denominators, positive-origin
  prevalence and historical-policy version; missing leads render as a dash with explanation.
- Bootstrap interval rule: blocks drawn with replacement, trimmed to N, identical index weights for
  onset/false-alert/exposure indicators; intervals regenerated and versioned.
- R1 acceptance: truncating/appending only industry data keeps price scores and label horizons
  byte-identical; corrected score reaches the later index date while industry coverage keeps its own
  as-of date.
- Documentation: `docs/MATHEMATICS.md` versioned reference with executable examples (60→56, tied
  midrank, no-H1 vs invalid window, closed cover endpoints, exactly 0.80, day 20 vs 21, forced
  duplicate bootstrap block), linked from README/Wiki/app Help.
- Film: record the **public deployment** after signed-out smoke; manifest must not say localhost.

## Progress log

- **R2 (in review):** paired bootstrap now draws blocks with replacement, concatenates/trims to N,
  keeps position multiplicity and applies identical index weights to each method's frozen event
  indicators; exposure denominator fixed at N; algorithm identity stored in report provenance;
  deterministic and duplicate-block/absent-event/shared-draw tests added; synthetic showcase report
  regenerated (gain interval valid replicates 952, TDA false-rate interval 0.38–1.37/year).
- **R3 (in review):** new `topomarket.data.identity.resolve_snapshot_identity` resolves the active
  pointer, refresh manifest, import manifest and content digest; conflicts raise a visible error;
  CLI evaluation carries the identity + provenance into the report and ledger; direct-directory and
  manifest-fallback tests added. R1 remains.

- **R1 (in review):** new `topomarket.data.signals` loads independent price/industry/VIX calendars
  with an explicit joint-`tda_daily` fallback for old synthetic snapshots; `topology`, `evaluate` and
  `industries` CLIs use their own calendars; evaluation rows are the price calendar left-joined with
  VIX by date; reports/CLI expose separate as-of dates, sources and fallback reasons in
  `snapshot_provenance.signal_calendars`. Acceptance tests append price/VIX dates past industry
  coverage and mutate only industry data, asserting price scores and evaluation reports are
  byte-identical. The refreshed-snapshot dashboard view of split calendars is a follow-up under
  U4/docs if needed; default synthetic data keeps the joint fallback.

- **U1/U2/U3/U5 + visual pair (in review):** guided tour now starts explicitly and its first
  stop is the frozen retrospective synthetic pair 2008-08-29 (29/66) -> 2008-10-10 (66/66, +37/0,
  mean 0.791 -> 0.911, onset 2008-09-16), auto-enabling the two-window comparison with both dates,
  counts and the retrospective label; the comparison producer now exposes per-window added/removed
  edges and the figure renders removed edges amber/dashed and added edges positive/solid with a
  legend and hover correlations (tested against independently computed edge sets). Blind replay
  refuses/blocks the comparison view and clears stale comparison state; Structure gains an inline
  reveal/hide outcome panel (origin/boundary/low/breach/max decline) that keeps the network, date,
  threshold and H1 explanation mounted, with a blind-safe payload when hidden. U4 (single-click/tap
  node and Mapper hit targets) remains.

- **Release candidate:** version bumped to 1.2.0; frozen showcase/presets regenerated; acceptance
  pack, hosted smoke, new film, evidence and release assets are being finalised.

## Owner actions pending

- **Private seed:** provide `TOPOMARKET_SEED_DIR` locally (outside Git) so the corrected private
  evaluation, R1/R2/R3 effects and the 678-test private acceptance suite can be re-run and recorded;
  the public repository and this environment do not contain the seed.
- **Film review:** final cut sign-off after the new hosted recording.

# TopoMarket v1.1 upgrade plan

Plan for the engineering acceptance review of v1.0 (`TopoMarket_v1.1_Release_Specification_EN.docx`,
25 November 2026). Decision: accept v1.0 as a substantial visualization and delivery milestone, but
correct the research-integrity defects and add direct manipulation before the next release. One
focused **v1.1.0** release delivers the whole scope.

Baseline: `main` `c788425`, tag `v1.0.0` `a558454`. The v1.0 reports, release assets, live URL and
Wiki remain available for comparison.

## Review findings addressed

| Finding | Severity | Work package |
| --- | --- | --- |
| F01 - calibration recall reads a non-existent `AlertMatch.episode_start`, so recall is always 0 and candidates are ranked only by false alerts (#37) | P0 | WP-A |
| F02 - blind Replay serializes retrospective alert classifications, matched episodes/onsets and outcome hints from the frozen report | P0 | WP-B |
| F03 - charts are static Matplotlib images; no direct node/edge/timeline selection or hover details | P1 | WP-C |
| D - the v1.0 film has a backwards date jump, small technical charts, a late example without a quantified miss and rerendered/scrolled layouts | P1 | WP-D |

## Work packages and GitHub issues

- [WP-A - Correct and freeze evidence (#43)](https://github.com/SergeyGer/TopoMarket/issues/43), P0.
  A1 fix calibration and close #37; A2 versioned policy/report identity with before/after comparison;
  A3 large three-method evidence metrics + comparison chart with CIs/limitations, keeping the
  `Experimental market anomaly` wording and keeping private results local.
- [WP-B - Causal blind Replay (#44)](https://github.com/SergeyGer/TopoMarket/issues/44), P0.
  B1 as-of alert object from readings/policy/cooldown using only dates <= the selected date, neutral
  blind labels, no retrospective matches/classifications in payload, markers, captions, hover,
  exports or preset names (review flow separate); B2 reveal exactly the next 20 closes and derived
  outcome, classification shown only when knowable from the revealed scope, reset on date/fixture
  change.
- [WP-C - Market Structure Studio (#45)](https://github.com/SergeyGer/TopoMarket/issues/45), P1.
  C1 two-window comparison with a chronological guided example or honest regime contrast; C2
  interactive Plotly network/timeline with direct node/edge/timeline selection, hover details,
  Mapper bands/members/overlap and accessible equivalents; C3 guided Quiet -> Stress -> Explain ->
  Replay sequence, inline H1/Takens explanation and mini timeline cursor, stable central plot.
- [WP-D - New 60-second demo video (#46)](https://github.com/SergeyGer/TopoMarket/issues/46), P1.
  Re-shoot from the public v1.1 app: stable composition, enlarged key plot, visible cursor/click
  highlight, honest chronological comparison, blind state and real reveal, large evidence metrics,
  English narration + reviewed SRT + captioned playback version, production report.
- [Release v1.1.0 (#47)](https://github.com/SergeyGer/TopoMarket/issues/47): deploy, hosted smoke,
  evidence pack, README/Wiki and release assets.
- [Epic (#48)](https://github.com/SergeyGer/TopoMarket/issues/48) and milestone **Release v1.1**.

## Build order and exit gates

The specification's order is binding; a later package starts only when the previous gate passes.

1. **A - calibration and evidence.** Correct candidate selection and versioned reports; the v1.0
   report remains as a baseline. Gate: tests prove nonzero recall for multi-candidate recall
   preferences, silent/tied/boundary cases, reproducible hashes, identical eligible dates, and that
   holdout-suffix mutation cannot change the fitted policy. Recall may deteriorate vs v1.0; that is
   reported transparently and does not block the release.
2. **B - blind Replay.** Gate: mutating both future prices and frozen report classifications/matches
   leaves the blind payload, markers, DOM and accessible text byte-identical; no future/outcome data
   in serialized or hidden chart elements; session 20/21, missing-observation, mode and hide/reveal
   boundary tests pass.
3. **C - Market Structure Studio.** Gate: independent Pearson verification, fixed positions, direct
   node/timeline selection and keyboard parity, chronology of guided dates, no future leak on hover,
   above-the-fold layout at 1440x900, no 390 px overflow, reduced-motion equivalence and cached
   date-change p95 <= 500 ms locally over 100 transitions (uncached/hosted recorded separately).
4. **D + release.** Deploy the final commit, run signed-out Cloud smoke on desktop/mobile/two
   sessions, record and verify the new film, publish release assets and links, update README/Wiki.

## Decisions

- Complete the **one release** model: land work through PRs on `main`, tag and publish `v1.1.0` only
  when every gate is green. Individual PRs are not released separately.
- Add **Plotly** as the interactive renderer (`[ui]` extra + effective Cloud `requirements.txt` +
  lock), keeping Matplotlib for static evidence, screenshots and the video pipeline; no component
  build or platform migration.
- Reports gain an explicit schema/version and provenance (`code_revision`, fixture/snapshot digest,
  calibration/policy/holdout hashes, candidate table, comparison block). v1.0 report files are kept
  untouched as `evaluation-v1.0-baseline.json` (or equivalent) for before/after display.
- Blind Replay gets a strict as-of projection; teaching/review examples (`Late warning`,
  `Missed warning`) move behind the explicit review flow and neutral preset labels in blind mode.
- Synthetic evidence is public; private reference results stay local and are only documented. The
  private seed is not present in this environment, so the corrected private report cannot be
  regenerated here - this is recorded as a required owner action for local verification (command in
  `docs/EVALUATION.md`), never committed.
- The new film is recorded from the deployed public v1.1 app after anonymous smoke tests; the social
  preview and end-card URL are preserved.

## Release gates (definition of done)

- [ ] Full public test suite + opt-in private seed acceptance run locally (owner-supplied seed);
      CI installs production UI dependencies and is green (tests py3.11/3.12, release checks,
      dependency audit, CodeQL, cloud-smoke).
- [ ] Community Cloud: root `app.py`, pinned requirements, Python 3.12; signed-out desktop/mobile
      load synthetic data, two sessions isolated; hosted evidence recorded.
- [ ] README shows actual version, tag, live URL and demo video; release downloads and Wiki match the
      new commit; stale authentication wording replaced and recorded-vs-independent checks clarified.
- [ ] Release commit/tag, data manifest, calibration report hashes, test and hosted browser
      evidence, video build report and acceptance pack (`docs/ACCEPTANCE_v1.1.md`) published; v1.0
      artifacts retained.

## Reporting

After each build step: what landed, remaining steps, failures/limitations, and expected actions from
the repository owner (for example: private seed path for the local corrected private report, review
of the new film, social-channel publication).

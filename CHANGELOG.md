# Changelog

Release notes per implementation step. TopoMarket identifies releases by step number and semantic
version; no release dates or schedules are published in repository content.

## v1.3.0 - Updated release-audit remediation: trustworthy guided walkthrough, media entry points and cross-platform evidence

Follow-up to the updated 26 November 2026 release audit. The research application is accepted; this
release corrects the guided demonstration, media/documentation and verification gaps and links one
named revision to the tested code, hosted app, film and evaluation report. Evidence:
`docs/ACCEPTANCE_v1.3.md`; plan: `docs/UPGRADE_v1.3.md`; epic #88.

- **Guided chronology (#77).** First guided stop renders Window A 2008-08-29 (29/66) then Window B
  2008-10-10 (66/66, +37 added/0 removed, mean r 0.791 -> 0.911); captions, cards, legend, edge
  colours and accessible table derive from the ordered result.
- **Mapper node identity (#78).** The selected Mapper node id is carried through state/persistence/
  cache; node-01 shows exactly 7 members, node-02 exactly 6; edges show real shared portfolios.
- **Late-alert classification (#79).** 2025-03-10 is a recorded post-onset late alert inside the
  frozen evaluation (episode onset 2025-03-06, zero early-warning credit, 2.02% max decline below the
  10% target); blind mode stays neutral.
- **Playback and captions (#80).** GitHub Pages signed-out player, README/Wiki links, and WebVTT/
  transcript/inline transcript generated from the reviewed SRT by `scripts/build_watch_assets.py`.
- **Public report provenance (#81).** Regenerated report carries import-manifest identity/digest,
  independent-calendar metadata, code revision and bootstrap v2; published metrics unchanged.
- **Documentation (#82/#83).** README two-window hero/citation, Wiki status merged into Roadmap,
  professional menu with Mathematics page, Methodology corrected (private TDA 0/9), KaTeX formatting
  and full-precision correlation boundary fixed.
- **Windows portability (#84).** Host-native path normalisation, POSIX canonical JSON, LF-pinned
  checksummed fixtures and a green windows-latest pytest + release-check job.
- **Performance and receipts (#85).** Fresh browser timing evidence (cached p95 497.6 ms, p50
  421.2 ms, cold start separately) and a sanitised owner-seeded private receipt; lazy inspection
  controls keep the rerun budget.
- **Corrected film (#86).** 60.000 s cut with the chronological pair, both topology plots during the
  Takens/H1 narration, enlarged outcome and large TDA 0/3 vs VIX 1/3 cards; checked-in builder and
  provenance (public URL, UTC, visible version, fixture, commit; documented capture deviation where
  the deployment was stale).
- **Release (#87).** v1.3.0 with Linux+Windows CI, hosted smoke, verified assets and preserved
  historical tags/artifacts.

## v1.2.0 - Release-audit follow-up: evaluation integrity, trustworthy Studio and public documentation

Focused follow-up to the 26 November 2026 release audit (`TopoMarket_Release_Audit_and_Improvement_Specification_EN.docx`).
The interactive market-structure demonstration is accepted; early warning stays explicitly experimental.
See `docs/ACCEPTANCE_v1.2.md` for the evidence matrix and `docs/UPGRADE_v1.2.md` for the plan.

- **R1 independent signal calendars (#55).** Price-based signals (S&P returns, TDA, realised
  volatility, labels, 20-session horizons) use the ordered index calendar; industry windows use their
  own table; VIX is joined by date for the comparison cohort only; old synthetic snapshots keep an
  explicit joint fallback. Reports/CLI expose separate as-of dates, sources and reasons; evaluation
  rows are the price calendar left-joined with VIX. Acceptance: appending only price/VIX dates past
  industry coverage extends the score and labels, and mutating only industry data leaves price
  scores/evaluation reports byte-identical. Owner-seeded run: 19,343 index rows through 2026-11-18,
  latest TDA score 2026-11-18 (baseline 2026-09-30), snapshot ID resolved, common eligible 3,220.
- **R2 bootstrap multiplicity (#56).** Blocks are drawn with replacement, concatenated and trimmed to
  N; identical position weights drive each method's frozen onset/false-alert indicators; exposure is
  fixed at N; algorithm identity `moving_block_with_replacement_v2`; intervals regenerated and
  versioned; duplicate-block/absent-event/shared-draw tests.
- **R3 CLI snapshot identity (#57).** Active pointer -> refresh manifest -> import manifest/content
  digest resolution with visible conflict failures; identity/source/manifest digest carried into
  reports, policies and ledger rows.
- **U1-U5 Studio trust fixes (#58/#59).** Explicit guided-tour start (no quiet-window mislabel) with the
  frozen retrospective 2008-08-29 (29/66) -> 2008-10-10 (66/66, +37/0) pair; blind replay blocks the
  comparative view; real edge-change encoding (removed amber dashed, added positive solid, legend,
  hover correlations); inline Structure reveal/hide of the 20-session outcome; reliable single-tap
  node/edge/Mapper targets.
- **Mathematics reference (#61).** `docs/MATHEMATICS.md` with corrected definitions, units, worked
  examples and links; correlation qualification now uses the full-precision value (six-decimal tag is
  display/provenance only).
- **Public presentation (#62).** Reader-first ~750-word README, honest 0/3 TDA vs 1/3 VIX holdout,
  browser-playable `docs/watch/index.html` with WebVTT captions/transcript/downloads, Wiki refresh.
- **New film (#63) and release (#65).** Re-recorded 60-second cut with hosted URL/UTC/version/fixture/
  commit manifest, WebVTT/SRT/captioned copy; v1.2.0 release assets; v1.0/v1.1 artifacts retained.
- No private data, credentials, ledgers or release dates are committed; private historical results
  stay outside the public repository.

## v1.1.0 - Acceptance-review release: auditable evidence, causal Replay and Market Structure Studio

Follow-up release implementing the v1.1 acceptance review (epic #48). See
`docs/ACCEPTANCE_v1.1.md` for the evidence matrix and `docs/UPGRADE_v1.1.md` for the plan.

- **WP-A evidence integrity (F01).** Calibration recall now counts unique matched episode onsets
  (the v1.0 code read a non-existent field and always reported zero recall); reports are versioned
  (`report_version 1.1`, `schema_version 2`) with provenance and a v1.0-baseline before/after
  comparison; the synthetic showcase was regenerated (validation recall is non-zero for VIX and
  realized volatility, holdout metrics/policies unchanged) and the Validation screen shows large
  per-method cards, a comparison chart and a details expander. Issue #37 closed.
- **WP-B causal blind Replay (F02).** Blind Replay and the Structure timeline derive alert state
  only from readings/policy/history at or before the selected session; neutral `Alert recorded`
  markers, no retrospective classifications/matches/onsets/outcome hints; review classifications are
  bounded to the revealed scope and flagged retrospective. Mutation and DOM-neutrality tests.
- **WP-C Market Structure Studio (F03).** Interactive Plotly landing frame with direct
  node/timeline box-selection and keyboard equivalents, three above-fold metrics, honest two-window
  comparison, guided Quiet -> Stress -> Explain -> Replay tour; Plotly 6.5 pinned and license-audited.
  Cached date-change browser p95 497 ms over 100 transitions (target 500 ms).
- **WP-D new film.** Re-recorded 60-second demo from the public v1.1 app with reviewed SRT,
  captioned playback variant, narration and editable production source.
- **Release.** Version bump to 1.1.0 with rebuilt frozen topology registry/showcase/presets; v1.0
  report retained as a baseline; README/Wiki updated; release assets and CI reports attached.
- No private data, credentials, ledgers or release dates are committed.

## v1.0.0 - Public release: structure, replay, cloud and demo video

Final release of the TopoMarket Upgrade and Demo Video Specification. See
`docs/ACCEPTANCE_v1.0.md` for the A01-A07 evidence matrix and `docs/UPGRADE.md` for the scope.

- **Public experience (v0.9.0).** Authoritative selected session with blind-replay integrity,
  independent S&P 500/VIX/industry calendars and source status, corrected chronological evaluation,
  Structure/Replay/Validation/Data screens, frozen demonstration presets and the synthetic showcase
  as the default public demo.
- **Cloud packaging (v0.9.0/v0.9.2).** Pinned Python 3.12 `requirements.txt` for Streamlit Community
  Cloud, no-flag `streamlit run app.py`, CI `cloud-smoke` job, and the Streamlit deployment contract
  in `docs/DEPLOYMENT.md`.
- **Demo video (v0.9.2).** 60 s 1920x1080 30 fps H.264/AAC master with reviewed English SRT,
  verified claims, editable production files and a re-runnable pipeline.
- **Performance (v1.0.0).** The shell keeps loaded data, screen payloads and rendered chart PNGs in
  session state; the Mapper window is built only when its view is visible; a browser measurement on
  the release candidate records **cached date-change p95 409 ms over 100 changes** against the
  500 ms target, with the first-visit/new-date and cold-start timings recorded separately
  (`docs/measurements/browser_performance.json`).
- **Evidence and notices.** Browser acceptance evidence and screenshots under `docs/measurements/`
  and `docs/assets/screenshots/`; MIT license and dependency audit (0 GPL/AGPL) documented in
  `NOTICE.md`/`docs/DEPENDENCY_LICENSES.md`; all published artifacts use the synthetic showcase only.
- **Known follow-ups.** Hosted signed-out verification and the final hosted smoke record depend on
  enabling anonymous access in the Cloud app settings; the deferred calibration-recall review is
  tracked in #37.
- No private data, credentials, ledgers or release dates are committed.

## v0.9.2 - Demo video and production assets

- **One-minute demo video (VD02).** 1920x1080 / 30 fps / H.264 High / AAC 48 kHz stereo master
  (60.0 s), reviewed English SRT captions, narration master, editable storyboard/narration/build
  pipeline and a production-source archive, published as release assets and linked from the README.
  The footage uses the synthetic showcase only, opens with the GitHub social preview and holds the
  exact repository URL for the final five seconds; every claim is verified against the released
  fixture in `docs/video/production_notes.md`. The specification's late-warning alternate line is
  used for the labelled teaching example because the frozen synthetic showcase has no
  evaluator-credited TDA alert.
- **Structure screen interaction fix.** The session date slider is now scoped to the selected date, so
  a preset/alert-jump/previous-next date change is no longer reverted by stale widget state on the
  next rerun (`tests/test_app.py`/AppTest coverage).
- **Mapper edge picker.** The Structure screen offers a keyboard-operable "Highlight Mapper edge"
  selector with the shared portfolios listed on screen and highlighted in the graph (UI02).
- **Mapper readability.** Group labels are enlarged for 1080p playback; click locations in the video
  are marked with a short amber highlight (headless capture has no visible cursor).
- Docs: README video links, `docs/video/` production files, acceptance A07 evidence and deployment
  status notes.
- No private data, credentials, ledgers or release dates are committed.

## v0.9.0 - Upgrade: Structure/Replay experience and evaluation integrity

- **One authoritative selected session (RE01).** The selected date is applied before any payload is
  built; history, network windows and alerts are sliced at the cutoff, blind replay no longer emits
  dates after it, and reveal state resets on navigation while the date persists across screens.
  Blind payload integrity is proven by mutation tests that rewrite every post-cutoff row.
- **Corrected chronological evaluation (EV01).** An alert is credited only when its own label is
  positive, its first breach belongs to the matched episode, and the episode onset is 1-20 sessions
  after the alert (one credit per episode; late/duplicate/pending/false classifications preserved).
  Average precision is computed over the complete eligible scored series with tie blocks (matches
  `sklearn.metrics.average_precision_score`); TDA, VIX and realized volatility are compared on common
  eligible dates; silent-policy fallback records the reason instead of a misleading threshold.
  Public synthetic report regenerated (scores byte-identical). Local private reference run:
  9 evaluable held-out episodes, 3,185 common eligible sessions, TDA recall 1/9, 13 false alerts =
  1.03/year, average precision 0.0494 (full series; alert-only value before the fix was 0.1625);
  frozen 99th-percentile policies and policy hashes unchanged; wording stays
  `Experimental market anomaly`. A calibration-recall defect found during the audit is documented as
  deferred for a follow-up recalibration review.
- **Independent observation calendars and source status (DA01).** The S&P 500 price calendar drives
  signal windows, labels and the replay horizon; VIX gaps stay gaps; the industry-return calendar can
  lag the price calendar and the map reports the date actually shown. The Data screen shows source
  coverage, last successful refresh, revisions, errors and the private-only validated refresh action;
  the public demo stays read-only and dependent scores invalidate on snapshot change.
- **Structure screen (UI01-UI04).** Landing experience with a warmed-up synthetic scene, four
  deterministic presets (quiet, stress transition, matched warning, missed/late), a fixed-layout
  12-industry Pearson correlation network (trailing 60 valid returns, fixed `r >= 0.80` cutoff,
  `n/66` pair count, node inspector), a Mapper view placed by volatility lens band with member
  inspector and shared-member edges, the shared S&P 500/VIX/score timeline with cursor, frozen
  threshold, alert markers and stale-map marking, and the score explanation (56-point Takens window,
  dim 3/lag 2, 2-D display-coordinate scatter, H1 birth-death diagram with the longest finite
  lifetime, industry PCA scatter).
- **Replay screen (RE01).** Blind score/price history, explicit reveal of the next 20 S&P 500
  sessions with origin close, 10% boundary, lowest close, first breach, maximum decline and pending
  state; hiding removes the payload.
- **Cloud packaging (CL01/CL02).** Python 3.12 Cloud definition `requirements.txt` (pinned Streamlit,
  analysis libraries and the matplotlib chart renderer), the public demo defaults to the 5,673-session
  synthetic showcase with no flags, deterministic payload caching (cached date-change p95 0.06 ms
  against the 500 ms budget), and a CI `cloud-smoke` job that installs the Cloud definition, imports
  the app, runs the plain demo and checks the Streamlit health endpoint.
- **Accessibility and visual behaviour.** Central theme tokens with WCAG AA contrast tests, teal
  market series / amber threshold, symbol+text alert marks, keyboard-operable inspectors, table/text
  alternatives for every chart, reduced-motion support and stable graph positions.
- **Notices, licensing and preview.** Issue #10 closed with the MIT confirmation and a dependency
  license audit (79 packages, 0 GPL/AGPL); `NOTICE.md` documents the software license and the
  synthetic-only publication rule; the 1280x640 GitHub social preview and 16:9 opening/end cards are
  generated from the synthetic fixture by `scripts/build_social_preview.py`.
- No private data, credentials, ledgers or release dates are committed.

## v0.8.2 - Operator UI replay visibility

- Overview renders a score-history timeline (recent scored sessions) with the frozen cutoff
  caption, so the landing screen exposes the research history instead of three sparse metrics.
- Replay at the latest available session explains that no future outcome horizon exists and guides
  the operator to an earlier session or a replay preset instead of a silent `0/20`.
- Sidebar replay presets jump to the documented historical alerts: 2020-03-16, 2020-03-13,
  2008-10-10, 2008-09-15.
- Explicit x/y chart columns fix the Streamlit mixed-type exception; real Streamlit AppTest against
  the showcase profile covers the chart and latest-session hint.
- Frozen topology config hash refreshed for the 0.8.2 package version.
- No private data, credentials, ledgers or release dates are committed.

## v0.8.1 - Operator UI replay visibility (superseded by v0.8.2)

- First patch of the operator UI: score-history preview and replay presets. Superseded by v0.8.2,
  which fixes the Overview chart construction and refreshes the frozen configuration hash.

## v0.8.0 - Step 8: Package and rehearse the public release

- Offline `topomarket release-check` command: version consistency, repository hygiene, packaged
  JSON resources, dependency lock, synthetic-fixture determinism, public-mode smoke commands and
  the committed synthetic showcase fixture.
- Clean-checkout release workflow building sdist/wheel, running `twine check`, retaining the test
  report and release artifacts.
- Dependency lock (`requirements.lock`), release runbook (`docs/RELEASING.md`) and a synthetic-only
  public walkthrough (`docs/WALKTHROUGH.md`) with a committed reproducible showcase fixture.
- License and data-source notices reviewed; README status updated for the completed release.
- No private data, credentials, ledgers or release dates are committed.

## v0.7.0 - Step 7: Interactive research dashboard

- Four-screen Streamlit dashboard (Overview, Topology, Validation, Data) over one persistent
  selection with blind replay safety, keyboard equivalents, accessible tokens/table alternatives/
  reduced motion and cached-performance benchmarks.
- Plain-text dashboard fallback without Streamlit; optional `[ui]` extra.

## v0.6.0 - Step 6: Chronological evaluation and warning evidence

- Labels/breach episodes, early/post-onset/false/missed alert matching, frozen alert policies with
  calibrated percentile cutoffs, out-of-sample evaluation metrics, paired moving-block bootstrap,
  controls/ablations, evidence wording and an append-only private ledger.

## v0.5.0 - Step 5: Industry explorer

- 60x12 industry cloud with robust scaling/PCA/Rips persistence, deterministic correlation-distance
  Mapper graph with overlapping volatility intervals, measurements, tooltips and a combined payload
  CLI.

## v0.4.0 - Step 4: Persistent homology and anomaly score

- Causal delay-embedding/Vietoris-Rips score with midrank percentile normalization, frozen
  configuration registry, warm-up/gap states, deterministic CSV export and the `topology` CLI.

## v0.3.0 - Step 3: Update and recovery

- Fixed-source HTTPS refresh with conditional GET/staging/validation, atomic immutable snapshots,
  revisions, single-writer lock, last-good recovery and the `refresh`/`sources` CLI.

## v0.2.0 - Step 2: Seed import

- Local seed adapters (OpenIntro, FRED, Cboe, Kenneth French, OFR), raw hash registry, parser
  reports, normalized tables (`sp500_daily`, `industries_daily`, `tda_daily`) and spec-aligned
  synthetic demo schema.

## v0.1.0 - Step 1: Runnable scaffold

- Python package/CLI, Streamlit shell, demo/private profiles, deterministic synthetic fixtures,
  snapshot manifest helpers, CI and security scanning.

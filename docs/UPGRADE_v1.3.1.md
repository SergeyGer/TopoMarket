# TopoMarket v1.3.1 plan (v1.3.0 acceptance-review patch)

Plan for `TopoMarket_v1.3.0_Acceptance_Review_EN.docx` (26 November 2026). The research demo is
accepted and the video is **owner-approved** (public copy: <https://youtu.be/8Xyp-BDM88Q>). Three
data-dependent UI errors plus interaction, visitor-path and evidence-reconciliation gaps remain; ship
one patch release (v1.3.1) and preserve the v1.3.0 record. Baseline: reviewed main `d688a42`, published
tag `v1.3.0` (`c65a9ed`), Wiki `d801e66`.

## Findings → work packages → issues

| # | Finding | Deliverable |
| --- | --- | --- |
| 97 | Manual two-window reverse order still substitutes the chronological `+37` sentence | Derive caption/cards/legend/edges/table from the ordered comparison; only the ordered 29 Aug -> 10 Oct direction gets the frozen retrospective label. Tests both directions. |
| 98 | One preset/tour/alert click updates charts but leaves the bound date control stale | Persist + rerun once after programmatic date changes, synchronising slider/header/accessibility/charts in the same render. Tests for preset, tour step and alert jump. |
| 99 | Replay threshold sentence hardcoded "below the target"; Structure duplicate late notice; fixed March dates | Compute the threshold sentence from breach/target/horizon; use the active alert record's onset/status; one notice; cases: below, reached (first breach + decline), pending, missing onset. |
| 100 | Mapper graph is static; plotted node click does not select | Interactive Mapper figure with node-id hit targets and keyboard equivalent; verify node-01/node-02 and shared Consumer durables. |
| 101 | README watch links open source; Wiki download opens player; missing YouTube link/owner approval | Reader links to Pages player; YouTube version; versioned release MP4 download; citation v1.3.0; record owner approval with master digest. |
| 102 | Stale version/report identity in README/Wiki/Mathematics/acceptance/plan | Reconcile public entry pages; pin/update Mathematics identity fields; versioned release evidence index with tag, generating revision, deployed version and media digests (incl. ZIP hash in an external manifest). |
| 103 | Hosted receipt lacks Replay/Validation/Data/Mapper assertions; timing predates lazy controls | Repair hosted checks on a named revision; fresh tagged-checkout timing with revision and separate cold start; update cue/timing receipts. |
| 104 | Patch release | v1.3.1 with verified assets, updated acceptance record, Linux+Windows CI and preserved historical tags. |

Milestone **Release v1.3.1 patch**.

## Order and gates

1. Data correctness: both comparison directions, one-click date sync, Replay threshold cases (chart,
   text, accessible value and inspector agree).
2. Interaction/visitor path: Mapper pointer selection; README/Wiki rendered links play the film with
   captions; dedicated MP4 download verified separately.
3. Consistent proof: hosted assertions on a named revision, regenerated cue/timing receipts,
   documentation reconciliation, release evidence index, owner approval against the master digest.

## Owner actions

- None blocking: video approved; the private seed/receipt is already supplied. Final sign-off on the
  v1.3.1 acceptance record after the patch release.

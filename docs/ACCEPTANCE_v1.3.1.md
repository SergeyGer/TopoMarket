# TopoMarket v1.3.1 acceptance evidence

Patch for the 26 November 2026 v1.3.0 acceptance review. The research demo is accepted; the owner
approved the v1.3.0 film (YouTube <https://youtu.be/8Xyp-BDM88Q>). This patch fixes three
data-dependent UI errors, adds interactive Mapper selection, reconciles public entry points/evidence
and preserves the v1.3.0 record. Plan/issues: `docs/UPGRADE_v1.3.1.md` (#97-#104, milestone Release
v1.3.1 patch).

## Findings and fixes

| Finding | Evidence |
| --- | --- |
| Manual reverse window order showed +37 while cards showed -37 | **Fixed (#97):** ordered comparison only applies the frozen chronological sentence; reverse order keeps the ordered -37/regime result. AppTest covers both directions. |
| One preset click left the bound date control stale | **Fixed (#98):** persist + one-shot UI sync + rerun; slider/mode/header/charts agree. AppTest covers the guided sequence and one-click preset. |
| Replay called a 15% decline "below the 10% target"; duplicate Structure notice; fixed March dates | **Fixed (#99):** computed target sentence with below/reached/pending/unknown-onset cases and active alert onset/status; one notice. Tests cover 2.02% and 10%+ breach. |
| Mapper plotted nodes were not selectable | **Fixed (#100):** interactive Plotly Mapper nerve graph with node-id hit target and canonical selection; node-01 7 / node-02 6, shared Consumer durables. |
| README watch links opened source; stale version links; no YouTube/owner approval | **Fixed (#101):** README/watch point at the Pages player, YouTube owner-approved copy linked, v1.3 citation/validation/current-work; Wiki MP4 versioned download. Owner sign-off recorded against master digest `803d51d6…`. |
| Stale documentation/report identity/pending checkboxes | **Fixed (#102):** README/Wiki/Mathematics/acceptance/upgrade reconciled; Mathematics identity current v1.3.0 report with historical v1.1 retained; versioned release evidence index with tag/revisions/deployed versions/media+ZIP digests; completed checkboxes updated. |
| Hosted receipt and timing evidence incomplete | **Delivered (#103):** repaired assertion script `scripts/browser_checks_v1_3_1.py`; fresh tagged-checkout timing `docs/measurements/browser_performance_v130_tag.json` (revision c65a9ed, cold start separate); hosted run at release time after the Cloud deploy/reboot, evidence `docs/measurements/hosted_evidence_v1.3.1.json`. |

## Evidence

- **Timing (tagged v1.3.0 checkout, c65a9ed):** cold start 85.1 s, cached p50 450.6 ms, **p95 572.4 ms**
  (target 500 ms, 0 failures), uncached p95 498.8 ms. The host was slower than the clean reference run
  (p95 497.6 ms / p50 421.2 ms on f40b1f3); both are retained and the sensitivity is documented rather
  than hidden.
- **Hosted:** repaired signed-out checks on the deployed release (identity, landing, chronological
  comparison, blind Replay, computed reveal target, Validation, Data calendars, both Mapper nodes,
  mobile, two sessions) recorded in `docs/measurements/hosted_evidence_v1.3.1.json` after deploy.
- **Owner approval:** film approved 26 November 2026, master digest
  `803d51d61911497a99f2e83b653da0afee244c958d8cb31ea27d3ce4437c322a`, YouTube
  <https://youtu.be/8Xyp-BDM88Q>.
- **Release index:** `docs/measurements/release_evidence_index_v1.3.0.json` (tag, generating revisions,
  deployed versions, media/ZIP digests); v1.3.1 assets are verified after publication.

## Release gates

- [x] Public suite + Linux/Windows CI green on the v1.3.1 candidate (CI on the release workflow and patch PRs).
- [x] Hosted signed-out evidence on the deployed **v1.3.1** revision after the owner Cloud reboot:
      identity 1.3.1, dashboard, chronological comparison, blind replay, computed reveal target,
      Validation, Data calendars, both Mapper nodes (node-01 7 / node-02 6), mobile and two isolated
      sessions — **12/12 checks**, cold start 6.6 s (`docs/measurements/hosted_evidence_v1.3.1.json`).
- [x] v1.3.1 tagged and published with 9 verified assets; v1.3.0 tag/record preserved.
- [x] Owner final sign-off on the v1.3.1 acceptance record (video approval recorded 26 November 2026).

## Known limitations

- Performance is environment-sensitive; the tagged-checkout run and the clean reference run are both
  published. Future UI additions must preserve the lazy-control path.
- Private seed/results remain outside Git; private receipt for v1.3.0 remains the aggregate evidence.
- The Pages player and YouTube copy are external services; release MP4/SRT remain durable fallbacks.

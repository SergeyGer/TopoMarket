# TopoMarket v1.3 plan (updated v1.2.0 release remediation)

Plan for `TopoMarket_v1.2.0_Updated_Release_Audit_and_Remediation_EN.docx` (26 November 2026).
Decision from the audit: **accept the research application**, correct the guided demonstration and the
media/documentation/verification gaps, then ship **one named follow-up release** so tested code, hosted
app, film and evaluation report refer to one identifiable revision. Baseline: `main` `9398133`
(PR #76), published release/tag `v1.2.0` at `ea93bf4`, Wiki reviewed at `56de76c`.

## Findings → work packages → issues

| # | Audit finding | Deliverable |
| --- | --- | --- |
| 77 | Guided comparison runs backwards (A=10 Oct 66/66, B=29 Aug 29/66, −37) | earlier date A, later B, ordered captions/cards/legend/edges/table; hosted per-card assertions (+37/0) |
| 78 | Mapper `node-01 · 7` resolves node-02 and shows 6 members | carry selected node ID in session state; pointer + keyboard select same node; edge shows shared portfolios; exact node/member acceptance |
| 79 | 2025-03-10 called "outside the evaluation" but is a recorded post-onset late alert (episode 6 Mar, zero early credit) | derive classification/credit from released report; neutral blind, post-onset late wording after reveal; align preset help/film notes/Wiki |
| 80 | README/Wiki watch links open HTML source or download-attachment MP4; captions/transcripts stale | real signed-out browser playback page; README+Wiki links; regenerate WebVTT/both transcripts from final cues; desktop/phone caption+seek checks |
| 81 | Public report has empty `snapshot_provenance` and old code revision | regenerate through release procedure with identity/digest/calibration comparison/bootstrap id; assert non-empty and metrics unchanged |
| 82 | README hero 56/66 Feb-2020 vs caption 2008; citation v1.1.0; Wiki stale status/Methodology TDA 1/9; menu | two-window hero+alt text; versioned citation; merge Home Status table into Roadmap; professional menu incl. Mathematics page; corrected Methodology; dated incident retained |
| 83 | GitHub math macros disallowed (`\operatorname`) and raw `$$`; §5.1/§7.5 still describe rounded-tag qualification | KaTeX-allowed formatting; full-precision boundary rule + table; network-builder boundary test |
| 84 | Windows checkout: 8 failures (path separators, canonical JSON, home-dir test, CRLF fixture digests) | normalise relative path components/stable separators; isolate Windows dir vars; `.gitattributes` for checksummed fixture; Windows CI pytest + release check |
| 85 | Timing file stale; private receipt on older candidate; acceptance notes stale | fresh 100-transition timing per run (env, commit, cold start, p95); private suite + sanitised receipt on chosen candidate; acceptance status sync |
| 86 | Film reversed shot, PCA scroll over topology narration, dense results, builder mismatch, tag manifest older than assets | UI fixes first; record corrected public app; hold embedding+H1; large TDA 0/3 vs VIX 1/3; checked-in builder; manifest URL/UTC/revision/fixture/digests; cues 00:16/00:30/00:46/00:52 |
| 87 | No single named revision connecting code/app/film/report | v1.3.0: bump, frozen artifacts, Windows+Linux CI, hosted smoke, published acceptance record, verified assets, preserved historical tags |

Epic **#88**, milestone **Release v1.3**.

## Order and gates (from the audit)

1. **Chronological comparison** (#77) — fresh hosted session shows Aug 29 first, Oct 10 second, 29→66,
   +37/0; text, colours and accessible table agree.
2. **Mapper + alert explanation** (#78/#79) — pointer/keyboard select exactly 7 or 6 members; March 10
   neutral until reveal, then post-onset + zero early credit.
3. **Cross-platform and data verification** (#81/#84/#85) — Windows and Linux release runs green with
   documented intentional skips; populated provenance; owner private run/receipt on the same candidate;
   fresh timing.
4. **Hosted film and assets** (#86) — corrected public deployment; both topology plots visible during
   narration; 2.02% and 10% boundary; large TDA 0/3 vs VIX 1/3; derived versions/captions.
5. **Viewer entry points + documentation** (#80/#82/#83) — README and Wiki both open a signed-out
   player; WebVTT/SRT/transcripts/audio agree; math example, release status, hero and citation fixed.
6. **Published acceptance record** (#87) — download published files, verify hashes against the
   versioned manifest, check cues at 00:16/00:30/00:46/00:52, preserve approved revision and record
   owner sign-off.

## Evidence contract

- No private data/seed in Git; private aggregates/receipts are sanitised and stored outside the repo.
- Public report regenerated with the release procedure and populated input provenance; metrics must
  stay at the published precision (TDA 0/3 AP 0.0154; VIX 1/3 0.1187; realised vol 0/3 0.0556;
  3,306 common eligible sessions).
- Hosted tests assert content inside named cards (not only headings) and the sign/date of the change.
- Film media versions derive from one edit; both captions and transcripts derive from the final
  narration cues; release assets and manifest live on one identifiable revision (historical tags
  preserved; release explicitly linked to corrected manifest or shipped as v1.3.0).

## Owner actions pending

- **Private seed run/receipt** on the chosen release candidate (`TOPOMARKET_SEED_DIR`), sanitised
  aggregate only.
- **Film sign-off** after the corrected public-deployment recording.
- **Streamlit Cloud**: keep the app on the selected release revision; report/redeploy if the wrapper
  page becomes stale again.

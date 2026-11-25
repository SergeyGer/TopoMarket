# v1.0 upgrade plan: market structure, replay integrity and the one-minute demo

Implementation plan for the *TopoMarket Upgrade and Demo Video Specification*
(24 November 2026) on top of the released v0.8.2 baseline (commit `20b51da`).

Tracking: milestone **Upgrade v1.0** (GitHub milestone #10) and epic issue
[#22](https://github.com/SergeyGer/TopoMarket/issues/22). Every workstream below
has its own issue; all changes land through reviewed pull requests with green CI
and the `main-guard` audit workflow.

## 1. Baseline and defects

The baseline is the v0.8.2 operator dashboard: a four-screen Streamlit shell
(Overview, Topology, Validation, Data) over one persistent selection, a private
research profile, and a committed synthetic showcase fixture. The specification
records these concrete defects that this upgrade closes:

| # | Baseline defect | Fix |
| --- | --- | --- |
| D1 | Overview draws one percentile series only | UI03: separate S&P 500, VIX and score panels with shared cursor |
| D2 | PCA coordinates rendered as line series | UI03: 2D scatter of the industry cloud; line-series misuse removed |
| D3 | Mapper rendered as counts and a table | UI02: Mapper graph placed by volatility band with inspector |
| D4 | Blind Replay can show dates after the selected session | RE01: slice history/features by authoritative selected session |
| D5 | Short default demo cannot populate the topology window | UI01/CL02: default public profile uses the 5,673-session showcase fixture |
| D6 | Evaluation matching credits 1 of 9 held-out episodes | EV01: corrected early-alert credit and average precision; regenerated reports |

## 2. Deliverables

1. Tagged release with a public Streamlit Community Cloud URL and a
   one-command local public demo.
2. Synchronized **Structure** and **Replay** experience, score explanation,
   evidence view and source status view; the private seed stays available for
   local research and refresh.
3. GitHub social preview, captioned video master, separate English captions,
   editable production files, README links to the app and the video.

Out of scope (explicit in the specification): optional 3D views and new
predictive models. The 12 industry portfolios and the existing TDA engine are
retained.

## 3. Workstream issues

| Spec | Issue | Scope | Release |
| --- | --- | --- | --- |
| UI01 | [#23](https://github.com/SergeyGer/TopoMarket/issues/23) | Default public Structure experience + frozen presets | v0.9.0 |
| UI02 | [#24](https://github.com/SergeyGer/TopoMarket/issues/24) | Correlation network + Mapper view | v0.9.0 |
| UI03 | [#25](https://github.com/SergeyGer/TopoMarket/issues/25) | Shared timeline + score explanation | v0.9.0 |
| UI04 | [#26](https://github.com/SergeyGer/TopoMarket/issues/26) | Visual behaviour + accessibility | v0.9.0 |
| RE01 | [#27](https://github.com/SergeyGer/TopoMarket/issues/27) | Authoritative selected session + blind replay | v0.9.0 |
| DA01 | [#28](https://github.com/SergeyGer/TopoMarket/issues/28) | Independent calendars + source status | v0.9.0 |
| EV01 | [#29](https://github.com/SergeyGer/TopoMarket/issues/29) | Corrected evaluation + regenerated reports | v0.9.0 |
| CL01 | [#30](https://github.com/SergeyGer/TopoMarket/issues/30) | Cloud entrypoint + pinned dependencies | v0.9.1 |
| CL02 | [#31](https://github.com/SergeyGer/TopoMarket/issues/31) | Showcase bundle + cached performance | v0.9.1 |
| CL03 | [#32](https://github.com/SergeyGer/TopoMarket/issues/32) | Deployment + operational handoff | v1.0.0 |
| VD01 | [#33](https://github.com/SergeyGer/TopoMarket/issues/33) | Social preview + end card | v0.8.3, v1.0.0 |
| VD02 | [#34](https://github.com/SergeyGer/TopoMarket/issues/34) | 60-second video, narration, captions, assets | v0.9.2 |
| ACC | [#35](https://github.com/SergeyGer/TopoMarket/issues/35) | Acceptance evidence A01-A07 | v1.0.0 |

## 4. Build sequence and releases

| Step | Implementation output | Exit evidence | Release |
| --- | --- | --- | --- |
| 0 | Plan, issues, social preview, license/data-notice audit | This document, committed preview asset, closed issue #10 | v0.8.3 |
| 1 | Date state, independent calendars, evaluation correction | Regression tests, regenerated public/private reports, source coverage | v0.9.0 |
| 2 | Network, timeline, inspectors, replay states | Payload + interaction tests, desktop/mobile captures | v0.9.0 |
| 3 | Showcase package, Cloud dependency definition, release candidate | Clean-clone run, anonymous session candidate | v0.9.1 |
| 4 | Frozen demonstration presets, video capture and captions | Fixture/commit/script agree with footage; SRT review | v0.9.2 |
| 5 | Final release: tag, README/Wiki links, hosted verification | All links and preview verified | v1.0.0 |

## 5. Architecture of the upgrade

The v0.8.2 shell separates pure payload builders (`ui/panels.py`), selection
state (`ui/dashboard.py`) and rendering (`app.py`). The upgrade keeps that
boundary and adds:

| Module | Purpose |
| --- | --- |
| `analysis/network.py` | Deterministic 12-node Pearson correlation network payload (fixed layout, r cutoff, 66-pair accounting, inspector values, replay-safe windowing). Shared by the UI, the social preview and the video fixtures. |
| `ui/structure.py` (planned) | Structure-screen payload: network view, Mapper view, timeline panels, Takens/embedding/H1 explanation, PCA scatter. |
| `ui/replay.py` (planned) | Blind/reveal payload with origin close, 10% boundary, lowest close, first breach, maximum decline, pending state. |
| `ui/charts.py` (planned) | Matplotlib/Altair rendering helpers used by the Streamlit shell; deterministic and testable without Streamlit. |
| `ui/presets.py` (planned) | Frozen demonstration presets (quiet, stress transition, matched warning, missed/late warning) with fixture IDs and verified dates. |

New screens: **Structure** (landing), **Replay**, **Validation**, **Data**. The
previous Overview and Topology screens are folded into Structure/Replay; the
selection model keeps one authoritative date for every panel (RE01).

Scientific honesty: the score percentile is shown as a *comparative* score, the
forecast is labelled an experiment, and the wording stays
`"Experimental market anomaly"` unless the evidence rule is satisfied.

## 6. Public data policy

- `showcase/` is fully synthetic (seed 4242, fixture `showcase-synthetic`) and is
  the only data used by the public app, README examples, screenshots and video.
- Genuine provider data stays outside GitHub (`private_data/`, git-ignored). The
  provider terms in `NOTICE.md` keep applying to any genuine data, charts or
  derivatives.
- MIT remains the code license; the dependency audit (`docs/DEPENDENCY_LICENSES.md`)
  confirms no GPL/AGPL dependency.
- Issue #10 (license and data-source notices) is resolved with the audit and the
  synthetic-only enforcement described above.

## 7. Acceptance evidence

The required regression checks A01-A07 from the specification are collected in
issue [#35](https://github.com/SergeyGer/TopoMarket/issues/35) and linked from
each release. Evidence artifacts live in `docs/` (reports, accessibility,
deployment, video production notes) and in CI runs; no genuine market data is
used in any evidence artifact.

## 8. User actions required

The repository owner (not automatable in this checkout):

1. Upload `docs/assets/social_preview.png` in GitHub → Settings → Social preview
   (the file is committed and regenerable with `scripts/build_social_preview.py`).
2. Create the Streamlit Community Cloud app from the released branch
   (`main`, entrypoint `app.py`) and share the public URL so it can be recorded
   in the README/release.
3. Upload/publish the video asset if the selected video host is not GitHub
   Releases, and confirm the final preview/video links after publication.

## 9. Risks

- Community Cloud deployment needs the owner's Streamlit account; the release
  documents the exact branch, SHA, Python version and smoke-test procedure.
- The demo video must be recorded from the real hosted/streamlit app with
  actual interactions; the production pipeline is scripted, but the final
  approval (claims, captions, timing) belongs to the owner.
- Evaluation corrections change the reported holdout numbers; both the public
  synthetic report and the local private report are regenerated and their
  digests recorded so the video and docs quote consistent evidence.

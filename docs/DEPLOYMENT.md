# Hosted release: Streamlit Community Cloud

This page records the operational contract for the public TopoMarket demo, the deployment
identity, the smoke checks and the rollback rule (CL03). No credentials or secrets live in the
repository; the Cloud app is read-only with respect to provider data.

## Deployment identity

| Item | Value |
| --- | --- |
| Host | Streamlit Community Cloud (`share.streamlit.io`) |
| Public URL | <https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/> |
| Repository / branch | `SergeyGer/TopoMarket` / `main` |
| Entrypoint | root `app.py` (no flags; defaults to the synthetic showcase) |
| Python | 3.12 (pinned in the Cloud app settings and in the CI Cloud smoke job) |
| Dependency definition | root `requirements.txt` (pinned runtime/UI subset) |
| Development lock | `requirements.lock` (runtime UI + development tools) |
| Data | committed synthetic `showcase/` fixture only (`synthetic: true`, snapshot `showcase-synthetic`) |
| Secrets | none |
| App created | 2026-11-25 by the repository owner |
| First accepted release | `v0.9.0` |

The app redeploys automatically from `main` after every merge. A release is only "accepted" once
the hosted smoke checks below pass on the merge commit; otherwise the deployment branch is reverted
to the last accepted commit through a normal pull request (never by force-push).

## Dependency discovery

Streamlit Community Cloud installs the root `requirements.txt` on Python 3.12. That file is
generated from the `[ui]` extra of `pyproject.toml`:

```bash
python3 -m venv /tmp/tm-cloud-venv
/tmp/tm-cloud-venv/bin/pip install -e ".[ui]"
/tmp/tm-cloud-venv/bin/pip freeze --exclude-editable | sort
```

It is pinned and audited offline by `scripts/audit_dependency_licenses.py` (0 GPL/AGPL; see
`docs/DEPENDENCY_LICENSES.md`). The local package is imported from `src/` by `app.py`, so the
package itself is not listed in `requirements.txt`. The CI `cloud-smoke` job installs exactly this
file, imports the app, runs the plain demo and checks the Streamlit health endpoint.

## Local Cloud-like verification

```bash
# 1. Clean Python 3.12 environment with only the effective Cloud definition.
python3 -m venv /tmp/tm-cloud-check
/tmp/tm-cloud-check/bin/pip install --upgrade pip
/tmp/tm-cloud-check/bin/pip install -r requirements.txt

# 2. Plain public demo: no private data, no flags, no network.
python app.py -- --profile demo

# 3. Streamlit entrypoint.
python -m streamlit run app.py --server.headless true --server.port 8599
curl -sf http://127.0.0.1:8599/_stcore/health
```

## Hosted smoke checklist (signed out)

Record the date, URL, branch, full SHA and Python version with the result.

- [ ] Cold start: the URL opens signed out and shows **Structure** with the synthetic badge.
- [ ] Presets: quiet, stress transition, matched (or labelled teaching example), missed/late.
- [ ] Graph inspection: select an industry; incident edges and pair values update.
- [ ] Mapper view: switch view, inspect a node and an edge's shared portfolios.
- [ ] Blind Replay: reveal the 20-session outcome, then hide it; changing date resets the reveal.
- [ ] Validation: evidence wording, sample size, false-alert rate and CSV export.
- [ ] Data: independent calendars and read-only public status.
- [ ] Mobile layout (390 px): panels stack and the node inspector is reachable below the map.
- [ ] Version identity in the app sidebar matches the tested release tag.
- [ ] Two independent browser sessions do not share selection state.

The app must be publicly viewable before the signed-out checks can complete. The owner reported
selecting **"This app is public and searchable"** in App settings -> Sharing, but anonymous HTTP
requests still receive a 303 redirect to `share.streamlit.io/-/auth/app` (checked repeatedly on
2026-11-25, including after v0.9.0 was merged). Action required from the owner: press **Save
changes** in the App settings -> Sharing dialog and, if the setting does not take effect within
about ten minutes, use **Reboot app** from the app menu. Then run the checklist above and record
the result in this log. Local release-candidate evidence for the same screens is in
`docs/assets/screenshots/`.

## Rollback

1. If a hosted check fails, open a revert PR against `main` restoring the last accepted release
   commit (for example `git revert <merge-sha>` or a `release/*` revert branch).
2. Merge it through the normal protected-branch flow; Cloud redeploys automatically.
3. Re-run the smoke checklist; record the outcome here and in the release notes.

## Deployment log

| Date (UTC) | Release | Commit | Result |
| --- | --- | --- | --- |
| 2026-11-25 | app created | `main` at v0.8.2 baseline | app created by owner; anonymous access currently restricted (sharing setting) |
| 2026-11-25 | v0.9.0 | `4f3a1c6` (main) | badge/version 0.9.0 deployed by the owner's Cloud app; anonymous access still redirects to login |
| 2026-11-25 | v0.9.2 | video/docs release | demo video recorded locally from the release candidate because anonymous hosted access was still gated; hosted checks pending |
| 2026-11-25 | v1.0.0 | release candidate (1.0.0) | local signed-out-equivalent checks, session isolation, mobile/keyboard and cached performance evidence recorded (`docs/ACCEPTANCE_v1.0.md`, `docs/measurements/`); hosted signed-out check still blocked by the sharing setting |

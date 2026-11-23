# Release runbook

This document covers the repeatable release rehearsal for TopoMarket. Releases are identified by
step number and semantic version (`v0.x.0`); no release dates or schedules are published in
repository content.

## Checklist

1. **Version consistency** - `pyproject.toml` and `topomarket.__version__` match; `CHANGELOG.md` has
   an entry for the version. `topomarket release-check` verifies this.
2. **Repository hygiene** - `private_data/`, `.adp-inputs/`, credentials, local data artifacts,
   ledgers and caches are untracked and covered by `.gitignore`; `release-check` fails on tracked
   private inputs or forbidden names.
3. **Packaged resources** - `topomarket.data/demo_markets.json` and
   `topomarket.topology/topology.json` are included in wheels/sdists and load from the installed
   package (not only from a source checkout). The wheel content check in the release workflow
   asserts this.
4. **Dependency lock** - regenerate `requirements.lock` in a fresh environment:
   ```bash
   python -m venv /tmp/tm-lock
   /tmp/tm-lock/bin/pip install --upgrade pip
   /tmp/tm-lock/bin/pip install -e ".[dev]"
   /tmp/tm-lock/bin/pip freeze --exclude-editable | grep -v '^topomarket' | sort > requirements.lock
   ```
   The lock contains pinned runtime and development tools; the optional `[ui]` extra (Streamlit) is
   installed separately for dashboard runs.
5. **Synthetic fixtures** - `topomarket synthetic --seed 42` is byte-deterministic across two runs;
   the committed `showcase/` fixture matches its `manifest.json` hashes.
6. **Offline public smoke** - `topomarket demo`, `synthetic`, `validate`, `status` and
   `python app.py --profile demo` succeed without credentials or network; `release-check` runs this.
7. **Test report** - the release workflow runs the public suite with
   `--junitxml=test-report.xml` and retains it (and the built distributions) as CI artifacts.
8. **Build artefacts** - the release workflow builds `sdist` + wheel with `python -m build`, runs
   `twine check dist/*`, verifies packaged JSON resources and uploads both artifacts.
9. **Private rehearsal** - the opt-in private acceptance imports the real seed, refreshes with the
   real bytes and recovers from a failed required refresh; it is never run with private data in
   public CI.
10. **Publish** - merge through the protected `main` PR, tag the squash commit
    (`git tag v0.x.0 && git push origin v0.x.0`), publish release notes from `CHANGELOG.md`, close
    the step issue/milestone and update the Wiki roadmap.

## Commands

```bash
rust-free local verification:
python -m compileall -q src tests app.py
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m topomarket release-check

# artefacts
python -m pip install build twine
python -m build
python -m twine check dist/*
```

## Public demo

The public walkthrough uses synthetic data only: see [WALKTHROUGH.md](WALKTHROUGH.md). The committed
`showcase/` fixture is synthetic, deterministic and safe to publish; private data, genuine market
screenshots and derived tables must follow the provider notices in `NOTICE.md`.

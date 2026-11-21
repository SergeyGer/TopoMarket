# TopoMarket

TopoMarket is a personal open-source research application that shows how the shape of US equity
returns changes over time and tests whether those changes precede a sharp fall in the S&P 500.
For each available US market close it computes a topological anomaly score; the owner can trace a
reading back to the returns that produced it, replay a historical episode session by session, and
compare warnings with simpler indicators.

The forecast target is fixed before evaluation: a fall of at least **10% from the selected close
within the next 20 index sessions**. The application ships with a credential-free synthetic demo
and a private-research profile; a working dashboard and a positive forecasting result are separate
release decisions.

## Status

| Step | Scope | State |
| --- | --- | --- |
| 1 | Runnable scaffold: package/CLI, Streamlit shell, demo/private profiles, deterministic synthetic fixtures (seed 42), snapshot manifests, CI | **Delivered** |
| 2 | Import the supplied local seed files: four core adapters + optional OFR, hash registry, parser reports, normalized tables (A2) | Next |
| 3 | Update and recovery paths: HTTPS refresh, conditional GET, atomic snapshot publication, revisions (A3) | Planned |
| 4 | Persistent homology: delay embeddings, H0/H1, midrank scores, frozen configurations (A4) | Planned |
| 5 | Industry explorer: 60×12 cloud and Mapper graph (A5) | Planned |
| 6 | Chronological evaluation: labels, events, alert policy, uncertainty, private ledger (A6) | Planned |
| 7 | Interactive dashboard: four screens, global date selection, accessibility (A7) | Planned |
| 8 | Package and rehearse the GitHub release (A8) | Planned |

Detailed acceptance criteria live in the GitHub Issues and milestones for each step.

## Quickstart

Requirements: Python 3.11+, `git`.

```bash
git clone https://github.com/SergeyGer/TopoMarket.git
cd TopoMarket
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Run the deterministic synthetic demo (no network, no credentials, no private data):

```bash
topomarket demo
topomarket demo --json

# Streamlit shell (synthetic demo profile)
streamlit run app.py -- --profile demo
```

CLI reference:

```bash
topomarket --help
topomarket info --profile demo
topomarket synthetic --out ./demo-data --seed 42
topomarket status --data-dir ./demo-data
topomarket validate --data-dir ./demo-data
```

## Profiles

- **demo** - fully synthetic, reproducible market data generated locally with seed 42. All charts
  and identifiers in this profile are marked as synthetic.
- **private** - local research against user-supplied data under a user-controlled directory
  (`TOPOMARKET_DATA_DIR` or `--data-dir`, default outside the checkout). The private seed archive
  is never committed and is not part of this repository.

Private inputs, local snapshots, caches and environment files are excluded by `.gitignore`; a scan
of tracked files is part of CI.

## Quality and security

- CI runs linting, compilation and tests on Python 3.11 and 3.12.
- Security workflows: dependency audit (`pip-audit`), static analysis (`bandit`), secret scanning
  (`detect-secrets`) and CodeQL.
- `main` is protected: changes arrive through pull requests with green checks and are squash-merged
  (linear history); direct pushes and force pushes are rejected. `main-guard` provides an
  independent audit signal.
- See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## Data notices

The public demo uses project-generated synthetic data only. Private research data comes from
third-party providers and is **not** redistributed by this repository:

- OpenIntro / Yahoo Finance S&P 500 daily observations
- Federal Reserve Bank of St. Louis (FRED) S&P 500 series (S&P Dow Jones Indices rights apply)
- Cboe Global Markets spot VIX history
- Kenneth R. French Data Library 12 Industry Portfolios
- Office of Financial Research Financial Stress Index

Provider terms must be reviewed before publishing genuine market data, screenshots or derived
products. See [NOTICE.md](NOTICE.md) for attribution and usage notes.

## License

MIT - see [LICENSE](LICENSE).

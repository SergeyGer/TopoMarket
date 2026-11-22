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
| 2 | Import the supplied local seed files: four core adapters + optional OFR, hash registry, parser reports, normalized tables (A2) | **Delivered** |
| 3 | Update and recovery paths: HTTPS refresh, conditional GET, staging/validation, atomic snapshot publication, revisions and last-good recovery (A3) | **Delivered** |
| 4 | Persistent homology: delay embeddings, H0/H1, midrank scores, frozen configurations (A4) | **Delivered** |
| 5 | Industry explorer: 60×12 cloud and Mapper graph (A5) | **Delivered** |
| 6 | Chronological evaluation: labels, events, alert policy, uncertainty, private ledger (A6) | Planned |
| 7 | Interactive dashboard: four screens, global date selection, accessibility (A7) | Planned |
| 8 | Package and rehearse the GitHub release (A8) | Planned |

Detailed acceptance criteria live in the GitHub Issues and milestones for each step; the technical reference is the [project Wiki](https://github.com/SergeyGer/TopoMarket/wiki).

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

## Industry explorer (Step 5)

`topomarket industries` builds both Step 5 products from the same validated
60-session window: the robust industry cloud/PCA/H0-H1 persistence result and
the correlation-distance Mapper graph. It resolves the active snapshot exactly
like `topomarket topology` and reads only `normalized/tda_daily.csv` from that
directory; it never downloads data and never uses a fixed private-data path.
`industry` is accepted as a command alias.

```bash
# Latest complete window in the active snapshot.
topomarket industries --data-dir /path/to/data

# Explicit window end date, JSON payload, and deterministic file output.
topomarket industries --data-dir /path/to/data --date 2020-03-16 --json
topomarket industries --data-dir /path/to/data --date 2020-03-16 \
  --out industry.json
```

`--date` (also `--as-of`) must name a date present in `tda_daily.csv`; without
it the command skips any trailing rows whose industry cells are incomplete and
selects the latest complete 60-session window. Missing tables, unavailable
windows, an unknown date, or malformed industry columns exit with status `2`.

The combined JSON payload contains the window summary (`as_of`, `start_date`,
`end_date`, `window_sessions`, `industry_columns`, `industry_labels`, `dates`,
`row_count`) plus nested `cloud` and `mapper` payloads, node/edge/interval
counts, and the resolved active snapshot id. JSON stdout is sorted-key and
deterministic. `--out` writes the same UTF-8, LF-only, sorted-key JSON with a
trailing newline. The public `topomarket.analysis.industry_explorer_payload`
helper returns the same combined structure without the CLI-only directory
fields.

The Mapper normally uses three inclusive volatility intervals. When every
industry has the same annualised sample volatility, the lens has zero width and
the edge case collapses to one inclusive interval instead of three identical
zero-width copies. See [docs/INDUSTRY_EXPLORER.md](docs/INDUSTRY_EXPLORER.md)
for the full Step 5 contract, payload shapes and offline data handling.

## Data contracts

Both profiles materialise the same three normalized analysis tables. The
canonical definitions live in `src/topomarket/data/schemas.py`; every import
also writes the machine-readable contract to `normalized/schemas.json`.

### `sp500_daily`

| Column | Type | Unit / meaning |
| --- | --- | --- |
| `date` | date | ISO-8601 observation date |
| `sp500_close` | float | Index closing level in index points |
| `price_source` | string | `openintro`, `fred`, or `synthetic` (demo) |
| `sp500_log_return` | float | Natural log of the simple close-to-close return |

When both series are present, OpenIntro is authoritative through the source
cutover and observed FRED closes are used after it. Log returns are computed
from the previous observed close and remain empty when it is unavailable.

### `industries_daily`

One row per trading date, with one decimal simple-return column per standard
industry portfolio:

| Column | Type | Unit |
| --- | --- | --- |
| `date` | date | ISO-8601 observation date |
| `ind_nodur_return` | float | decimal simple return |
| `ind_durbl_return` | float | decimal simple return |
| `ind_manuf_return` | float | decimal simple return |
| `ind_enrgy_return` | float | decimal simple return |
| `ind_chems_return` | float | decimal simple return |
| `ind_buseq_return` | float | decimal simple return |
| `ind_telcm_return` | float | decimal simple return |
| `ind_utils_return` | float | decimal simple return |
| `ind_shops_return` | float | decimal simple return |
| `ind_hlth_return` | float | decimal simple return |
| `ind_money_return` | float | decimal simple return |
| `ind_other_return` | float | decimal simple return |

Source returns in percent are divided by 100 exactly once; consumers always see
decimal returns.

### `tda_daily`

`tda_daily` has `date`, `sp500_close`, `sp500_log_return`, and `vix_close`
followed by the twelve `ind_*_return` columns above. `vix_close` is in VIX index
points; the industry columns keep their decimal simple-return unit.

The table is an exact-date inner join of the index, industry, and VIX series.
Dates absent from any required series are dropped, and missing cells remain
empty; there is no forward fill or interpolation. All tables are sorted by
`date`, use the canonical column order, and are written as deterministic
UTF-8/LF CSV so identical inputs produce byte-identical output.

## Importing local seed data

`topomarket import` is an offline command: it never downloads data and never
reads credentials. It accepts a local directory, zip archive, or single file and
writes the source tables, normalized analysis tables, raw hash registry, parser
reports, and an import manifest.

Required source ids are `openintro_sp500`, `fred_sp500`, `cboe_vix`, and
`french_12_industries`; `ofr_fsi` is optional. Provider aliases such as
`openintro`, `fred`, `cboe`, `french`, and `ofr` are accepted by `--require`.

```bash
# Directory of supplied seed files. With --profile private the output defaults
# to the profile's artifacts/private directory.
topomarket import --profile private --input-dir /path/to/seed \
  --require openintro_sp500 --require fred_sp500 \
  --require cboe_vix --require french_12_industries

# Zip archive, treating unrecognised or unparseable files as errors.
topomarket import --profile private --input-zip /path/to/seed.zip --strict

# Single file with an explicit output directory and JSON summary.
topomarket import --input /path/to/seed.csv \
  --output-dir ./artifacts/private --json
```

`--registry` and `--reports` override the default registry and parser-report
paths. Without `--strict`, unrecognised files are recorded as warnings and the
recognised sources are still imported.

An import writes:

- `<source_id>.csv` source tables, mirrored under `normalized/`;
- `sp500_daily.csv`, `industries_daily.csv`, and `tda_daily.csv`, also mirrored
  under `normalized/`;
- `normalized/schemas.json` and `normalized_tables.json` with columns, types,
  units, row counts, and observation ranges;
- `raw_hashes.json` (plus the `raw_hash_registry.json` alias) with SHA-256
  digests of every input file;
- `parser_reports.json` and `reports/<source_id>.json`; and
- `import_manifest.json` with a content-addressed `snapshot_id`, source ids,
  warnings, errors, normalized row counts, and output checksums.

The lower-level compatibility entry point performs the same offline import:

```bash
python -m topomarket.data.adapters --input-dir /path/to/seed \
  --output-dir ./artifacts/private
```

Private inputs and import output belong outside the repository. Keep seed files
under `private_data/` or another local directory; `artifacts/` and
`private_data/` are ignored by git.

## Reports and validation

`topomarket report` prints per-source row counts, observation ranges, parser
warnings, normalized table row counts, and the active snapshot id. Use
`--data-dir` for an explicit directory, or `--profile private` to report on the
profile's import output when it exists.

```bash
topomarket report --data-dir ./artifacts/private
topomarket report --profile private
topomarket report --data-dir ./artifacts/private --json
```

`topomarket status` gives the shorter status summary (manifest validity,
snapshot count, latest data date, and source rows):

```bash
topomarket status --data-dir ./artifacts/private
topomarket status --data-dir ./artifacts/private --json
```

`topomarket validate --data-dir` is the offline integrity check. It verifies the
import manifest and its snapshot id, output checksums, required normalized
tables, parser reports, and raw hash registry, and exits non-zero on any
problem:

```bash
topomarket validate --data-dir ./artifacts/private
```

`topomarket validate --profile private` validates the profile configuration
only; it does not inspect or require private data.

## Testing and A2 acceptance

### Public tests

Public tests use synthetic fixtures and temporary directories only; no network
access or private inputs are required.

```bash
python -m compileall -q src tests app.py
ruff check .
ruff format --check .
pytest -q
```

The private-seed tests skip automatically when their environment variables are
not set, so the same `pytest -q` command is safe on a clean checkout and in
public CI.

### Private tests

The private smoke test checks that a local seed directory, archive, or single
file imports against the public schema. Point it at the seed with one of
`TOPOMARKET_PRIVATE_SEED_DIR`, `TOPOMARKET_PRIVATE_SEED_ARCHIVE`,
`TOPOMARKET_PRIVATE_SEED_ZIP`, `TOPOMARKET_PRIVATE_SEED_PATH`,
`TOPOMARKET_PRIVATE_SEED`, `TOPOMARKET_SEED_DIR`, `TOPOMARKET_SEED_ARCHIVE`,
`TOPOMARKET_SEED_ZIP`, or `TOPOMARKET_SEED_PATH`:

```bash
TOPOMARKET_PRIVATE_SEED_DIR=/path/to/seed pytest -q tests/test_private_seed.py
```

### A2 acceptance process

The private A2 proof is the opt-in acceptance suite in
`tests/private_acceptance/`. It reads the seed only from
`TOPOMARKET_SEED_DIR` (a directory, zip archive, or single file), imports it in
memory with writing disabled, and skips when the variable is absent:

```bash
TOPOMARKET_SEED_DIR=/path/to/seed pytest -q tests/private_acceptance
```

The suite establishes A2 acceptance by checking that:

1. the four required sources and optional OFR import into all three normalized
   tables with the canonical names, column order, types, and units;
2. row counts, source coverage, missing/blank-value reporting, and the known
   source disagreement match the acceptance snapshot;
3. a known golden observation matches within the documented price, return, and
   VIX tolerances, including decimal industry returns and the exact-date
   `tda_daily` join;
4. importing the same seed twice produces identical normalized table hashes;
   and
5. private seed bytes and normalized output hashes do not appear anywhere in the
   repository checkout.

A2 is accepted when this suite passes against the supplied seed and
`topomarket validate --data-dir` passes on the written import output. The
acceptance and report commands do not redistribute provider observations or
publish release dates; keep raw seed files and generated artifacts outside git.

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

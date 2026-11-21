# TopoMarket

TopoMarket is a small, topology-aware market research toolkit. It ships with a
synthetic demo profile so the repository can be explored safely, and a private
profile for local research against user-supplied data.

## Requirements

- Python 3.10 or newer
- `pip` (or another PEP 517-compatible installer)

## Setup

Clone the repository and create an isolated environment:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

The package uses a `src/` layout. After installation the `topomarket` console
script is available; the repository-level `app.py` wrapper also works from a
fresh checkout without installing:

```bash
python app.py --help
```

## CLI commands

```bash
topomarket --help
topomarket --version

# Run the bundled synthetic demo (no private inputs required)
topomarket demo
topomarket demo --json

# Inspect the resolved settings for a profile
topomarket info --profile demo
topomarket info --profile private

# Validate a profile configuration file
topomarket validate --profile demo
topomarket validate --profile private
```

`python -m topomarket <command>` is equivalent to the `topomarket` console
script once the package is installed.

## Demo command

`topomarket demo` loads the synthetic market fixtures in
`src/topomarket/data/demo_markets.json` and prints a short summary. Use
`topomarket demo --json` for machine-readable output. The demo command never
reads private inputs, writes to the network, or requires credentials.

## Profiles

Profiles live in `config/` and are plain JSON files:

| Profile   | File                  | Data source                         | Intended use                                      |
| --------- | --------------------- | ----------------------------------- | ------------------------------------------------- |
| `demo`    | `config/demo.json`    | Bundled synthetic fixtures          | Public examples, tests, and first-run exploration  |
| `private` | `config/private.json` | User-supplied local private data    | Local research only; never committed or packaged   |

Both profiles define `profile`, `name`, `description`, `data_source`,
`data_dir`, `output_dir`, `cache_dir`, `random_seed`, and `private_data`.
Relative paths are resolved against the repository root.

## Data-source notices

- The `demo` profile uses **synthetic sample data only**. It is not real
  market data and must not be used for trading or investment decisions.
- The `private` profile expects data supplied by the operator at the configured
  local path (by default `private_data/`). That directory is ignored by Git and
  is not part of this repository.
- TopoMarket does not download data, place orders, or connect to brokers.
  Review and validate any external data before using it.

## No private data

This repository contains **no private data, credentials, API keys, or secrets**.
The `config/private.json` file is a safe template that only references a local
directory; the data itself must be supplied locally and remains untracked under
`private_data/` (also excluded via `.gitignore`).

## Development

Run the test suite and linter from the repository root:

```bash
pytest
ruff check .
```

The project configuration for both tools is in `pyproject.toml`.

## Project layout

```text
app.py                         Repository entry point
config/                        demo.json and private.json profiles
src/topomarket/                Python package (CLI, profiles, data, UI, topology, evaluation)
src/topomarket/data/           Synthetic demo fixtures
tests/                         Test suite
.github/workflows/ci.yml       Continuous integration checks
```

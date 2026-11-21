# Security policy

## Reporting a vulnerability

Please do not open a public issue for exploitable vulnerability details. Contact the repository
owner directly (GitHub profile) with a description, reproduction and impact. Public security
hardening tasks are tracked as issues labelled `type: security`.

## What the repository never contains

- private market data, local snapshots or derived exports,
- credentials, provider API keys, `.env` files or local tokens,
- personal research ledgers or cached data directories.

These are excluded by `.gitignore`; CI includes secret scanning and a tracked-file scan for
private-data patterns.

## Data and provider terms

The public demo is synthetic. Any genuine market data, screenshot or derived table must comply
with the provider's terms (see [NOTICE.md](NOTICE.md)). Distribution of the S&P 500 series can
require prior permission from S&P Dow Jones Indices; review provider terms before publishing.

## Supply chain

- Dependabot alerts and automated security fixes are enabled.
- CodeQL, `pip-audit`, `bandit` and `detect-secrets` run in CI.
- `main` is protected: PR-only, required checks, linear history, no force pushes or deletion.

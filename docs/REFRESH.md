# Refresh and recovery runbook

`topomarket refresh` updates the fixed provider sources and publishes a new immutable snapshot
without ever leaving a half-written view. This document describes the operational contract.

## Quick reference

```bash
topomarket refresh --data-dir /path/to/data
topomarket refresh --data-dir /path/to/data --sources fred,cboe --json
topomarket sources --data-dir /path/to/data
topomarket validate --data-dir /path/to/data
topomarket status --data-dir /path/to/data --json
topomarket report --data-dir /path/to/data
```

Exit codes: `0` success (including "unchanged"), `2` validation/refresh failure with the last good
snapshot still active, `1` unexpected error.

## Sources

| Source id | Provider | Role |
| --- | --- | --- |
| `fred_sp500` | FRED S&P 500 price index | Required; supplies closes after the fixed OpenIntro cutover |
| `cboe_vix` | Cboe VIX history | Required; TDA/VIX inputs |
| `french_12_industries` | Kenneth French daily 12-industry archive | Required; value-weighted industry returns |
| `ofr_fsi` | OFR Financial Stress Index | Optional context series |

OpenIntro S&P 500 history is a fixed historical seed; it is not refreshed.

## Pipeline

1. **Lock** - one `state/refresh.lock` file serializes writers. A second concurrent refresh returns
   a clear "busy" error before touching any state; a stale lock (older than 10 minutes) is broken
   explicitly.
2. **Fetch** - conditional GET with a 15 s timeout and up to three attempts with exponential
   backoff for 429/5xx/timeouts/transport errors. Validators are loaded only when they belong to the
   currently active snapshot.
3. **Stage** - received bytes are written under `staging/<attempt>/` with a sidecar recording
   source, URL, SHA-256, size and receive time. The 50 MiB per-payload limit and ZIP member path
   checks are enforced before adapter validation.
4. **Validate** - the staged files pass through the same adapters as `topomarket import` in a
   throwaway build directory; empty/unknown/malformed payloads are rejected and quarantined.
5. **Merge** - the candidate is reconciled with the active snapshot:
   - `sp500_daily`: prior rows are retained; FRED rows are accepted only strictly after the fixed
     OpenIntro cutover (2018-12-07); log returns are recomputed across the merged series;
   - `industries_daily`: replaced from the refreshed French archive;
   - `tda_daily`: rebuilt as the complete inner join of prices, VIX and industry returns (older VIX
     observations are preserved, so the table does not shrink to the FRED export range);
   - revisions are recorded for changed overlapping price/industry observations.
6. **Publish** - the complete snapshot directory is built in staging and renamed atomically to
   `snapshots/<snapshot_id>`; only then is `state/active_snapshot.json` replaced (write-temp +
   atomic replace). If the normalized content is unchanged, the current snapshot id is preserved
   and nothing is published.
7. **Commit metadata** - `state/validators.json` (per-source ETag/Last-Modified bound to the new
   snapshot) and `state/refresh_status.json` are written after publication.

Any failure before step 6 leaves the pointer untouched; the previous snapshot remains the active
view. A failed required source aborts the refresh; an optional OFR failure is recorded as
`optional_failed` and the refresh can still publish.

## Data-directory layout

```
<data-dir>/
  seed/, normalized/, reports/, *.csv, import_manifest.json   # baseline from `topomarket import`
  state/
    active_snapshot.json    # atomic pointer to the published snapshot
    validators.json         # conditional-request validators (bound to snapshot id)
    refresh_status.json     # per-source last attempt/success and last refresh outcome
    refresh.lock            # writer lock (transient)
  staging/                  # transient attempt directories (cleaned on completion)
  snapshots/<id>/
    normalized/             # sp500_daily, industries_daily, tda_daily + schemas
    reports/                # per-source parser reports
    import_manifest.json    # hashes/row counts for validation
    refresh_manifest.json   # source statuses, revisions, warnings, latest date
```

`topomarket status`, `report`, `validate`, the Streamlit UI and `build_overview` resolve the active
snapshot automatically. Baseline directories created by `topomarket import` keep working; the first
refresh publishes their content into a snapshot.

## Validation and recovery checklist

- After a refresh: `topomarket validate --data-dir <dir>` and `topomarket sources --data-dir <dir>`.
- On failure: the command exits `2`, prints the failed source and keeps the previous snapshot
  active. Inspect `state/refresh_status.json`, fix the provider/network, rerun the refresh.
- A conditional (304) refresh should not change the active snapshot id.
- Never edit manifests, normalized files or snapshots by hand; rerun the import/refresh instead.
- Private data, snapshots and status files stay outside the repository checkout.

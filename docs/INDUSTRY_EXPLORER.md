# Industry explorer (Step 5)

This page documents the implemented Step 5 integration contract: the public
analysis API, the active-snapshot `topomarket industries` command, its combined
payload and the deterministic output guarantees. The methodology remains the
project Wiki reference; this is the shipped behaviour.

## Public API

`topomarket.analysis` re-exports both analysis products:

- `select_industry_window`, `build_industry_cloud`, `IndustryWindow` and
  `IndustryCloud` from `topomarket.analysis.industries`;
- `compute_mapper_graph`, `mapper_payload`, `MapperGraph`, `MapperError`,
  `mapper_intervals`, `pearson_correlations` and the volatility/distance
  helpers from `topomarket.analysis.mapper`.

`industry_explorer_payload(rows, as_of=None)` is the convenience helper that
computes the cloud and the Mapper graph from the same window and returns the
combined dictionary described below. `industry_payload` is an alias for the
same helper. With no explicit date it selects the latest complete trailing
window. The package `__all__` is the union of the two module APIs, including
the combined helper.

The analysis starts from already-loaded `tda_daily`/`industries_daily` rows. It
does not read files, download data, infer an exchange calendar, forward fill,
interpolate or cache results.

## Command

```bash
topomarket industries --data-dir /path/to/data
topomarket industries --data-dir /path/to/data --date 2020-03-16
topomarket industries --data-dir /path/to/data --date 2020-03-16 --json
topomarket industries --data-dir /path/to/data --out industry.json
```

`industry` is accepted as an alias for `industries`. `--date`, `--as-of` and
`--asof` are equivalent date selectors; `--out` and `--output` are equivalent
file destinations.

### Snapshot resolution

The command uses the same `resolve_active_data_dir` helper as
`topomarket topology`. If `state/active_snapshot.json` points at an existing
snapshot, the command loads `normalized/tda_daily.csv` from that snapshot
directory. Otherwise it falls back to the supplied data directory. No other
table, path or network source is consulted.

### Date selection

- With an explicit `--date`, the date must be present in `tda_daily.csv` and
  its trailing 60 sessions must have finite values for all twelve industry
  columns. Selection is strict; the command exits `2` rather than falling back.
- Without `--date`, the command scans backwards for the latest complete
  60-session window. This keeps the default useful when the newest inner-join
  rows still contain blank industry cells. If no complete window exists, it
  exits `2`.
- The window is always the trailing 60 sessions in ascending ISO-8601 order.
  All analysis modules share the canonical twelve French industry columns.

Missing `normalized/tda_daily.csv`, fewer than 60 rows, duplicate dates,
unknown or missing industry columns, blank/non-finite window values, an
unavailable as-of date and malformed dates all exit with status `2` and an
`error:` line on stderr.

## Combined payload

The JSON output is one object with these top-level fields:

| Field | Shape / meaning |
| --- | --- |
| `command` | `"industries"` |
| `as_of`, `as_of_date` | ISO-8601 end date of the window |
| `start_date`, `end_date` | first and last window dates |
| `window_sessions` | `60` |
| `row_count` | `60` |
| `columns`, `industry_columns` | twelve canonical `ind_*_return` column names |
| `labels`, `industry_labels` | twelve human-readable industry names |
| `dates` | 60 ascending ISO-8601 dates |
| `cloud` | full `IndustryCloud` payload |
| `mapper` | full Mapper graph payload |
| `node_count`, `edge_count`, `interval_count` | Mapper summary counts |
| `data_dir`, `active_data_dir` | resolved active data/snapshot directory |
| `active_snapshot_id`, `snapshot_id` | active snapshot id, or `null` |

The nested `cloud` payload includes `cloud`/`scaled_cloud` (`60 × 12`), `pca`
(`60 × 2`), explained variance and ratios, PCA loadings, H0/H1 diagrams and
finite lifetimes, `as_of`, window dates and columns. The nested `mapper`
payload includes the `12 × 12` Pearson correlation and clipped distance
matrices, twelve annualised volatilities, the inclusive intervals, nodes,
edges, configuration and config hash, and its `as_of`/dates. Both nested
`as_of` values equal the top-level value and both date lists equal the
top-level `dates`.

### Stable JSON and file output

JSON stdout uses `json.dumps(payload, indent=2, sort_keys=True)` followed by a
single newline, so repeated runs over identical data are byte-identical.
`--out` writes the same bytes using UTF-8, sorted keys, LF line endings and a
trailing newline. The command creates the destination parent directory when
needed and writes no other artefact. Passing both `--json` and `--out` emits
exactly the bytes written to the file; `--out` alone keeps the human-readable
summary on stdout.

## Mapper interval edge case

The lens is annualised sample volatility (`std(ddof=1) * sqrt(252)`). The
normal case splits the lens range into three inclusive, equally wide intervals
whose adjacent endpoints overlap exactly on the boundary. If all twelve
volatilities are equal, the range has zero width; the edge case emits one
inclusive interval `[value, value]` instead of three identical zero-width
copies. Membership is exact, with no absolute tolerance that could make a tiny
distinct volatility belong to every interval. Identical member sets across
intervals are merged once, keeping the lowest interval index.

## Offline data handling

- The command is fully offline. It performs no HTTP request, reads no
  credential or environment secret and honours no fixed private-data path.
- Private seeds are imported only through the existing local import helper
  (`topomarket.data.adapters.import_sources`) into a user-controlled directory,
  normally outside the repository; generated snapshots and JSON output are not
  committed.
- Public tests use synthetic temporary CSVs only. The opt-in Step 5 acceptance
  test reads `TOPOMARKET_SEED_DIR`, imports it into a pytest temporary
  directory, and skips when the variable is unset.
- The active-snapshot resolver and the `normalized/tda_daily.csv` loader are
  shared with Step 4, so refresh/recovery and topology contracts are unchanged.

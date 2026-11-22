# Topological signal (Step 4)

This page documents the causal daily anomaly score implemented in
`src/topomarket/topology/`. The full methodology (labels, alert policy, evaluation) is described in
the project Wiki; this is the implemented Step 4 contract.

## Pipeline

For every market close `t` with a complete table of preceding returns:

1. **Window** - take the last `window_sessions = 60` S&P 500 log returns ending at `t`. The window is
   valid only when all 60 values are finite; a missing return makes the window unavailable and the
   score stays unavailable until a new run of 60 consecutive valid returns exists. There is no
   interpolation, no forward fill and no exchange-calendar inference: `tda_daily` is already the
   ordered complete-session table.
2. **Robust scaling** - subtract the window median and divide by `1.4826 * MAD` (median absolute
   deviation). A zero scale makes the window unavailable.
3. **Delay embedding** - dimension `m = 3`, lag `tau = 2`:
   `x(i) = [z(i), z(i-2), z(i-4)]`; a complete 60-return window yields 56 points.
4. **Persistence** - Vietoris-Rips filtration on Euclidean distances via `ripser` with H0/H1,
   coefficient field GF(2) and a complete filtration (no distance threshold, no subsampling).
   Finite intervals with lifetime `<= 1e-8` are ignored; infinite deaths are not lifetimes.
5. **L(t)** - the largest finite H1 lifetime, or `0.0` when the cloud has no finite H1 pairs.
6. **Deviation** - `D(t) = |L(t) - median(previous 252 valid L values)|`, excluding the current
   observation.
7. **Score** - midrank of `D(t)` against the previous 252 valid `D` values:
   `score = 100 * (below + 0.5 * equal) / 252`.

## Warm-up and gaps

| State | Meaning |
| --- | --- |
| `unavailable` | Fewer than 60 consecutive valid returns, or a missing/non-finite return |
| `warming_up` | A valid L is available but the 252-reference window for L or D is not full yet |
| `scored` | Both reference windows are full; `score` is in `[0, 100]` |

A `D` value enters the reference history only when it was computed from a full 252-value L reference
set. Invalid windows never enter the history.

The first valid L appears at index `window_sessions - 1` (0-based), the first D at
`window_sessions - 1 + reference_window`, and the first score after another
`reference_window` valid observations.

## Frozen configuration

`config/topology.json` declares the frozen default (`window_sessions=60`, `embedding_dimension=3`,
`lag=2`, `reference_window=252`, `score_scale=100`, `min_interval=1e-8`, `algorithm_version=tda-v1`,
and the other fields). Its `config_hash` is verified on load; a modified frozen entry is rejected.
Custom configurations must be loaded explicitly and are marked **exploratory**; their cache key and
export sidecar keep them separate from frozen output.

## CLI

```bash
topomarket topology --data-dir /path/to/data
topomarket topology --data-dir /path/to/data --out scores.csv
topomarket topology --data-dir /path/to/data --json
topomarket topology --data-dir /path/to/data --config custom-topology.json
```

The command resolves the active snapshot automatically (fallback: the supplied data directory) and
reads `normalized/tda_daily.csv`. `--out` writes a deterministic CSV
(`date,sp500_log_return,L,D,score,state,h1_count,reason`) plus a `*.meta.json` sidecar with the
configuration hash, cache key and exploratory flag. Existing exports with a different identity are
never silently overwritten. `--json` emits the full series summary and points.

## Reproducibility

- The score series is deterministic for identical rows and configuration.
- `cache_key` combines the configuration hash, algorithm/package version, row count, date endpoints
  and a digest of all points; different content or configuration cannot share a key.
- Appending future rows never changes earlier points (causal computation).
- The public test suite covers the embedding/persistence primitives against ripser directly; the
  opt-in private acceptance suite computes the default series over the real 9,250-row `tda_daily`
  snapshot and verifies warm-up boundaries, score range, reproducibility and causality.

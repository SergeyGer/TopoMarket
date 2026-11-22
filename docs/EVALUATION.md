# Chronological evaluation and warning evidence (Step 6)

`topomarket evaluate` implements the offline evaluation contract.

## Pipeline

1. **Labels** - for each origin close `P(t)`, `y(t) = 1` when any of the next 20 closes is
   `<= 0.9 * P(t)` (inclusive); the first such session is the breach date. Origins without a full
   20-session horizon are `pending` and are never treated as negative.
2. **Episodes** - distinct breach dates, chained when consecutive breach dates are at most 20
   sessions apart; the first breach date is the episode onset.
3. **Methods** - TDA score (frozen Step 4 configuration), VIX close, and 20-session annualized
   sample volatility (`std(ddof=1) * sqrt(252)`), evaluated on the same eligible dates.
4. **Calibration** - 2005-2013 validation; percentile cutoffs 85/90/92.5/95/97.5/99 of each
   method's own readings with a 20-session cooldown; preference order: maximum episode recall
   subject to at most 2 false alerts/year, then fewer false alerts, then the higher cutoff. The
   last 20 validation origins are purged before selection; the chosen cutoffs are frozen with a
   policy hash binding method, cutoff, percentile, cooldown, window, annualization, validation
   period, session-sequence digest and eligible-year denominator.
5. **Out-of-sample test** - 2014+ through the last mature origin. Metrics: episode recall with
   numerator/denominator, false alerts per year, median lead with min/max range, daily average
   precision and event prevalence. Undefined values are explicit `null`; the report records the
   counts that explain them. Every method table carries the source snapshot id.
6. **Bootstrap** - paired moving-block bootstrap over 60-session test blocks, 1,000 replicates,
   identical block draws for all methods, fixed seed in the report; report 95% percentile intervals
   and valid replicate counts.
7. **Evidence wording** - `"Experimental market anomaly"` by default. `"Historical early-warning
   evidence"` only when at least five evaluable held-out episodes exist, the lower 95% paired
   interval for the episode-recall gain against the comparator is above zero, and the held-out
   false-alert rate is at most 2/year and no higher than the comparator's. Otherwise the report
   lists the observed limitation.
8. **Controls/ablations** - `--ablations` adds a return-shuffled TDA control (deterministic
   permutation with the report seed) and an unscaled-topology ablation (`normalization="none"`).
9. **Ledger** - `--ledger PATH` appends JSONL forecast records (recorded time, as-of, method,
   value, cutoff, alert, snapshot id, config/policy hashes). Existing bytes are never rewritten;
   invalid records are rejected. Keep the ledger outside the repository checkout.

## CLI

```bash
topomarket evaluate --data-dir /path/to/data
topomarket evaluate --data-dir /path/to/data --json --report-out report.json
topomarket evaluate --data-dir /path/to/data --seed 42 --ablations
topomarket evaluate --data-dir /path/to/data --ledger /outside/repo/forecast-ledger.jsonl
```

The command resolves the active snapshot, computes the frozen default TDA score, and prints a
summary with frozen cutoffs, test metrics, bootstrap intervals and evidence wording. `--json` and
`--report-out` emit the same deterministic report (sorted keys, UTF-8/LF). Invalid or missing data
exits with status `2`.

## Reproducibility and acceptance

- Labels, episodes, calibrations, policies, bootstrap draws and ablations are deterministic for a
  given rows input and seed; the report digest is stable across runs.
- Public tests cover the exact 10% boundary, day 20 vs day 21, pending labels, post-onset and
  duplicate alerts, calibration preference rules, bootstrap determinism, wording rules, ledger
  append-only behaviour and CLI/report determinism.
- The opt-in private acceptance computes the full report over the real 9,250-row snapshot and checks
  frozen policies, metric provenance, bootstrap validity, wording, ledger appends and future-suffix
  label causality.
- Real snapshot reference run: 28 episodes, 9 evaluable held-out episodes, TDA recall 1/9,
  1.03 false alerts/year, average precision 0.1625, median lead 10 sessions; the evidence rule
  yields `"Experimental market anomaly"` (the false-alert rate is not below the comparator's).

# Chronological evaluation and warning evidence (Step 6)

`topomarket evaluate` implements the offline evaluation contract.

## Pipeline

1. **Labels** - for each origin close `P(t)`, `y(t) = 1` when any of the next 20 closes is
   `<= 0.9 * P(t)` (inclusive: a close exactly at 90% is a breach, day 20 is inside the horizon
   and day 21 is outside); the first such session is the breach date. Origins whose observed
   horizon shows no breach and is not yet complete are `pending` and are never treated as
   negative or used for scoring.
2. **Episodes** - distinct breach dates, chained when consecutive breach dates are at most 20
   sessions apart; the first breach date is the episode onset.
3. **Methods** - TDA score (frozen Step 4 configuration), VIX close, and 20-session annualized
   sample volatility (`std(ddof=1) * sqrt(252)`). The three methods are compared on one common set
   of eligible dates: the intersection of the dates where every compared method has a finite
   reading, the target label is mature and the session is inside the out-of-sample test period.
   The report records that window (`common_eligible_dates.start`/`end`), the shared session count
   and each method's own reading count; average precision, event prevalence and the paired
   bootstrap all use the same shared dates.
4. **Calibration** - 2005-2013 validation; percentile cutoffs 85/90/92.5/95/97.5/99 of each
   method's own readings with a 20-session cooldown; preference order: maximum episode recall
   subject to at most 2 false alerts/year, then fewer false alerts, then the higher cutoff. The
   last 20 validation origins are purged before selection; the chosen cutoffs are frozen with a
   policy hash binding method, cutoff, percentile, cooldown, window, annualization, validation
   period, session-sequence digest and eligible-year denominator. The percentile is a
   *comparative* calibration rank within the method's own validation readings, not a probability.
   If no percentile candidate satisfies the false-alert constraint, calibration records the
   reason (`calibrated: false`, `silent: true`, `reason: ...`) and freezes a **silent policy**
   (`silent: true`, no cutoff, emits no alerts) instead of asserting a misleading threshold. The
   method is still reported, with zero alerts and its score-based average precision.
5. **Early-alert credit** - an alert is credited only when all three conditions hold:
   (a) its *own* target label is positive - the alert close itself breaches 90% within 20
   sessions, so pending labels can never credit; (b) the label's first breach date belongs to the
   matched episode's breach dates (an alert cannot claim a neighbouring episode's breach); and
   (c) the matched episode onset is one to 20 sessions after the alert. Each episode is credited
   at most once. Alerts inside an already-started episode stay `post_onset` (late), alerts that
   would claim an already-credited episode stay `duplicate`, alerts whose own horizon is unobserved
   stay `pending`, and mature alerts that are not credited are `false_mature` and enter the
   false-alert count. Episodes without a qualifying alert stay `missed`.
6. **Out-of-sample test** - 2014+ through the last mature origin, on the common eligible dates.
   Metrics: episode recall with numerator/denominator, false alerts per year (over the eligible
   test sessions), median lead with min/max range, average precision over the **complete eligible
   scored daily series** and event prevalence. Average precision ranks every scored session by
   descending score against its mature positive label; all sessions sharing a score form one
   threshold block (`sum (recall_after - recall_before) * precision_after`), which is the standard
   tied-score average precision (identical to `sklearn.metrics.average_precision_score`). If the
   eligible series has no positive label, average precision is `null` and the reason is recorded
   (`average_precision_reason`) together with the scored-session/positive counts. Undefined values
   are explicit `null`; the report records the counts that explain them. Every method table carries
   the source snapshot id.
7. **Bootstrap** - paired moving-block bootstrap over 60-session test blocks on the shared
   eligible dates, 1,000 replicates, identical block draws for all methods, fixed seed in the
   report; report 95% percentile intervals and valid replicate counts. **v1.2 (R2):** blocks are
   drawn *with replacement* on the eligible test sequence, concatenated and trimmed to N positions;
   every drawn position keeps its multiplicity and the same index weights are applied to each
   method's frozen onset/credited-onset/false-alert indicators. The exposure denominator is always
   N positions, so overlapping blocks can no longer shrink the sample. Rows with no event give an
   undefined recall for that replicate (valid-replicate counts make this explicit); false-alert
   rates use the fixed N exposure. The algorithm identity is
   `provenance.bootstrap_algorithm = moving_block_with_replacement_v2`; intervals computed under
   this rule are versioned against the retained v1.1 report.
8. **Evidence wording** - `"Experimental market anomaly"` by default; the forecast is presented as
   an experiment. `"Historical early-warning evidence"` only when at least five evaluable held-out
   episodes exist, the lower 95% paired interval for the episode-recall gain against the comparator
   is above zero, and the held-out false-alert rate is at most 2/year and no higher than the
   comparator's. Otherwise the report lists the observed limitations.
9. **Controls/ablations** - `--ablations` adds a return-shuffled TDA control (deterministic
   permutation with the report seed) and an unscaled-topology ablation (`normalization="none"`).
10. **Ledger** - `--ledger PATH` appends JSONL forecast records (recorded time, as-of, method,
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
  duplicate alerts, the strict credit rule (own label, breach ownership, one credit per episode),
  complete-series average precision with tied scores against `sklearn`, common eligible dates,
  silent policies, calibration preference rules, bootstrap determinism, wording rules, ledger
  append-only behaviour and CLI/report determinism (`tests/test_evaluation_contract.py` holds the
  EV01/A05 contract tests).
- The opt-in private acceptance computes the full report over the real 9,250-row snapshot and checks
  frozen policies, metric provenance, bootstrap validity, wording, ledger appends and future-suffix
  label causality.
- Real snapshot reference run (local private seed, 9,250 rows 1990-01-03..2026-09-30, not in this
  repository): 28 episodes, 9 evaluable held-out episodes, 3,185 common eligible test sessions
  (2014-01-02..2026-09-01). TDA recall 1/9 (alert 2022-09-08, onset 2022-09-22, lead 10), 13 false
  alerts = 1.03/year, median lead 10 sessions, average precision 0.0494 on the complete scored
  daily series (the alert-only value previously quoted was 0.1625). VIX average precision 0.0677
  (1 alert, 0 false) and realized volatility 0.0704 (1 alert, 0 false); event prevalence 0.0314.
  The frozen policies remain the 99th percentile of each method's validation readings (TDA 99.60,
  VIX 62.94, realized volatility 0.7583); the selected cutoffs and percentiles are unchanged from
  the previous release. The evidence rule yields
  `"Experimental market anomaly"`: the lower 95% paired bound on the episode-recall gain is not
  above zero (0.0) and TDA's false-alert rate is above the VIX comparator's (0.0).
- The public synthetic fixture (`showcase/`, seed 4242) records the same schema but its own
  numbers: 4 episodes, 3 evaluable held-out episodes, 3,306 common eligible sessions, TDA recall
  0/3 with average precision 0.0154, VIX recall 1/3 with average precision 0.1187, realized
  volatility recall 0/3 with average precision 0.0556, and `"Experimental market anomaly"`.

## Independent signal calendars (v1.2 R1)

Price-based signals no longer depend on industry coverage. `topomarket.data.signals` loads three
independent calendars from a snapshot:

- **price** (`normalized/sp500_daily.csv`, or the joint `tda_daily` fallback for old synthetic
  snapshots) drives S&P log returns, the TDA score, realised volatility, origin labels and
  20-index-session horizons;
- **industry** (`normalized/industries_daily.csv`, or fallback) drives industry windows/Mapper only;
- **VIX** (`normalized/vix_daily.csv`, a saved VIX source file, or fallback) is joined by date for the
  comparison cohort only.

`topomarket topology` and `topomarket evaluate` use the price calendar; evaluation rows are the price
calendar left-joined with VIX by date, so a later VIX/industry date can no longer extend or truncate
the price/label series. Reports and CLI output record separate as-of dates, the source of each
calendar and the fallback reason; `provenance.snapshot_provenance.signal_calendars` carries the same
block. Acceptance tests write split tables, append price/VIX dates beyond the industry coverage,
mutate only the industry table and assert price scores and evaluation reports are byte-identical.

## Snapshot identity at the CLI (v1.2 R3)

`topomarket evaluate` now resolves one non-empty identity before running: active snapshot pointer,
then the direct snapshot's `refresh_manifest.json`, then `import_manifest.json` (and its content
digest). The identity and its source/manifest digest are carried into the report, policies,
provenance and private ledger rows; conflicting identity sources fail visibly with a clear error
instead of emitting an empty snapshot id. Tests cover direct-directory and active-snapshot forms,
content-digest fallback, conflicting sources and the CLI report provenance.

## F01 correction: calibration recall (v1.1)

The v1.0 audit found one integrity defect outside the corrected matching/reporting path:
`alerts.calibrate_method` read `pair.episode_start` from an `AlertMatch`, but that attribute does not
exist (the match exposes `episode_onset` / `episode.start_date`). The calibration `matched_count`
and calibration episode recall were therefore always `0`, and the documented preference rule
"maximum episode recall, then fewer false alerts, then the higher cutoff" was effectively dead code:
frozen cutoffs were selected on the false-alert count only.

v1.1 fixes this with `calibration_version = "F01-corrected-v1"`:

- Recall counts **unique matched episode onsets**, one credit per episode, using the canonical
  `AlertMatch.onset_date` / `episode.start_date` accessor.
- The documented ordering, silent-policy behaviour, validation/holdout boundaries, purging,
  cooldown, labels and benchmark contracts are unchanged.
- Reports are now versioned (`report_version = "1.1"`, `schema_version = 2`) and carry
  provenance (`code_revision`, package version, snapshot, config hash, seed, label contract,
  calibration and policy hashes) plus a `calibration_comparison` block comparing the retained v1.0
  baseline with the corrected run on identical eligible dates.

Public synthetic regeneration (`scripts/build_showcase.py`, seed 4242): the corrected validation
recall is **1.0 for VIX and realized volatility** (v1.0 reported 0.0 for every method), while TDA
stays 0.0. Because all three frozen percentiles remain the 99th percentile, **holdout metrics and
policy hashes are unchanged**: TDA 0/3 recall, average precision 0.0154; VIX 1/3 recall, AP 0.1187;
realized volatility 0/3 recall, AP 0.0556; common eligible sessions 3,306. The v1.0 report is
retained verbatim at `docs/reports/evaluation-v1.0-baseline.json` for comparison, and the Validation
screen shows the before/after calibration table.

### Private reference report (owner action)

The private seed is not present in the public repository or this build environment, so the corrected
private report cannot be regenerated here. The v1.0 private reference (9,250 rows, 28 episodes,
9 evaluable held-out episodes, 3,185 common eligible sessions, TDA recall 1/9, 13 false alerts
= 1.03/year, AP 0.0494, frozen 99th-percentile policies) remains the documented baseline. To produce
the corrected private report locally (result stays outside Git):

```bash
TOPOMARKET_SEED_DIR=/path/to/seed topomarket evaluate \
  --profile private --data-dir /path/to/data \\
  --report-out /path/to/private/reports/evaluation-v1.1.json --json
```

Record the report digest, policy hashes and before/after calibration comparison (the report contains
both) in the local acceptance notes; do not commit private values. If the corrected selection moves
the private cutoffs (the audit expected TDA/VIX/volatility 97.5/95/85 instead of 99/99/99 and TDA
holdout 0/9), publish only the documented summary after reviewing redistribution rights.

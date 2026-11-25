"""Chronological out-of-sample evaluation and warning evidence (Step 6).

The pipeline is deterministic and offline:

1. labelled origins and breach episodes (``labels`` module);
2. methods: TDA score, VIX close, 20-session annualized realized volatility;
3. calibration on 2005-2013 (percentile cutoffs, 20-session cooldown, preference
   rules), frozen policies with hashes; a method whose candidates all violate the
   false-alert constraint freezes into a recorded *silent* policy (no alerts);
4. evaluation on 2014+ on one common set of eligible dates (episode recall with
   the strict own-label/breach-ownership credit rule, false alerts per year,
   median lead, average precision over the complete scored daily series, explicit
   losing/missing/matched examples);
5. paired moving-block bootstrap (60-session blocks, shared draws on the common
   eligible dates);
6. optional controls/ablations (return-shuffled TDA, unscaled TDA);
7. evidence wording rules and an append-only private ledger.

All result tables carry the source snapshot id (when supplied) so every row can
be traced back to the assessed data.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from topomarket import __version__
from topomarket.topology import TopologyConfig, compute_topology_scores

from .alerts import (
    ANNUALIZATION,
    METHODS,
    VALIDATION_END,
    VALIDATION_START,
    AlertEvaluation,
    AlertPolicy,
    CalibrationResult,
    calibrate_method,
    evaluate_alerts,
    freeze_policy,
    generate_alerts,
    readings_from_rows,
    readings_from_scores,
    select_comparator,
)
from .labels import build_breach_episodes, build_target_labels
from .ledger import ForecastLedger, ledger_records_for_alerts

TEST_START = "2014-01-01"
DEVELOPMENT_START = "1990-01-01"
BOOTSTRAP_BLOCK_SESSIONS = 60
BOOTSTRAP_REPLICATES = 1_000
DEFAULT_SEED = 42
MIN_EVALUABLE_EPISODES = 5
MAX_FALSE_ALERTS_PER_YEAR = 2.0


class EvaluationError(ValueError):
    """Raised for invalid evaluation inputs or report construction."""


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    lower: float | None
    upper: float | None
    mean: float | None
    valid_replicates: int
    total_replicates: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "mean": self.mean,
            "valid_replicates": self.valid_replicates,
            "total_replicates": self.total_replicates,
        }


@dataclass(frozen=True, slots=True)
class EvidenceWording:
    wording: str
    historical_evidence: bool
    criteria: Mapping[str, Any]
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "wording": self.wording,
            "historical_evidence": self.historical_evidence,
            "criteria": dict(self.criteria),
            "limitations": list(self.limitations),
        }


def _float_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _date_index(dates: Sequence[str]) -> dict[str, int]:
    return {date: index for index, date in enumerate(dates)}


def _all_episode_onsets(evaluation: AlertEvaluation) -> set[str]:
    onsets = {
        str(example.get("episode_onset"))
        for example in evaluation.matched
        if example.get("episode_onset")
    }
    onsets.update(
        str(example.get("episode_onset"))
        for example in evaluation.missed_episodes
        if example.get("episode_onset")
    )
    return onsets


def _block_bootstrap(
    *,
    primary: AlertEvaluation,
    comparator: AlertEvaluation | None,
    dates: Sequence[str],
    test_start: str,
    test_end: str,
    seed: int,
    block_sessions: int = BOOTSTRAP_BLOCK_SESSIONS,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, BootstrapInterval]:
    """Paired moving-block bootstrap over the test eligible dates."""
    if replicates < 1:
        raise EvaluationError("bootstrap replicates must be >= 1")
    start_index = next(index for index, date in enumerate(dates) if date >= test_start)
    end_index = max(index for index, date in enumerate(dates) if date <= test_end)
    period_indices = list(range(start_index, end_index + 1))
    if len(period_indices) < 2:
        raise EvaluationError("not enough sessions for a bootstrap")
    block = max(2, min(int(block_sessions), len(period_indices)))
    block_count = max(1, int(math.ceil(len(period_indices) / block)))
    # Deterministic statistical bootstrap, not a cryptographic use.
    rng = random.Random(int(seed))  # nosec B311

    primary_onsets = _all_episode_onsets(primary)
    primary_matched = {
        str(example.get("episode_onset"))
        for example in primary.matched
        if example.get("episode_onset")
    }
    primary_false = set(primary.false_alerts)
    comparator_onsets = _all_episode_onsets(comparator) if comparator is not None else set()
    comparator_matched = (
        {
            str(example.get("episode_onset"))
            for example in comparator.matched
            if example.get("episode_onset")
        }
        if comparator is not None
        else set()
    )
    comparator_false = set(comparator.false_alerts) if comparator is not None else set()

    gains: list[float] = []
    primary_recalls: list[float] = []
    comparator_recalls: list[float] = []
    primary_rates: list[float] = []
    comparator_rates: list[float] = []
    for _ in range(replicates):
        sampled: set[int] = set()
        for _block in range(block_count):
            offset = rng.randrange(0, max(1, len(period_indices) - block + 1))
            start = period_indices[offset]
            sampled.update(range(start, min(start + block, end_index + 1)))
        sampled_dates = {dates[index] for index in sampled}
        sampled_count = len(sampled_dates)
        if sampled_count == 0:
            continue
        tda_total = len(primary_onsets & sampled_dates)
        tda_matched = len(primary_matched & sampled_dates)
        comp_total = len(comparator_onsets & sampled_dates)
        comp_matched = len(comparator_matched & sampled_dates)
        tda_false = len(primary_false & sampled_dates)
        comp_false = len(comparator_false & sampled_dates)
        tda_recall = tda_matched / tda_total if tda_total else None
        comp_recall = comp_matched / comp_total if comp_total else None
        tda_rate = tda_false / (sampled_count / ANNUALIZATION)
        comp_rate = comp_false / (sampled_count / ANNUALIZATION)
        if tda_recall is not None:
            primary_recalls.append(tda_recall)
        primary_rates.append(tda_rate)
        if comparator is not None:
            if comp_recall is not None:
                comparator_recalls.append(comp_recall)
            comparator_rates.append(comp_rate)
            if tda_recall is not None and comp_recall is not None:
                gains.append(tda_recall - comp_recall)

    def interval(values: Sequence[float]) -> BootstrapInterval:
        ordered = sorted(values)
        if not ordered:
            return BootstrapInterval(None, None, None, 0, replicates)
        lower = ordered[int(0.025 * (len(ordered) - 1))]
        upper = ordered[int(0.975 * (len(ordered) - 1))]
        return BootstrapInterval(
            lower=_float_or_none(lower),
            upper=_float_or_none(upper),
            mean=_float_or_none(sum(ordered) / len(ordered)),
            valid_replicates=len(ordered),
            total_replicates=replicates,
        )

    return {
        "episode_recall_gain": interval(gains),
        "tda_episode_recall": interval(primary_recalls),
        "comparator_episode_recall": interval(comparator_recalls),
        "tda_false_alerts_per_year": interval(primary_rates),
        "comparator_false_alerts_per_year": interval(comparator_rates),
    }


def evidence_wording(
    primary: AlertEvaluation,
    comparator: AlertEvaluation | None,
    bootstrap: Mapping[str, BootstrapInterval],
    *,
    min_evaluable_episodes: int = MIN_EVALUABLE_EPISODES,
) -> EvidenceWording:
    """Apply the documented evidence-wording rules."""
    gain = bootstrap.get("episode_recall_gain")
    criteria: dict[str, Any] = {
        "evaluable_episodes": primary.episode_count,
        "min_evaluable_episodes": min_evaluable_episodes,
        "recall_gain_lower_95": None if gain is None else gain.lower,
        "recall_gain_upper_95": None if gain is None else gain.upper,
        "recall_gain_valid_replicates": None if gain is None else gain.valid_replicates,
        "tda_false_alerts_per_year": primary.false_alerts_per_year,
        "comparator_false_alerts_per_year": (
            None if comparator is None else comparator.false_alerts_per_year
        ),
        "max_false_alerts_per_year": MAX_FALSE_ALERTS_PER_YEAR,
    }
    enough_episodes = primary.episode_count >= min_evaluable_episodes
    positive_gain = gain is not None and gain.lower is not None and gain.lower > 0.0
    false_rate_ok = (
        primary.false_alerts_per_year is not None
        and primary.false_alerts_per_year <= MAX_FALSE_ALERTS_PER_YEAR
        and (
            comparator is None
            or comparator.false_alerts_per_year is None
            or primary.false_alerts_per_year <= comparator.false_alerts_per_year
        )
    )
    criteria.update(
        {
            "enough_evaluable_episodes": enough_episodes,
            "positive_lower_recall_gain_bound": positive_gain,
            "false_alert_rate_within_rule": false_rate_ok,
        }
    )
    historical = bool(enough_episodes and positive_gain and false_rate_ok)
    limitations: list[str] = []
    if not enough_episodes:
        limitations.append(
            f"fewer than {min_evaluable_episodes} evaluable held-out episodes; "
            "the result is descriptive only"
        )
    if not positive_gain:
        limitations.append(
            "the lower 95% bootstrap bound on the episode-recall gain is not above zero"
        )
    if not false_rate_ok:
        limitations.append(
            "the held-out false-alert rate does not satisfy the evidence rule "
            "(<= 2/year and no higher than the comparator)"
        )
    wordings = "Historical early-warning evidence" if historical else "Experimental market anomaly"
    return EvidenceWording(
        wording=wordings,
        historical_evidence=historical,
        criteria=criteria,
        limitations=tuple(limitations),
    )


def _evaluate_method(
    *,
    method: str,
    policy: AlertPolicy,
    readings: Sequence[Any],
    labels: Sequence[Any],
    episodes: Sequence[Any],
    dates: Sequence[str],
    start: str,
    end: str,
    evaluation_dates: Sequence[str] | None = None,
) -> AlertEvaluation:
    alerts = generate_alerts(readings, dates, policy)
    return evaluate_alerts(
        method=method,
        alerts=alerts,
        episodes=episodes,
        labels=labels,
        sessions=dates,
        start=start,
        end=end,
        policy=policy,
        readings=readings,
        evaluation_dates=evaluation_dates,
    )


def _censor_episodes(
    episodes: Sequence[Any], dates: Sequence[str]
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Drop episodes whose onset falls within the unresolved final lead window."""
    last_index = len(dates) - 1
    resolved: list[Any] = []
    censored: list[dict[str, Any]] = []
    for episode in episodes:
        start_index = int(getattr(episode, "start_index", 0))
        if start_index > last_index - 20:
            censored.append(
                {
                    "episode_onset": str(getattr(episode, "start_date", "")),
                    "reason": "onset within the final unresolved 20-session window",
                }
            )
        else:
            resolved.append(episode)
    return resolved, censored


def _topology_readings(rows: Sequence[Mapping[str, Any]], *, normalization: str | None = None):
    config = TopologyConfig()
    if normalization is not None:
        config = TopologyConfig(normalization=normalization)
    series = compute_topology_scores(rows, config)
    return readings_from_scores(series.points, "tda"), series


def _shuffled_rows(rows: Sequence[Mapping[str, Any]], *, seed: int) -> list[dict[str, Any]]:
    shuffled = [dict(row) for row in rows]
    returns = [row.get("sp500_log_return") for row in shuffled]
    # Deterministic control permutation, not a cryptographic use.
    rng = random.Random(int(seed))  # nosec B311
    rng.shuffle(returns)
    for row, value in zip(shuffled, returns, strict=True):
        row["sp500_log_return"] = value
    return shuffled


def _frame_label_counts(labels: Sequence[Any]) -> dict[str, int]:
    counts = {"positive": 0, "negative": 0, "pending": 0}
    for label in labels:
        status = str(getattr(label, "status", "")).lower()
        if status == "pending":
            counts["pending"] += 1
        elif status.startswith("positive"):
            counts["positive"] += 1
        elif status.startswith("negative"):
            counts["negative"] += 1
    return counts


def build_evaluation_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    score_series: Any | None = None,
    config_hash: str | None = None,
    snapshot_id: str | None = None,
    seed: int = DEFAULT_SEED,
    include_ablations: bool = False,
    ledger_path: Path | str | None = None,
    ledger_snapshot_id: str | None = None,
    clock: Any | None = None,
) -> dict[str, Any]:
    """Run the full deterministic evaluation pipeline and return the report."""
    materialised = [dict(row) for row in rows]
    if not materialised:
        raise EvaluationError("evaluation requires at least one row")
    dates = [str(row.get("date")) for row in materialised]
    for left, right in zip(dates, dates[1:], strict=False):
        if left >= right:
            raise EvaluationError("rows must be strictly ordered by date")

    labels = build_target_labels(materialised)
    episodes = build_breach_episodes(labels)
    resolved_episodes, censored_episodes = _censor_episodes(episodes, dates)
    label_counts = _frame_label_counts(labels)

    readings_by_method: dict[str, tuple[Any, ...]] = {}
    if score_series is not None:
        readings_by_method["tda"] = readings_from_scores(score_series.points, "tda")
    readings_by_method["vix"] = readings_from_rows(materialised, "vix")
    readings_by_method["realized_vol"] = readings_from_rows(materialised, "realized_vol")

    calibrations: dict[str, CalibrationResult] = {}
    policies: dict[str, AlertPolicy] = {}
    for method in METHODS:
        readings = readings_by_method.get(method)
        if not readings:
            continue
        calibration = calibrate_method(
            method=method,
            readings=readings,
            labels=labels,
            sessions=dates,
            config_hash=config_hash or "unspecified",
        )
        calibrations[method] = calibration
        if calibration.calibrated or calibration.silent:
            policies[method] = freeze_policy(calibration)

    mature_dates = [
        str(label.date)
        for label in labels
        if str(getattr(label, "status", "")).lower() != "pending"
    ]
    if not mature_dates:
        raise EvaluationError("no mature labels available for evaluation")
    test_end = mature_dates[-1]
    if test_end < TEST_START:
        raise EvaluationError("no mature labels in the out-of-sample test period")

    # EV01: every compared method is scored on the same sessions - the
    # intersection of the dates where each method has a finite reading, the
    # label is mature and the session is inside the out-of-sample test period.
    mature_label_dates = {date for date in mature_dates}
    compared_methods = [
        method for method in METHODS if method in policies and readings_by_method.get(method)
    ]
    method_dates: dict[str, set[str]] = {}
    for method in compared_methods:
        method_dates[method] = {
            reading.date
            for reading in readings_by_method[method]
            if TEST_START <= reading.date <= test_end and reading.date in mature_label_dates
        }
    common_dates: list[str] = []
    if compared_methods:
        shared = set(method_dates[compared_methods[0]])
        for method in compared_methods[1:]:
            shared &= method_dates[method]
        common_dates = sorted(shared)
        if not common_dates:
            raise EvaluationError("no common eligible evaluation dates across methods")

    evaluations: dict[str, AlertEvaluation] = {}
    for method, policy in policies.items():
        evaluations[method] = _evaluate_method(
            method=method,
            policy=policy,
            readings=readings_by_method[method],
            labels=labels,
            episodes=resolved_episodes,
            dates=dates,
            start=TEST_START,
            end=test_end,
            evaluation_dates=common_dates,
        )

    comparator_method = select_comparator(calibrations)
    primary_method = "tda" if "tda" in evaluations else None
    primary = evaluations.get(primary_method) if primary_method else None
    comparator = evaluations.get(comparator_method) if comparator_method else None
    if primary is None or comparator is None:
        raise EvaluationError(
            "paired evaluation requires a calibrated TDA method and a calibrated simple comparator"
        )

    bootstrap = _block_bootstrap(
        primary=primary,
        comparator=comparator,
        dates=common_dates,
        test_start=TEST_START,
        test_end=test_end,
        seed=seed,
    )
    wording = evidence_wording(primary, comparator, bootstrap)

    purge_sessions = 0
    for calibration in calibrations.values():
        if not (calibration.calibrated or calibration.silent):
            continue
        validation_sessions = [date for date in dates if VALIDATION_START <= date <= VALIDATION_END]
        if validation_sessions:
            purge_sessions = max(
                purge_sessions,
                len(validation_sessions) - int(round(calibration.eligible_years * ANNUALIZATION)),
            )

    report: dict[str, Any] = {
        "schema_version": 1,
        "package_version": __version__,
        "snapshot_id": snapshot_id or ledger_snapshot_id,
        "seed": int(seed),
        "methods": list(evaluations),
        "primary_method": primary_method,
        "comparator_method": comparator_method,
        "periods": {
            "development": {"start": DEVELOPMENT_START, "end": "2004-12-31"},
            "validation": {"start": VALIDATION_START, "end": VALIDATION_END},
            "test": {"start": TEST_START, "end": test_end},
        },
        "row_count": len(materialised),
        "data_start": dates[0],
        "data_end": dates[-1],
        "config_hash": config_hash,
        "label_counts": label_counts,
        "episode_count": len(episodes),
        "resolved_episode_count": len(resolved_episodes),
        "censored_episodes": censored_episodes,
        "purged_validation_sessions": purge_sessions,
        "common_eligible_dates": {
            "start": common_dates[0] if common_dates else None,
            "end": common_dates[-1] if common_dates else None,
            "session_count": len(common_dates),
            "methods": compared_methods,
            "method_session_counts": {
                method: len(method_dates.get(method, set())) for method in compared_methods
            },
            "criteria": (
                "intersection of dates where every compared method has a finite reading, "
                "the target label is mature and the session is inside the test period"
            ),
        },
        "credit_rule": "label_positive_and_breach_owned",
        "silent_policies": {
            method: calibration.reason
            for method, calibration in calibrations.items()
            if calibration.silent
        },
        "calibrations": {
            method: calibration.as_dict() for method, calibration in calibrations.items()
        },
        "policies": {method: policy.as_dict() for method, policy in policies.items()},
        "metrics": {
            method: {
                **evaluation.as_dict(),
                "snapshot_id": snapshot_id or ledger_snapshot_id,
            }
            for method, evaluation in evaluations.items()
        },
        "bootstrap": {key: interval.as_dict() for key, interval in bootstrap.items()},
        "evidence": wording.as_dict(),
        "examples": {
            method: {
                "matched": list(evaluation.matched[:5]),
                "missed": list(evaluation.missed_episodes[:5]),
                "false_alerts": list(evaluation.false_alerts[:5]),
            }
            for method, evaluation in evaluations.items()
        },
    }

    if include_ablations:
        ablations = _build_ablations(
            materialised,
            labels=labels,
            episodes=resolved_episodes,
            dates=dates,
            test_end=test_end,
            seed=seed,
            config_hash=config_hash,
            evaluation_dates=common_dates,
        )
        report["ablations"] = ablations

    if ledger_path is not None:
        ledger = ForecastLedger(ledger_path)
        records = ledger_records_for_alerts(
            primary,
            policy=policies[primary_method],
            snapshot_id=snapshot_id or ledger_snapshot_id or "unknown",
            config_hash=config_hash or "unspecified",
        )
        appended = ledger.append_many(records) if records else 0
        report["ledger"] = {"path": str(Path(ledger_path)), "appended_records": appended}
    return report


def _build_ablations(
    rows: Sequence[Mapping[str, Any]],
    *,
    labels: Sequence[Any],
    episodes: Sequence[Any],
    dates: Sequence[str],
    test_end: str,
    seed: int,
    config_hash: str | None,
    evaluation_dates: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compute the two documented control/ablation variants."""
    ablations: dict[str, Any] = {}
    try:
        unscaled_readings, _ = _topology_readings(rows, normalization="none")
        unscaled_calibration = calibrate_method(
            method="tda",
            readings=unscaled_readings,
            labels=labels,
            sessions=dates,
            config_hash=config_hash or "unspecified",
        )
        if unscaled_calibration.calibrated or unscaled_calibration.silent:
            policy = freeze_policy(unscaled_calibration)
            evaluation = _evaluate_method(
                method="tda_unscaled",
                policy=policy,
                readings=unscaled_readings,
                labels=labels,
                episodes=episodes,
                dates=dates,
                start=TEST_START,
                end=test_end,
                evaluation_dates=evaluation_dates,
            )
            ablations["tda_unscaled"] = {
                "calibration": unscaled_calibration.as_dict(),
                "metrics": evaluation.as_dict(),
            }
        else:
            ablations["tda_unscaled"] = {"calibration": unscaled_calibration.as_dict()}
    except Exception as error:  # pragma: no cover - depends on input size
        ablations["tda_unscaled"] = {"error": f"{type(error).__name__}: {error}"}

    try:
        shuffled = _shuffled_rows(rows, seed=seed)
        shuffled_readings, _ = _topology_readings(shuffled)
        shuffled_calibration = calibrate_method(
            method="tda",
            readings=shuffled_readings,
            labels=labels,
            sessions=dates,
            config_hash=config_hash or "unspecified",
        )
        if shuffled_calibration.calibrated or shuffled_calibration.silent:
            policy = freeze_policy(shuffled_calibration)
            evaluation = _evaluate_method(
                method="tda_shuffled",
                policy=policy,
                readings=shuffled_readings,
                labels=labels,
                episodes=episodes,
                dates=dates,
                start=TEST_START,
                end=test_end,
                evaluation_dates=evaluation_dates,
            )
            ablations["tda_shuffled"] = {
                "calibration": shuffled_calibration.as_dict(),
                "metrics": evaluation.as_dict(),
            }
        else:
            ablations["tda_shuffled"] = {"calibration": shuffled_calibration.as_dict()}
    except Exception as error:  # pragma: no cover - depends on input size
        ablations["tda_shuffled"] = {"error": f"{type(error).__name__}: {error}"}
    return ablations


def report_digest(report: Mapping[str, Any]) -> str:
    """Stable digest of an evaluation report (independent of dict ordering)."""
    encoded = json.dumps(report, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def write_evaluation_report(
    report: Mapping[str, Any],
    path: Path | str,
) -> Path:
    """Write the deterministic UTF-8/LF JSON report (sorted keys)."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(target)
    return target


__all__ = [
    "BOOTSTRAP_BLOCK_SESSIONS",
    "BOOTSTRAP_REPLICATES",
    "DEFAULT_SEED",
    "DEVELOPMENT_START",
    "EvaluationError",
    "EvidenceWording",
    "MAX_FALSE_ALERTS_PER_YEAR",
    "MIN_EVALUABLE_EPISODES",
    "TEST_START",
    "build_evaluation_report",
    "evidence_wording",
    "report_digest",
    "write_evaluation_report",
]

"""
ITBIS — CERT r4.2 evaluation, pass B: model, risk engine and answer key

Reads what replay.py wrote and measures how well each detection setup finds
the dataset's red-team insiders, as the live system would have run day by day:

  1. Personal baselines: for every person and day, mean / population std of
     each feature over the previous 28 calendar days (inactive days count as
     zeros, as `build_baseline` does); used once 5 of those days were active,
     otherwise the population statistics.
  2. Model input: the same 32 values `build_32_features` builds.
  3. Models: the shipped artifact (v2), and a fresh model (v3) trained only on
     days before `--train-end`, then saved next to v2.
  4. Setups compared
        ml_only_v2 / ml_only_v3   the old rule: alert on a HIGH+ model result
                                  scored against a personal baseline
        detectors_only            risk engine fed by category findings only
        risk_engine_v2 / _v3      risk engine fed by findings + model results
     Risk-engine setups run each person's days in order through the platform's
     own `score_employee` and `alert_warranted`; earlier alerts feed the
     historical component the way analyst-confirmed alerts do live.
  5. Metrics over days on/after `--eval-start`, against the answer key.

    python -m evaluation.cert.evaluate --run ../data/evaluation/cert_r4.2 \
        --answers ../archive/answers
"""

from __future__ import annotations

import argparse
import gzip
import json
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import structlog

from app.modules.alerts.application.risk_alert_service import alert_warranted
from app.modules.anomaly.application.model_service import DEFAULT_ARTIFACT_PATH, ModelService
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION
from app.modules.detection.domain.categories import AnomalyCategory
from app.modules.risk.application.scoring import score_employee
from app.modules.risk.domain.model import CATEGORY_COMPONENT, RiskComponent, RiskSignal
from evaluation.cert.cert_io import Insider, load_insiders

log = structlog.get_logger("cert.evaluate")

BASELINE_DAYS = 28
MIN_BASELINE_DAYS = 5
ANOMALY_FLOOR = 40.0
HIGH_RISK = 60.0


# ─── Data ───────────────────────────────────────────────────


def load_features(run_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(run_dir / "features.csv.gz", parse_dates=["day"])
    df["day"] = df["day"].dt.date
    return df


def load_findings(run_dir: Path) -> list[dict]:
    path = run_dir / "findings.jsonl.gz"
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


@dataclass
class Grid:
    """Every person x every calendar day x every feature (zeros when inactive)."""

    users: list[str]
    days: list[date]
    values: np.ndarray  # (users, days, features)
    active: np.ndarray  # (users, days) bool

    @classmethod
    def from_features(cls, df: pd.DataFrame) -> Grid:
        users = sorted(df["user_id"].unique())
        first, last = min(df["day"]), max(df["day"])
        days = [d.date() for d in pd.date_range(first, last, freq="D")]
        u_index = {u: i for i, u in enumerate(users)}
        d_index = {d: i for i, d in enumerate(days)}
        values = np.zeros((len(users), len(days), len(FEATURE_NAMES)), dtype=np.float64)
        active = np.zeros((len(users), len(days)), dtype=bool)
        ui = df["user_id"].map(u_index).to_numpy()
        di = df["day"].map(d_index).to_numpy()
        values[ui, di, :] = df[FEATURE_NAMES].to_numpy(dtype=np.float64)
        active[ui, di] = df["event_count"].to_numpy() > 0
        return cls(users, days, values, active)


def rolling_baselines(
    grid: Grid, window: int = BASELINE_DAYS
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    For each (user, day): mean and population std of each feature over the
    `window` days before it, and how many of those days were active.
    """
    u, d, f = grid.values.shape
    pad = np.zeros((u, 1, f))
    csum = np.concatenate([pad, np.cumsum(grid.values, axis=1)], axis=1)
    csq = np.concatenate([pad, np.cumsum(grid.values**2, axis=1)], axis=1)
    cact = np.concatenate([np.zeros((u, 1)), np.cumsum(grid.active, axis=1)], axis=1)
    idx = np.arange(d)
    lo = np.maximum(idx - window, 0)
    sums = csum[:, idx, :] - csum[:, lo, :]
    squares = csq[:, idx, :] - csq[:, lo, :]
    means = sums / window
    stds = np.sqrt(np.maximum(squares / window - means**2, 0.0))
    active_days = cact[:, idx] - cact[:, lo]
    return means, stds, active_days


def model_inputs(
    grid: Grid,
    means: np.ndarray,
    stds: np.ndarray,
    active_days: np.ndarray,
    *,
    global_means: dict[str, float],
    global_stds: dict[str, float],
    model_features: list[str],
    min_baseline_days: int = MIN_BASELINE_DAYS,
) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Row-per-active-user-day table plus the model's 32-value input matrix,
    built exactly as `feature_prep.build_32_features` builds one row.
    """
    ui, di = np.nonzero(grid.active)
    base = grid.values[ui, di, :]
    personal = active_days[ui, di] >= min_baseline_days
    g_mean = np.array([float(global_means.get(n, 0.0)) for n in FEATURE_NAMES])
    g_std_raw = np.array([float(global_stds.get(n, 0.0)) for n in FEATURE_NAMES])
    g_std = np.where(np.isnan(g_std_raw) | (g_std_raw <= 0), 0.0, g_std_raw)

    p_mean = means[ui, di, :]
    p_std = stds[ui, di, :]
    mean = np.where(personal[:, None], p_mean, g_mean[None, :])
    std = np.where(personal[:, None] & (p_std > 0), p_std, g_std[None, :])
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(std > 0, (base - mean) / np.where(std > 0, std, 1.0), 0.0)

    column = {n: base[:, i] for i, n in enumerate(FEATURE_NAMES)}
    column |= {f"{n}_zscore": z[:, i] for i, n in enumerate(FEATURE_NAMES)}
    matrix = np.column_stack([column[name] for name in model_features])
    rows = pd.DataFrame(
        {
            "user_id": [grid.users[i] for i in ui],
            "day": [grid.days[j] for j in di],
            "baseline": np.where(personal, "personal", "global"),
        }
    )
    return rows, matrix


def risk_from_decision(decision: np.ndarray, low: float, high: float) -> np.ndarray:
    """Vectorised `risk_scoring.risk_score_from_decision`."""
    eps = 1e-9
    normal_span = high if high > eps else max(abs(low), eps)
    anomaly_span = -low if low < -eps else max(abs(high), eps)
    normal = (ANOMALY_FLOOR - 0.01) * (1.0 - np.minimum(decision / normal_span, 1.0))
    anomaly = ANOMALY_FLOOR + (100.0 - ANOMALY_FLOOR) * np.minimum(-decision / anomaly_span, 1.0)
    return np.round(np.where(decision >= 0, normal, anomaly), 3)


# ─── Models ─────────────────────────────────────────────────


def score_with(service: ModelService, matrix: np.ndarray, chunk: int = 50_000):
    preds, decisions = [], []
    for startrow in range(0, len(matrix), chunk):
        p, s = service.score_many(matrix[startrow : startrow + chunk])
        preds.extend(p)
        decisions.extend(s)
    return np.asarray(preds), np.asarray(decisions)


def train_model(
    matrix: np.ndarray,
    model_features: list[str],
    *,
    global_means: dict[str, float],
    global_stds: dict[str, float],
    metadata: dict,
    out_path: Path,
    n_estimators: int = 250,
    contamination: float = 0.03,
) -> Path:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    frame = pd.DataFrame(matrix, columns=model_features)
    scaler = StandardScaler().fit(frame)
    scaled = scaler.transform(frame)
    model = IsolationForest(
        n_estimators=n_estimators, contamination=contamination, random_state=42, n_jobs=-1
    ).fit(scaled)
    decisions = model.decision_function(scaled)
    artifact = {
        "model": model,
        "scaler": scaler,
        "baseline_stats": {},
        "global_means": global_means,
        "global_stds": global_stds,
        "feature_columns": list(FEATURE_NAMES),
        "z_feature_columns": [f"{n}_zscore" for n in FEATURE_NAMES],
        "model_features": model_features,
        "count_features": [],
        "score_low": float(np.percentile(decisions, 5)),
        "score_high": float(np.percentile(decisions, 95)),
        "metadata": {
            **metadata,
            "feature_version": FEATURE_VERSION,
            "algorithm": "IsolationForest",
            "n_estimators": n_estimators,
            "contamination": contamination,
            "random_state": 42,
            "training_rows": int(len(matrix)),
            "score_space": "decision_function",
            "baseline_type": (
                f"per-user {BASELINE_DAYS}-day mean/pstdev, " f"min {MIN_BASELINE_DAYS} active days"
            ),
            "trained_at": datetime.now(UTC).isoformat(),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        joblib.dump(artifact, out_path)
    return out_path


# ─── Setups ─────────────────────────────────────────────────


@dataclass
class SetupResult:
    name: str
    alerts: dict[tuple[str, date], dict] = field(default_factory=dict)
    peak_priority: dict[str, float] = field(default_factory=dict)


def ml_only(name: str, rows: pd.DataFrame, risk: np.ndarray, preds: np.ndarray) -> SetupResult:
    result = SetupResult(name)
    for (user, day, baseline), r, p in zip(
        rows[["user_id", "day", "baseline"]].itertuples(index=False), risk, preds, strict=True
    ):
        if baseline == "personal":
            result.peak_priority[user] = max(result.peak_priority.get(user, 0.0), float(r))
        if p == -1 and baseline == "personal" and r >= HIGH_RISK:
            result.alerts[(user, day)] = {
                "priority": float(r),
                "score": float(r),
                "categories": "BEHAVIORAL_ANOMALY",
            }
    return result


def risk_engine(
    name: str,
    rows: pd.DataFrame,
    findings: list[dict],
    *,
    risk: np.ndarray | None = None,
    preds: np.ndarray | None = None,
) -> SetupResult:
    """Each person's days, in order, through the platform's risk scoring and alert rule."""
    result = SetupResult(name)
    by_user_day: dict[str, dict[date, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for f in findings:
        by_user_day[f["user_id"]][date.fromisoformat(f["day"])].append(f)

    model_by_user: dict[str, dict[date, float]] = defaultdict(dict)
    if risk is not None and preds is not None:
        for (user, day, baseline), r, p in zip(
            rows[["user_id", "day", "baseline"]].itertuples(index=False), risk, preds, strict=True
        ):
            if p == -1 and baseline == "personal":
                model_by_user[user][day] = float(r)

    days_by_user: dict[str, set[date]] = defaultdict(set)
    for user, day in rows[["user_id", "day"]].itertuples(index=False):
        days_by_user[user].add(day)
    for user, per_day in by_user_day.items():
        days_by_user[user].update(per_day)

    for user, days in days_by_user.items():
        signals: list[RiskSignal] = []
        previous: list[float] = []
        user_findings = by_user_day.get(user, {})
        user_model = model_by_user.get(user, {})
        for day in sorted(days):
            when = datetime(day.year, day.month, day.day, tzinfo=UTC)
            todays = user_findings.get(day, [])
            for f in todays:
                category = AnomalyCategory(f["category"])
                signals.append(
                    RiskSignal(
                        day=when,
                        component=CATEGORY_COMPONENT[category],
                        severity=float(f["severity"]),
                        label=f["title"],
                        category=category,
                    )
                )
            model_today = day in user_model
            if model_today:
                signals.append(
                    RiskSignal(
                        day=when,
                        component=RiskComponent.BEHAVIORAL_ANOMALIES,
                        severity=user_model[day],
                        label="Behavioral model",
                        category=AnomalyCategory.BEHAVIORAL_ANOMALY,
                    )
                )
            signals = [s for s in signals if (when - s.day).days <= 365]
            scored = score_employee(user, when, signals, previous_scores=previous)
            previous.append(scored.score)
            result.peak_priority[user] = max(result.peak_priority.get(user, 0.0), scored.priority)
            if alert_warranted(scored, findings_today=len(todays), model_today=model_today):
                categories = sorted(
                    {f["category"] for f in todays}
                    | ({"BEHAVIORAL_ANOMALY"} if model_today else set())
                )
                result.alerts[(user, day)] = {
                    "priority": scored.priority,
                    "score": scored.score,
                    "level": scored.level.value,
                    "categories": ";".join(categories),
                }
                # A raised alert becomes part of the person's security history.
                signals.append(
                    RiskSignal(
                        day=when,
                        component=RiskComponent.HISTORICAL_SECURITY_EVENTS,
                        severity=50.0,
                        label="Earlier alert",
                    )
                )
    return result


# ─── Metrics ────────────────────────────────────────────────


def auc(positive: list[float], negative: list[float]) -> float | None:
    """Probability a random insider outranks a random other person (ties count half)."""
    if not positive or not negative:
        return None
    ranks = pd.Series(positive + negative).rank(method="average").to_numpy()
    pos_rank_sum = ranks[: len(positive)].sum()
    return float(
        (pos_rank_sum - len(positive) * (len(positive) + 1) / 2) / (len(positive) * len(negative))
    )


def evaluate_setup(
    setup: SetupResult,
    insiders: dict[str, Insider],
    *,
    eval_start: date,
    eval_end: date,
    population: set[str],
    active_malicious: set[tuple[str, date]],
) -> dict:
    alerts = {k: v for k, v in setup.alerts.items() if eval_start <= k[1] <= eval_end}

    def in_window(d: date) -> bool:
        return eval_start <= d <= eval_end

    # Only insiders whose malicious activity falls inside the evaluated days.
    in_scope = {u: i for u, i in insiders.items() if any(map(in_window, i.malicious_days))}
    malicious = {(u, d) for u, i in in_scope.items() for d in i.malicious_days if in_window(d)}
    hits = [k for k in alerts if k in malicious]

    detected, delays, per_scenario = {}, [], defaultdict(lambda: [0, 0])
    for user, insider in in_scope.items():
        days = sorted(d for d in insider.malicious_days if in_window(d))
        caught = sorted(d for (u, d) in alerts if u == user and d in insider.malicious_days)
        detected[user] = bool(caught)
        per_scenario[insider.scenario][1] += 1
        if caught:
            per_scenario[insider.scenario][0] += 1
            delays.append((caught[0] - days[0]).days)

    normal_users = population - set(insiders)
    fp_users = {u for (u, _) in alerts if u in normal_users}
    eval_days = max((eval_end - eval_start).days + 1, 1)
    positive = [setup.peak_priority.get(u, 0.0) for u in in_scope]
    negative = [setup.peak_priority.get(u, 0.0) for u in normal_users]
    k = len(in_scope)
    top_k = sorted(setup.peak_priority.items(), key=lambda kv: -kv[1])[:k]

    reachable = malicious & active_malicious
    return {
        "setup": setup.name,
        "alert_user_days": len(alerts),
        "alerts_per_day": round(len(alerts) / eval_days, 2),
        "insiders_in_scope": len(in_scope),
        "insiders_detected": sum(detected.values()),
        "insider_detection_rate": round(sum(detected.values()) / len(in_scope), 3)
        if in_scope
        else None,
        "by_scenario": {
            str(s): {"detected": c[0], "insiders": c[1]} for s, c in sorted(per_scenario.items())
        },
        "median_days_to_detect": float(np.median(delays)) if delays else None,
        "malicious_user_days": len(reachable),
        "malicious_days_alerted": len(set(hits) & reachable),
        "day_recall": round(len(set(hits) & reachable) / len(reachable), 3) if reachable else None,
        "day_precision": round(len(hits) / len(alerts), 3) if alerts else None,
        "false_positive_users": len(fp_users),
        "false_positive_user_rate": round(len(fp_users) / len(normal_users), 3)
        if normal_users
        else None,
        "alerted_user_precision": round(
            len({u for (u, _) in alerts if u in in_scope}) / len({u for (u, _) in alerts}), 3
        )
        if alerts
        else None,
        "ranking_auc": None if (a := auc(positive, negative)) is None else round(a, 3),
        "insiders_in_top_k": sum(1 for u, _ in top_k if u in in_scope),
    }


def detector_table(
    findings: list[dict], insiders: dict[str, Insider], eval_start: date
) -> list[dict]:
    malicious = {(u, d) for u, i in insiders.items() for d in i.malicious_days}
    table: dict[str, dict] = defaultdict(
        lambda: {"findings": 0, "on_malicious_days": 0, "insiders": set(), "other_users": set()}
    )
    for f in findings:
        day = date.fromisoformat(f["day"])
        if day < eval_start:
            continue
        row = table[f["detector"]]
        row["findings"] += 1
        if (f["user_id"], day) in malicious:
            row["on_malicious_days"] += 1
        (row["insiders"] if f["user_id"] in insiders else row["other_users"]).add(f["user_id"])
    return [
        {
            "detector": name,
            "findings": r["findings"],
            "on_malicious_days": r["on_malicious_days"],
            "precision": round(r["on_malicious_days"] / r["findings"], 3)
            if r["findings"]
            else None,
            "insiders_flagged": len(r["insiders"]),
            "other_users_flagged": len(r["other_users"]),
        }
        for name, r in sorted(table.items())
    ]


# ─── Report ─────────────────────────────────────────────────


def write_report(out: Path, summary: dict) -> None:
    lines = [
        "# ITBIS detection evaluation — CERT Insider Threat r4.2",
        "",
        f"Generated {summary['generated_at']}. Evaluation period {summary['eval_start']} → "
        f"{summary['eval_end']}; models trained / baselines warmed up before "
        f"{summary['train_end']}.",
        "",
        f"Population {summary['population']} people; {summary['insiders_total']} red-team insiders "
        f"in the dataset, {summary['setups'][0]['insiders_in_scope']} active in the "
        "evaluation period.",
        "",
        "## Headline",
        "",
        "| Setup | Insiders detected | Scenario 1 | Scenario 2 | Scenario 3 "
        "| Median days to detect "
        "| Alerts / day | False-positive people | Day precision | Ranking AUC |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summary["setups"]:
        scen = {k: f"{v['detected']}/{v['insiders']}" for k, v in s["by_scenario"].items()}
        lines.append(
            f"| {s['setup']} | {s['insiders_detected']}/{s['insiders_in_scope']} "
            f"({(s['insider_detection_rate'] or 0):.0%}) | {scen.get('1', '–')} "
            f"| {scen.get('2', '–')} "
            f"| {scen.get('3', '–')} | {s['median_days_to_detect']} | {s['alerts_per_day']} "
            f"| {s['false_positive_users']} ({(s['false_positive_user_rate'] or 0):.1%}) "
            f"| {s['day_precision']} | {s['ranking_auc']} |"
        )
    lines += [
        "",
        "## Detectors (evaluation period)",
        "",
        "| Detector | Findings | On malicious days | Precision | Insiders flagged "
        "| Other people flagged |",
        "|---|---|---|---|---|---|",
    ]
    for d in summary["detectors"]:
        lines.append(
            f"| {d['detector']} | {d['findings']} | {d['on_malicious_days']} | {d['precision']} "
            f"| {d['insiders_flagged']} | {d['other_users_flagged']} |"
        )
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in summary["caveats"]] + [""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


# ─── Main ───────────────────────────────────────────────────


def evaluate(
    run_dir: Path,
    answers_dir: Path,
    *,
    train_end: date,
    eval_start: date,
    v2_path: Path,
    v3_path: Path,
) -> dict:
    began = time.monotonic()
    df = load_features(run_dir)
    findings = load_findings(run_dir)
    insiders = load_insiders(answers_dir)
    grid = Grid.from_features(df)
    means, stds, active_days = rolling_baselines(grid)
    log.info(
        "evaluate.loaded",
        users=len(grid.users),
        days=len(grid.days),
        active_user_days=int(grid.active.sum()),
        findings=len(findings),
    )

    v2 = ModelService(artifact_path=str(v2_path))
    art = v2.get_artifact()
    model_features = list(art.model_features)
    rows_v2, matrix_v2 = model_inputs(
        grid,
        means,
        stds,
        active_days,
        global_means=art.global_means,
        global_stds=art.global_stds,
        model_features=model_features,
    )
    preds_v2, dec_v2 = score_with(v2, matrix_v2)
    risk_v2 = risk_from_decision(dec_v2, art.score_low, art.score_high)

    train_mask_rows = np.array([d < train_end for d in rows_v2["day"]])
    train_base = df[df["day"] < train_end]
    g_means = {n: float(train_base[n].mean()) for n in FEATURE_NAMES}
    g_stds = {n: float(train_base[n].std(ddof=0)) for n in FEATURE_NAMES}
    rows_v3, matrix_v3 = model_inputs(
        grid,
        means,
        stds,
        active_days,
        global_means=g_means,
        global_stds=g_stds,
        model_features=model_features,
    )
    train_model(
        matrix_v3[train_mask_rows],
        model_features,
        global_means=g_means,
        global_stds=g_stds,
        metadata={
            "model_version": "itbis_behavior_v3",
            "training_start": str(grid.days[0]),
            "training_end": str(train_end),
            "trained_on": "CERT r4.2 replay (all users)",
        },
        out_path=v3_path,
    )
    v3 = ModelService(artifact_path=str(v3_path))
    art3 = v3.get_artifact()
    preds_v3, dec_v3 = score_with(v3, matrix_v3)
    risk_v3 = risk_from_decision(dec_v3, art3.score_low, art3.score_high)
    log.info(
        "evaluate.scored",
        rows=len(rows_v2),
        v2_anomalies=int((preds_v2 == -1).sum()),
        v3_anomalies=int((preds_v3 == -1).sum()),
    )

    setups = [
        ml_only("ml_only_v2", rows_v2, risk_v2, preds_v2),
        ml_only("ml_only_v3", rows_v3, risk_v3, preds_v3),
        risk_engine("detectors_only", rows_v2, findings),
        risk_engine("risk_engine_v2", rows_v2, findings, risk=risk_v2, preds=preds_v2),
        risk_engine("risk_engine_v3", rows_v3, findings, risk=risk_v3, preds=preds_v3),
    ]
    eval_end = grid.days[-1]
    population = set(grid.users)
    active_pairs = set(zip(rows_v2["user_id"], rows_v2["day"], strict=True))
    metrics = [
        evaluate_setup(
            s,
            insiders,
            eval_start=eval_start,
            eval_end=eval_end,
            population=population,
            active_malicious=active_pairs,
        )
        for s in setups
    ]

    malicious = {(u, d) for u, i in insiders.items() for d in i.malicious_days}
    for s in setups:
        alert_rows = [
            {
                "user_id": u,
                "day": d.isoformat(),
                "malicious_day": (u, d) in malicious,
                "insider": u in insiders,
                **info,
            }
            for (u, d), info in sorted(s.alerts.items(), key=lambda kv: kv[0][1])
        ]
        pd.DataFrame(alert_rows).to_csv(run_dir / f"alerts_{s.name}.csv", index=False)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "train_end": train_end.isoformat(),
        "eval_start": eval_start.isoformat(),
        "eval_end": eval_end.isoformat(),
        "population": len(population),
        "insiders_total": len(insiders),
        "models": {
            "v2": str(v2_path),
            "v3": str(v3_path),
            "v3_training_rows": int(train_mask_rows.sum()),
        },
        "setups": metrics,
        "detectors": detector_table(findings, insiders, eval_start),
        "caveats": [
            "The shipped v2 model was trained on 2010-01-02 → 2010-12-17 of this same "
            "dataset, which "
            "overlaps the evaluation period and contains insider activity; its numbers are "
            "optimistic. "
            "v3 is trained only on days before the evaluation period.",
            "Web categories (leak sites, job boards, keylogger vendors) are hand-maintained "
            "lists that "
            "include domains used in the dataset's scenarios; detectors depending on them are "
            "likely "
            "to generalise less well than their scores here suggest.",
            "Machine owners are inferred from the full logon history (standing in for an "
            "asset register).",
            "r4.2 is a 'dense needles' dataset with far more insider activity than a real "
            "organisation, "
            "which inflates precision compared with production.",
            "Historical security events are the evaluated system's own earlier alerts "
            "(there are no analyst "
            "decisions in a replay).",
            "Malicious days are days with red-team activity logged under the insider's own "
            "account; "
            "scenario 3's use of the supervisor's account is not labelled.",
        ],
        "runtime_seconds": round(time.monotonic() - began, 1),
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    write_report(run_dir, summary)
    log.info("evaluate.done", runtime_seconds=summary["runtime_seconds"])
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--run", type=Path, required=True, help="replay output directory")
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--train-end", type=date.fromisoformat, default=date(2010, 7, 1))
    parser.add_argument("--eval-start", type=date.fromisoformat, default=date(2010, 7, 1))
    parser.add_argument("--v2", type=Path, default=Path(DEFAULT_ARTIFACT_PATH))
    parser.add_argument(
        "--v3",
        type=Path,
        default=Path(DEFAULT_ARTIFACT_PATH).with_name("itbis_behavior_model_v3.joblib"),
    )
    args = parser.parse_args()
    summary = evaluate(
        args.run,
        args.answers,
        train_end=args.train_end,
        eval_start=args.eval_start,
        v2_path=args.v2,
        v3_path=args.v3,
    )
    for s in summary["setups"]:
        print(
            f"{s['setup']:<16} detected {s['insiders_detected']}/{s['insiders_in_scope']}  "
            f"alerts/day {s['alerts_per_day']}  fp people {s['false_positive_users']}  "
            f"auc {s['ranking_auc']}"
        )


if __name__ == "__main__":
    main()

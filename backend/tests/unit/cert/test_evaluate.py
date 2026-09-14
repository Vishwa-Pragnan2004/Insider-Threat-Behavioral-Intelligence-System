"""
ITBIS — Unit tests: CERT evaluation pass B (baselines, model input parity, metrics).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.modules.anomaly.application.feature_prep import build_32_features
from app.modules.anomaly.application.risk_scoring import risk_score_from_decision
from app.modules.behavioral.domain.enums import FEATURE_NAMES
from evaluation.cert.cert_io import Insider
from evaluation.cert.evaluate import (
    Grid,
    SetupResult,
    auc,
    evaluate_setup,
    model_inputs,
    risk_engine,
    risk_from_decision,
    rolling_baselines,
)
from tests.unit.anomaly.test_anomaly_detection_service import (  # noqa: F401 - fixture
    _make_baseline,
    _make_row,
    model_service,
)

DAY0 = date(2010, 1, 1)


def _features(rows: list[tuple[str, int, dict[str, float]]]) -> pd.DataFrame:
    records = []
    for user, offset, values in rows:
        record = {"user_id": user, "day": DAY0 + timedelta(days=offset), "event_count": 1}
        record |= {n: float(values.get(n, 0.0)) for n in FEATURE_NAMES}
        records.append(record)
    return pd.DataFrame(records)


def test_rolling_baselines_count_inactive_days_as_zero_and_exclude_today():
    rows = [("u", d, {"logon_count": 2.0}) for d in range(0, 30, 2)]  # every other day
    grid = Grid.from_features(_features(rows))
    means, stds, active = rolling_baselines(grid, window=4)
    i = FEATURE_NAMES.index("logon_count")

    # Day 8: previous 4 days are 4,5,6,7 -> active on 4 and 6 -> values 2,0,2,0.
    assert active[0, 8] == 2
    assert means[0, 8, i] == pytest.approx(1.0)
    assert stds[0, 8, i] == pytest.approx(1.0)
    assert active[0, 0] == 0 and means[0, 0, i] == 0.0


def test_model_input_matches_the_live_feature_builder(model_service):  # noqa: F811
    rng = np.random.default_rng(7)
    rows = [("u", d, {n: float(rng.integers(0, 6)) for n in FEATURE_NAMES}) for d in range(40)]
    grid = Grid.from_features(_features(rows))
    art = model_service.get_artifact()
    means, stds, active = rolling_baselines(grid)
    table, matrix = model_inputs(
        grid,
        means,
        stds,
        active,
        global_means=art.global_means,
        global_stds=art.global_stds,
        model_features=list(art.model_features),
    )

    for day_index in (2, 35):  # one global-baseline day, one personal-baseline day
        row_index = int(np.nonzero(table["day"].to_numpy() == grid.days[day_index])[0][0])
        live_row = _make_row(
            "u",
            values=dict(zip(FEATURE_NAMES, grid.values[0, day_index], strict=True)),
            window_start=datetime.combine(grid.days[day_index], datetime.min.time(), UTC),
        )
        baseline = None
        if table.loc[row_index, "baseline"] == "personal":
            baseline = _make_baseline(
                "u",
                means=dict(zip(FEATURE_NAMES, means[0, day_index], strict=True)),
                stds=dict(zip(FEATURE_NAMES, stds[0, day_index], strict=True)),
            )
        live = build_32_features(live_row, baseline, art)
        assert live.baseline_source == table.loc[row_index, "baseline"]
        assert matrix[row_index] == pytest.approx(live.vector)


def test_vectorised_risk_matches_the_platform_mapping():
    decisions = np.array([0.3, 0.1, 0.0, -0.01, -0.05, -1.0])
    expected = [risk_score_from_decision(d, -0.04, 0.25) for d in decisions]
    assert risk_from_decision(decisions, -0.04, 0.25) == pytest.approx(expected)


def test_auc():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1], [1]) == 0.5
    assert auc([], [1]) is None


def test_risk_engine_alerts_on_findings_and_metrics_score_them():
    rows = pd.DataFrame(
        {
            "user_id": ["jane", "jane", "bob"],
            "day": [DAY0, DAY0 + timedelta(days=1), DAY0],
            "baseline": ["personal"] * 3,
        }
    )
    findings = [
        {
            "user_id": "jane",
            "day": (DAY0 + timedelta(days=1)).isoformat(),
            "category": "ABNORMAL_DATA_DOWNLOAD",
            "detector": "abnormal_data_download",
            "severity": 80.0,
            "title": "Abnormal data download / upload",
        },
        {
            "user_id": "bob",
            "day": DAY0.isoformat(),
            "category": "INSIDER_RISK_INDICATOR",
            "detector": "insider_risk_indicators",
            "severity": 40.0,
            "title": "Job-search activity",
        },
    ]
    setup = risk_engine("detectors_only", rows, findings)
    assert list(setup.alerts) == [("jane", DAY0 + timedelta(days=1))]

    insiders = {
        "jane": Insider("jane", 1, datetime.now(UTC), datetime.now(UTC), {DAY0 + timedelta(days=1)})
    }
    metrics = evaluate_setup(
        setup,
        insiders,
        eval_start=DAY0,
        eval_end=DAY0 + timedelta(days=1),
        population={"jane", "bob"},
        active_malicious={("jane", DAY0 + timedelta(days=1))},
    )
    assert metrics["insiders_detected"] == 1 and metrics["false_positive_users"] == 0
    assert metrics["day_precision"] == 1.0 and metrics["day_recall"] == 1.0
    assert metrics["median_days_to_detect"] == 0.0 and metrics["ranking_auc"] == 1.0
    empty = evaluate_setup(
        SetupResult("none"),
        insiders,
        eval_start=DAY0,
        eval_end=DAY0,
        population={"jane", "bob"},
        active_malicious=set(),
    )
    assert empty["insiders_detected"] == 0 and empty["day_precision"] is None


def test_insiders_active_only_after_the_window_are_out_of_scope():
    later = Insider("late", 2, datetime.now(UTC), datetime.now(UTC), {DAY0 + timedelta(days=90)})
    metrics = evaluate_setup(
        SetupResult("none"),
        {"late": later},
        eval_start=DAY0,
        eval_end=DAY0 + timedelta(days=30),
        population={"late", "bob"},
        active_malicious=set(),
    )
    assert metrics["insiders_in_scope"] == 0 and metrics["insider_detection_rate"] is None

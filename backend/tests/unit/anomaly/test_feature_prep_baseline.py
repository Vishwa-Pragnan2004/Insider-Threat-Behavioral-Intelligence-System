"""
ITBIS — Unit tests: personal baselines in the model's input vector.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.anomaly.application.feature_prep import build_32_features
from app.modules.behavioral.domain.enums import FEATURE_NAMES
from tests.unit.anomaly.test_anomaly_detection_service import (  # noqa: F401 - fixture
    _make_baseline,
    _make_row,
    model_service,
)


def test_a_personal_mean_of_zero_is_kept(model_service):  # noqa: F811
    """
    Regression: someone who never uses USB has a personal mean of 0. That was
    treated as missing and replaced by the population mean, which made their
    first USB use look ordinary.
    """
    art = model_service.get_artifact()
    baseline = _make_baseline(
        "alice",
        means={n: 0.0 for n in FEATURE_NAMES} | {"logon_count": 2.0},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    row = _make_row(
        values={"usb_activity_count": 3.0, "logon_count": 2.0},
        window_start=datetime(2010, 8, 1, tzinfo=UTC),
    )

    prepared = build_32_features(row, baseline, art)

    assert prepared.baseline_source == "personal"
    assert prepared.baseline_means["usb_activity_count"] == 0.0
    assert prepared.zscores["usb_activity_count"] == pytest.approx(3.0)
    assert prepared.zscores["logon_count"] == pytest.approx(0.0)

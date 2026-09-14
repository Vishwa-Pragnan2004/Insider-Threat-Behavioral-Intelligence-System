"""
ITBIS — Unit tests: alert response timestamps.

`acknowledged_at` and `resolved_at` feed the Security Manager's compliance
metrics (time to acknowledge, time to resolve, critical-alert SLA).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.modules.alerts.domain.entities import Alert
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.alerts.infrastructure.mongo_alert_repository import MongoAlertRepository


def _alert() -> Alert:
    start = datetime(2026, 9, 1, tzinfo=UTC)
    return Alert(
        idempotency_key="k",
        anomaly_result_id=uuid.uuid4(),
        user_id="insider.jane",
        source_dataset="all",
        window="daily",
        window_start=start,
        window_end=start,
        model_version="v",
        feature_version="f",
        title="t",
        description="d",
        risk_score=90.0,
        risk_level="CRITICAL",
        severity=AlertSeverity.CRITICAL,
    )


def test_new_alert_has_no_response_times():
    alert = _alert()
    assert alert.acknowledged_at is None and alert.resolved_at is None


def test_first_action_is_the_acknowledgement_and_is_kept():
    alert = _alert()
    alert.change_status(AlertStatus.ACKNOWLEDGED)
    first = alert.acknowledged_at
    alert.change_status(AlertStatus.IN_PROGRESS)

    assert first is not None
    assert alert.acknowledged_at == first
    assert alert.resolved_at is None


def test_resolving_straight_from_open_sets_both():
    alert = _alert()
    alert.change_status(AlertStatus.FALSE_POSITIVE)
    assert alert.acknowledged_at is not None
    assert alert.resolved_at == alert.acknowledged_at


def test_retrying_the_same_status_changes_nothing():
    alert = _alert()
    alert.change_status(AlertStatus.OPEN)
    assert alert.acknowledged_at is None


def test_response_times_survive_storage():
    alert = _alert()
    alert.change_status(AlertStatus.RESOLVED)
    doc = MongoAlertRepository._to_doc(alert)
    doc["created_at"] = alert.created_at.isoformat()  # older rows may hold strings

    restored = MongoAlertRepository._from_doc(doc)

    assert restored.acknowledged_at == alert.acknowledged_at
    assert restored.resolved_at == alert.resolved_at


def test_legacy_documents_without_response_times_still_load():
    doc = MongoAlertRepository._to_doc(_alert())
    del doc["acknowledged_at"], doc["resolved_at"]
    restored = MongoAlertRepository._from_doc(doc)
    assert restored.acknowledged_at is None and restored.resolved_at is None

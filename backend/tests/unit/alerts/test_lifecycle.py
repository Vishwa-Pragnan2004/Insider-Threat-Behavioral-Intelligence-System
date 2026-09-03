"""
ITBIS — Unit tests: Alert lifecycle (status transitions, assignment,
investigation linking, idempotency key).

Covers:
  - allowed transitions from each state
  - rejection of illegal transitions
  - self-loops are silent no-ops
  - change_status and assign bump updated_at
  - investigation linking
  - compute_idempotency_key is deterministic and content-based
"""
from datetime import UTC, datetime

import pytest

from app.modules.alerts.application.alert_generation_service import (
    compute_idempotency_key,
)
from app.modules.alerts.domain.entities import (
    Alert,
    allowed_next_statuses,
    is_valid_transition,
)
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus

# ─── is_valid_transition / allowed_next_statuses ─────────


def test_valid_transition_open_to_acknowledged():
    assert is_valid_transition(AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)


def test_valid_transition_open_to_in_progress():
    assert is_valid_transition(AlertStatus.OPEN, AlertStatus.IN_PROGRESS)


def test_valid_transition_open_to_resolved():
    assert is_valid_transition(AlertStatus.OPEN, AlertStatus.RESOLVED)


def test_valid_transition_open_to_false_positive():
    assert is_valid_transition(AlertStatus.OPEN, AlertStatus.FALSE_POSITIVE)


def test_valid_transition_acknowledged_to_in_progress():
    assert is_valid_transition(AlertStatus.ACKNOWLEDGED, AlertStatus.IN_PROGRESS)


def test_valid_transition_acknowledged_to_resolved():
    assert is_valid_transition(AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED)


def test_valid_transition_in_progress_to_resolved():
    assert is_valid_transition(AlertStatus.IN_PROGRESS, AlertStatus.RESOLVED)


def test_valid_transition_in_progress_back_to_acknowledged():
    assert is_valid_transition(AlertStatus.IN_PROGRESS, AlertStatus.ACKNOWLEDGED)


def test_valid_transition_resolved_back_to_in_progress_is_illegal():
    """For alerts, RESOLVED is terminal — must NOT go back to IN_PROGRESS."""
    assert not is_valid_transition(AlertStatus.RESOLVED, AlertStatus.IN_PROGRESS)


def test_valid_transition_acknowledged_to_false_positive():
    assert is_valid_transition(
        AlertStatus.ACKNOWLEDGED, AlertStatus.FALSE_POSITIVE
    )


def test_resolved_to_false_positive_is_illegal():
    # Once resolved, an alert is terminal — it can't be re-categorised.
    assert not is_valid_transition(
        AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE
    )


# ─── illegal transitions ─────────────────────────────────


def test_illegal_resolved_to_open():
    """RESOLVED is not allowed to skip back to OPEN (must go through IN_PROGRESS)."""
    assert not is_valid_transition(AlertStatus.RESOLVED, AlertStatus.OPEN)


def test_illegal_resolved_to_acknowledged():
    assert not is_valid_transition(AlertStatus.RESOLVED, AlertStatus.ACKNOWLEDGED)


def test_alert_resolved_is_terminal():
    """RESOLVED is a terminal state for alerts."""
    for target in AlertStatus:
        if target == AlertStatus.RESOLVED:
            continue
        assert not is_valid_transition(AlertStatus.RESOLVED, target), (
            f"RESOLVED should be terminal but allowed {target}"
        )


def test_illegal_false_positive_is_terminal():
    for target in AlertStatus:
        if target == AlertStatus.FALSE_POSITIVE:
            continue
        assert not is_valid_transition(AlertStatus.FALSE_POSITIVE, target), (
            f"FALSE_POSITIVE should be terminal but allowed transition to {target}"
        )


def test_self_loop_is_not_a_valid_transition():
    for s in AlertStatus:
        assert not is_valid_transition(s, s)


def test_allowed_next_statuses_resolved_is_empty():
    assert allowed_next_statuses(AlertStatus.RESOLVED) == set()


def test_allowed_next_statuses_false_positive_is_empty():
    assert allowed_next_statuses(AlertStatus.FALSE_POSITIVE) == set()


# ─── entity change_status + assign + investigation linking ─


def _make_alert(**overrides) -> Alert:
    defaults = dict(
        idempotency_key="k",
        anomaly_result_id=__import__("uuid").uuid4(),
        user_id="u",
        source_dataset="cert",
        window="daily",
        window_start=datetime(2026, 8, 1, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, tzinfo=UTC),
        model_version="m",
        feature_version="f",
        title="t",
        description="d",
        risk_score=80.0,
        risk_level="CRITICAL",
        severity=AlertSeverity.CRITICAL,
        status=AlertStatus.OPEN,
    )
    defaults.update(overrides)
    return Alert(**defaults)


def test_change_status_updates_status_and_bumps_updated_at():
    a = _make_alert()
    original = a.updated_at
    a.change_status(AlertStatus.ACKNOWLEDGED)
    assert a.status == AlertStatus.ACKNOWLEDGED
    assert a.updated_at >= original


def test_self_loop_change_status_is_noop():
    a = _make_alert()
    original = a.updated_at
    a.change_status(AlertStatus.OPEN)  # self-loop
    assert a.status == AlertStatus.OPEN
    # updated_at is NOT bumped on a no-op self-loop
    assert a.updated_at == original


def test_change_status_to_illegal_target_raises():
    a = _make_alert()
    a.change_status(AlertStatus.RESOLVED)
    # RESOLVED -> OPEN is illegal
    with pytest.raises(ValueError):
        a.change_status(AlertStatus.OPEN)


def test_assign_sets_assigned_to_and_bumps_updated_at():
    a = _make_alert()
    original = a.updated_at
    a.assign("alice")
    assert a.assigned_to == "alice"
    assert a.updated_at >= original


def test_link_investigation_stores_id():
    a = _make_alert()
    inv_id = __import__("uuid").uuid4()
    a.link_investigation(inv_id)
    assert a.investigation_id == inv_id


# ─── idempotency key ────────────────────────────────────


def test_idempotency_key_is_deterministic():
    ws = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    k1 = compute_idempotency_key(
        user_id="u", window="daily", window_start=ws, model_version="m"
    )
    k2 = compute_idempotency_key(
        user_id="u", window="daily", window_start=ws, model_version="m"
    )
    assert k1 == k2


def test_idempotency_key_differs_per_user():
    ws = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    a = compute_idempotency_key(user_id="a", window="daily", window_start=ws, model_version="m")
    b = compute_idempotency_key(user_id="b", window="daily", window_start=ws, model_version="m")
    assert a != b


def test_idempotency_key_differs_per_window_start():
    a = compute_idempotency_key(
        user_id="u",
        window="daily",
        window_start=datetime(2026, 8, 1, tzinfo=UTC),
        model_version="m",
    )
    b = compute_idempotency_key(
        user_id="u",
        window="daily",
        window_start=datetime(2026, 8, 2, tzinfo=UTC),
        model_version="m",
    )
    assert a != b


def test_idempotency_key_differs_per_model_version():
    ws = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    a = compute_idempotency_key(user_id="u", window="daily", window_start=ws, model_version="v1")
    b = compute_idempotency_key(user_id="u", window="daily", window_start=ws, model_version="v2")
    assert a != b

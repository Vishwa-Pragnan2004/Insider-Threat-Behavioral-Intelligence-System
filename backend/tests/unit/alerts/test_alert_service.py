"""
ITBIS — Unit tests: AlertService (lifecycle, assignment, link).

Covers:
  - acknowledge moves OPEN -> ACKNOWLEDGED
  - change_status validates transitions
  - illegal transitions raise IllegalAlertStatusTransitionError
  - self-loops are no-ops
  - assign + link_investigation
  - get raises AlertNotFoundError on miss
  - list filters
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.modules.alerts.application.alert_service import AlertService
from app.modules.alerts.domain.entities import Alert
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.alerts.domain.exceptions import (
    AlertNotFoundError,
    IllegalAlertStatusTransitionError,
)
from app.modules.alerts.domain.repositories import IAlertRepository

# ─── Fake (delegates to real dict) ───────────────────────


class FakeAlertRepository(IAlertRepository):
    def __init__(self) -> None:
        self.docs: dict[str, Alert] = {}
        self.by_id: dict[uuid.UUID, Alert] = {}

    async def upsert(self, alert: Alert) -> tuple[Alert, bool]:
        existing = self.docs.get(alert.idempotency_key)
        self.docs[alert.idempotency_key] = alert
        self.by_id[alert.id] = alert
        return alert, existing is not None

    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        return self.by_id.get(alert_id)

    async def _build_query(self, **kw):
        return kw

    async def list_alerts(self, **kwargs):
        items = list(self.docs.values())
        for k, v in kwargs.items():
            if v is None or k in ("skip", "limit"):
                continue
            items = [
                a for a in items if (
                    getattr(a, k) == v
                    or (k == "status" and getattr(a, k) == getattr(v, "value", v))
                )
            ]
        items.sort(key=lambda a: a.created_at, reverse=True)
        return items[kwargs.get("skip", 0):][: kwargs.get("limit", 50)]

    async def count_alerts(self, **kwargs):
        items = await self.list_alerts(
            **{k: v for k, v in kwargs.items() if k not in ("skip", "limit")}
        )
        return len(items)

    async def update(self, alert: Alert) -> Alert:
        self.docs[alert.idempotency_key] = alert
        self.by_id[alert.id] = alert
        return alert


def _make_alert(**overrides) -> Alert:
    defaults = dict(
        idempotency_key=f"k-{uuid.uuid4()}",
        anomaly_result_id=uuid.uuid4(),
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


class FakeUserDirectory:
    """Permissive user-existence stub — tests can override `exists`."""

    def __init__(self) -> None:
        self.exists_map: dict[str, bool] = {}

    async def user_exists(self, user_id: str) -> bool:
        return self.exists_map.get(user_id, True)


@pytest.fixture
def service():
    repo = FakeAlertRepository()
    user_dir = FakeUserDirectory()
    return repo, AlertService(repo, user_directory=user_dir), user_dir


# ─── get / not-found ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_alert_by_id(service):
    repo, svc, _ = service
    a = _make_alert()
    repo.by_id[a.id] = a
    repo.docs[a.idempotency_key] = a
    got = await svc.get(a.id)
    assert got.id == a.id


@pytest.mark.asyncio
async def test_get_raises_on_missing_id(service):
    _, svc, _ = service
    with pytest.raises(AlertNotFoundError):
        await svc.get(uuid.uuid4())


# ─── acknowledge / change_status ─────────────────────────


@pytest.mark.asyncio
async def test_acknowledge_moves_open_to_acknowledged(service):
    repo, svc, _ = service
    a = _make_alert()
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    saved = await svc.acknowledge(a.id)
    assert saved.status == AlertStatus.ACKNOWLEDGED


@pytest.mark.asyncio
async def test_change_status_walks_full_lifecycle(service):
    repo, svc, _ = service
    a = _make_alert()
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    await svc.acknowledge(a.id)
    await svc.change_status(a.id, AlertStatus.IN_PROGRESS)
    await svc.change_status(a.id, AlertStatus.RESOLVED)
    final = await svc.get(a.id)
    assert final.status == AlertStatus.RESOLVED


@pytest.mark.asyncio
async def test_illegal_transition_raises_409(service):
    repo, svc, _ = service
    a = _make_alert(status=AlertStatus.RESOLVED)
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    # RESOLVED -> OPEN is illegal (must go through IN_PROGRESS).
    with pytest.raises(IllegalAlertStatusTransitionError):
        await svc.change_status(a.id, AlertStatus.OPEN)


@pytest.mark.asyncio
async def test_illegal_transition_from_resolved_terminal(service):
    repo, svc, _ = service
    a = _make_alert(status=AlertStatus.RESOLVED)  # RESOLVED is a terminal state
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    with pytest.raises(IllegalAlertStatusTransitionError):
        await svc.change_status(a.id, AlertStatus.ACKNOWLEDGED)


@pytest.mark.asyncio
async def test_self_loop_change_status_is_noop(service):
    repo, svc, _ = service
    a = _make_alert(status=AlertStatus.OPEN)
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    out = await svc.change_status(a.id, AlertStatus.OPEN)
    assert out.status == AlertStatus.OPEN


# ─── assign / link ────────────────────────────────────────


@pytest.mark.asyncio
async def test_assign_stores_user_id(service):
    repo, svc, _ = service
    a = _make_alert()
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    saved = await svc.assign(a.id, "alice")
    assert saved.assigned_to == "alice"


@pytest.mark.asyncio
async def test_assign_reassign_overwrites(service):
    repo, svc, _ = service
    a = _make_alert()
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    await svc.assign(a.id, "alice")
    saved = await svc.assign(a.id, "bob")
    assert saved.assigned_to == "bob"


# ─── list with filters ───────────────────────────────────


@pytest.mark.asyncio
async def test_list_filters_by_status(service):
    repo, svc, _ = service
    for s in [AlertStatus.OPEN, AlertStatus.OPEN, AlertStatus.RESOLVED]:
        a = _make_alert(status=s)
        repo.docs[a.idempotency_key] = a
        repo.by_id[a.id] = a
    items, total = await svc.list(status=AlertStatus.OPEN)
    assert total == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_list_pagination(service):
    repo, svc, _ = service
    for _ in range(5):
        a = _make_alert()
        repo.docs[a.idempotency_key] = a
        repo.by_id[a.id] = a
    items, total = await svc.list(skip=2, limit=2)
    assert total == 5
    assert len(items) == 2


# ─── FIX 3: assignment validates that the target user exists ────────


@pytest.mark.asyncio
async def test_assign_alert_to_existing_user_succeeds(service):
    """Sanity check: a real (or permissive) user lookup allows assign."""
    repo, svc, _user_dir = service
    a = _make_alert()
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    saved = await svc.assign(a.id, "some-real-user-id")
    assert saved.assigned_to == "some-real-user-id"


@pytest.mark.asyncio
async def test_assign_alert_to_nonexistent_user_raises(service):
    """FIX 3: assigning to a non-existent user raises AssigneeNotFoundError
    and does not persist any change."""
    from app.modules.alerts.domain.exceptions import AssigneeNotFoundError

    repo, svc, user_dir = service
    a = _make_alert()
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    # Configure the directory to reject this user id.
    user_dir.exists_map["ghost-user"] = False

    with pytest.raises(AssigneeNotFoundError) as exc_info:
        await svc.assign(a.id, "ghost-user")
    assert "ghost-user" in str(exc_info.value)

    # The alert is not updated in the repo (no row-level update was issued).
    assert repo.docs[a.idempotency_key].assigned_to is None


@pytest.mark.asyncio
async def test_assign_alert_to_existing_user_does_not_raise(service):
    repo, svc, user_dir = service
    a = _make_alert()
    repo.docs[a.idempotency_key] = a
    repo.by_id[a.id] = a
    user_dir.exists_map["real-user"] = True

    # No exception.
    saved = await svc.assign(a.id, "real-user")
    assert saved.assigned_to == "real-user"

"""
ITBIS — Unit tests for the FeatureEngineeringService.

Uses fakes for the feature store, baseline repo, and event source so no
SQL/Mongo is required.  Covers CERT and agent events in the same flow.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.behavioral.application.services.feature_engineering_service import (
    FeatureEngineeringService,
)
from app.modules.behavioral.domain.entities import BehavioralBaseline, BehavioralFeatures
from app.modules.behavioral.domain.enums import FEATURE_VERSION
from app.modules.behavioral.domain.exceptions import NoDataForBaselineError
from app.modules.behavioral.domain.repositories import (
    IBehavioralBaselineRepository,
    IBehavioralEventSource,
    IBehavioralFeatureStore,
)

# ─── Fakes ────────────────────────────────────────────────


class FakeFeatureStore(IBehavioralFeatureStore):
    def __init__(self) -> None:
        self.docs: list[BehavioralFeatures] = []

    async def upsert_many(self, features):
        for f in features:
            self.docs.append(f)
        return len(features)

    async def list_for_user(self, user_id, start=None, end=None, source_dataset=None):
        out = [d for d in self.docs if d.user_id == user_id]
        if start is not None:
            out = [d for d in out if d.window_start >= start]
        if end is not None:
            out = [d for d in out if d.window_start < end]
        if source_dataset is not None:
            out = [d for d in out if d.source_dataset == source_dataset]
        return out

    async def list_users_with_features(self, source_dataset=None):
        return sorted({d.user_id for d in self.docs})

    async def list_in_window(self, start=None, end=None, source_dataset=None):
        return [
            d for d in self.docs
            if (start is None or d.window_start >= start)
            and (end is None or d.window_start < end)
            and (source_dataset is None or d.source_dataset == source_dataset)
        ]


class FakeBaselineRepo(IBehavioralBaselineRepository):
    def __init__(self) -> None:
        self.baselines: dict[tuple[str, str], BehavioralBaseline] = {}

    async def save(self, baseline: BehavioralBaseline) -> BehavioralBaseline:
        self.baselines[(baseline.user_id, baseline.feature_version)] = baseline
        return baseline

    async def get(self, user_id, feature_version):
        return self.baselines.get((user_id, feature_version))

    async def list_all(self):
        return list(self.baselines.values())


class FakeEventSource(IBehavioralEventSource):
    def __init__(self, events: list[dict] | None = None) -> None:
        self.all_events: list[dict] = events or []

    def add(self, ev: dict) -> None:
        self.all_events.append(ev)

    async def find_events(
        self, *, user_id=None, source_dataset=None, start=None, end=None, limit=100_000
    ):
        out = list(self.all_events)
        if user_id is not None:
            out = [e for e in out if e.get("user_id") == user_id]
        if source_dataset is not None:
            out = [e for e in out if e.get("source_dataset") == source_dataset]
        if start is not None:
            out = [e for e in out if _ts(e) >= start]
        if end is not None:
            out = [e for e in out if _ts(e) < end]
        out.sort(key=_ts)
        return out[:limit]


def _ts(ev: dict) -> datetime:
    value = ev.get("timestamp")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError(value)


def _ev(
    *,
    event_type: str,
    ts: datetime,
    user_id: str = "alice",
    source_dataset: str = "cert",
    device_id: str = "WS-1",
    target_resource: str | None = None,
    risk_indicators: list[str] | None = None,
) -> dict:
    e = {
        "event_type": event_type,
        "timestamp": ts,
        "user_id": user_id,
        "source_dataset": source_dataset,
        "device_id": device_id,
    }
    if target_resource is not None:
        e["target_resource"] = target_resource
    if risk_indicators is not None:
        e["risk_indicators"] = risk_indicators
    return e


@pytest.fixture
def service() -> FeatureEngineeringService:
    return FeatureEngineeringService(
        feature_store=FakeFeatureStore(),
        baseline_repo=FakeBaselineRepo(),
        event_source=FakeEventSource(),
    )


# ─── generate_features: daily ─────────────────────────────


@pytest.mark.asyncio
async def test_generate_features_creates_daily_rows(service: FeatureEngineeringService):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 4, tzinfo=UTC)
    for d in range(3):
        for h in (9, 10, 11):
            service.event_source.add(_ev(
                event_type="logon",
                ts=start + timedelta(days=d, hours=h),
            ))

    rows = await service.generate_features(
        start=start, end=end, source_dataset="cert"
    )
    # Three full daily windows: 00:00 of each day.
    assert len(rows) == 3
    # Each day has 3 logon events
    for row in rows:
        assert row.user_id == "alice"
        assert row.source_dataset == "cert"
        assert row.window == "daily"
        assert row.features["logon_count"] == 3
        assert row.features["after_hours_activity_count"] == 0
        assert row.features["unique_device_count"] == 1


@pytest.mark.asyncio
async def test_generate_features_handles_no_events(service):
    start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 3, 0, 0, tzinfo=UTC)
    rows = await service.generate_features(start=start, end=end, source_dataset="cert")
    # No events -> no rows (the user-discovery step finds no users).
    assert rows == []


@pytest.mark.asyncio
async def test_generate_features_handles_multiple_users(service):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 4, tzinfo=UTC)
    for user, hour in [("alice", 9), ("bob", 14)]:
        for d in range(3):
            service.event_source.add(_ev(
                event_type="logon", ts=start + timedelta(days=d, hours=hour),
                user_id=user,
            ))
    rows = await service.generate_features(start=start, end=end, source_dataset="cert")
    users = {r.user_id for r in rows}
    assert users == {"alice", "bob"}
    # 3 days × 2 users = 6 rows
    assert len(rows) == 6


@pytest.mark.asyncio
async def test_generate_features_filters_by_source_dataset(service):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 3, tzinfo=UTC)
    # CERT events for alice
    for d in range(2):
        service.event_source.add(_ev(
            event_type="logon", ts=start + timedelta(days=d, hours=10),
            source_dataset="cert",
        ))
    # Windows-agent events for alice
    for d in range(2):
        service.event_source.add(_ev(
            event_type="logon", ts=start + timedelta(days=d, hours=11),
            source_dataset="win_endpoint",
        ))

    cert_rows = await service.generate_features(
        start=start, end=end, source_dataset="cert"
    )
    win_rows = await service.generate_features(
        start=start, end=end, source_dataset="win_endpoint"
    )
    all_rows = await service.generate_features(
        start=start, end=end, source_dataset="all"
    )

    assert all(r.source_dataset == "cert" for r in cert_rows)
    assert all(r.source_dataset == "win_endpoint" for r in win_rows)
    assert all(r.source_dataset == "all" for r in all_rows)
    # 'all' sees 2 events per day, 'cert' sees 1 per day
    assert all_rows[0].features["logon_count"] == 2
    assert cert_rows[0].features["logon_count"] == 1
    assert win_rows[0].features["logon_count"] == 1


@pytest.mark.asyncio
async def test_generate_features_rolling_window(service):
    # Three days, one event per day.  Rolling-7d accumulates events over
    # the trailing 7 days ending at each day's midnight.
    day1 = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    for d in range(3):
        service.event_source.add(_ev(
            event_type="logon", ts=day1 + timedelta(days=d, hours=1),
        ))
    end = datetime(2026, 8, 4, 0, 0, tzinfo=UTC)

    rows = await service.generate_features(
        start=day1, end=end, source_dataset="cert", window="rolling_7d"
    )
    # Three daily windows.
    assert len(rows) == 3
    # Counts accumulate: end of day 1 -> 1, day 2 -> 2, day 3 -> 3.
    counts = [r.features["logon_count"] for r in rows]
    assert counts == [1, 2, 3]
    for r in rows:
        assert r.window == "rolling_7d"


# ─── Duplicate event handling ─────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_events_are_counted_each_time(service):
    """Four events with the same shape count as 4 — no feature-level dedup."""
    start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 2, 0, 0, tzinfo=UTC)
    for m in range(4):
        service.event_source.add(_ev(
            event_type="logon", ts=start + timedelta(hours=9, minutes=m)
        ))
    rows = await service.generate_features(start=start, end=end, source_dataset="cert")
    assert len(rows) == 1
    assert rows[0].features["logon_count"] == 4


# ─── Determinism ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_feature_generation_is_deterministic(service: FeatureEngineeringService):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 3, tzinfo=UTC)
    for d in range(2):
        for h in (9, 10, 14, 22):
            service.event_source.add(_ev(
                event_type="logon",
                ts=start + timedelta(days=d, hours=h),
            ))
    rows1 = await service.generate_features(start=start, end=end, source_dataset="cert")
    rows2 = await service.generate_features(start=start, end=end, source_dataset="cert")
    assert [r.features for r in rows1] == [r.features for r in rows2]


# ─── build_baseline ──────────────────────────────────────


@pytest.mark.asyncio
async def test_build_baseline_uses_only_historical_events(service):
    history_start = datetime(2026, 8, 1, tzinfo=UTC)
    eval_start = datetime(2026, 8, 8, tzinfo=UTC)

    # 7 days of normal history
    for d in range(7):
        for _ in range(5):
            service.event_source.add(_ev(
                event_type="logon",
                ts=history_start + timedelta(days=d, hours=10),
            ))
    # 7 days of "anomalous" evaluation period — must NOT affect baseline
    for d in range(7):
        for _ in range(100):
            service.event_source.add(_ev(
                event_type="logon",
                ts=eval_start + timedelta(days=d, hours=10),
            ))

    baseline = await service.build_baseline(
        user_id="alice",
        history_start=history_start,
        history_end=eval_start,
        source_dataset="cert",
    )
    assert baseline.user_id == "alice"
    # mean of historical logon_count is 5 per day, not 100
    assert baseline.stats["logon_count"]["mean"] == pytest.approx(5.0)
    assert baseline.stats["logon_count"]["max"] == 5.0


@pytest.mark.asyncio
async def test_build_baseline_raises_when_no_history(service):
    with pytest.raises(NoDataForBaselineError):
        await service.build_baseline(
            user_id="ghost",
            history_start=datetime(2026, 8, 1, tzinfo=UTC),
            history_end=datetime(2026, 8, 8, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_build_baseline_excludes_evaluation_period(service):
    """Verify a single event on the boundary (history_end) is excluded."""
    history_start = datetime(2026, 8, 1, tzinfo=UTC)
    history_end = datetime(2026, 8, 8, tzinfo=UTC)
    for d in range(7):
        service.event_source.add(_ev(
            event_type="logon", ts=history_start + timedelta(days=d, hours=10),
        ))
    # Edge case: event AT history_end must be excluded
    service.event_source.add(_ev(
        event_type="logon", ts=history_end,
    ))

    baseline = await service.build_baseline(
        user_id="alice",
        history_start=history_start,
        history_end=history_end,
    )
    # Only 7 days of 1 logon each
    assert baseline.stats["logon_count"]["mean"] == pytest.approx(1.0)
    assert baseline.stats["logon_count"]["count"] == 7


# ─── Persistence ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_features_persists_rows(service: FeatureEngineeringService):
    start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 3, 0, 0, tzinfo=UTC)
    # One event per day so we get exactly two daily windows
    service.event_source.add(_ev(event_type="logon", ts=start + timedelta(hours=9)))
    service.event_source.add(_ev(event_type="logon", ts=start + timedelta(days=1, hours=9)))

    await service.generate_features(start=start, end=end, source_dataset="cert")
    # Two daily windows: 00:00→midnight day 1, then midnight→midnight day 2
    assert len(service.feature_store.docs) == 2
    assert all(isinstance(d, BehavioralFeatures) for d in service.feature_store.docs)


@pytest.mark.asyncio
async def test_build_baseline_persists_baseline(service: FeatureEngineeringService):
    history_start = datetime(2026, 8, 1, tzinfo=UTC)
    history_end = datetime(2026, 8, 8, tzinfo=UTC)
    for d in range(7):
        service.event_source.add(_ev(
            event_type="logon", ts=history_start + timedelta(days=d, hours=10),
        ))

    await service.build_baseline(
        user_id="alice",
        history_start=history_start,
        history_end=history_end,
    )
    saved = await service.get_baseline("alice")
    assert saved is not None
    assert saved.user_id == "alice"
    assert saved.feature_version == FEATURE_VERSION
    assert saved.stats["logon_count"]["mean"] == pytest.approx(1.0)

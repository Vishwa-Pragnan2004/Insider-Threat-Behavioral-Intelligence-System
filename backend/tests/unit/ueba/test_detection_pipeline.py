"""
ITBIS — Unit tests: continuous detection pipeline orchestration, coordination
and scheduling, with fake stages (no databases, no model).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone

import fakeredis.aioredis
import pytest

from app.modules.anomaly.domain.exceptions import ModelLoadError
from app.modules.ueba.application.detection_pipeline import (
    NO_ACTIVITY,
    DetectionPipeline,
    DetectionSummary,
    FeatureSummary,
    PipelineBusyError,
    PipelineCoordinator,
    PipelineScheduler,
    trailing_window,
)

NOW = datetime(2026, 9, 14, 9, 30, tzinfo=UTC)


class FakeStages:
    def __init__(
        self,
        users=("alice",),
        summary: DetectionSummary | None = None,
        feature_error: Exception | None = None,
        detect_error: Exception | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.users = list(users)
        self.summary = summary or DetectionSummary(
            results=2, anomalies=1, high_risk=1, alerts_created=1
        )
        self.feature_error = feature_error
        self.detect_error = detect_error
        self.gate = gate
        self.calls: list[tuple] = []

    async def generate_features(self, start, end):
        self.calls.append(("features", start, end))
        if self.gate is not None:
            await self.gate.wait()
        if self.feature_error:
            raise self.feature_error
        return FeatureSummary(rows=len(self.users) * 2, user_ids=list(self.users))

    async def detect(self, start, end, user_ids):
        self.calls.append(("detect", start, end, tuple(user_ids)))
        if self.detect_error:
            raise self.detect_error
        return self.summary


def _factory(stages: FakeStages):
    @asynccontextmanager
    async def factory():
        yield stages

    return factory


def _pipeline(stages: FakeStages, lookback_days: int = 2) -> DetectionPipeline:
    return DetectionPipeline(_factory(stages), lookback_days=lookback_days, clock=lambda: NOW)


# ─── Window ─────────────────────────────────────────────────


def test_window_covers_whole_days_up_to_the_end_of_today():
    assert trailing_window(NOW, 2) == (
        datetime(2026, 9, 13, tzinfo=UTC),
        datetime(2026, 9, 15, tzinfo=UTC),
    )


def test_single_day_window_is_today():
    assert trailing_window(NOW, 1) == (
        datetime(2026, 9, 14, tzinfo=UTC),
        datetime(2026, 9, 15, tzinfo=UTC),
    )


def test_naive_time_is_treated_as_utc_and_other_zones_are_converted():
    ist = timezone(timedelta(hours=5, minutes=30))
    # 02:00 IST on the 15th is still the 14th in UTC.
    assert trailing_window(datetime(2026, 9, 15, 2, 0, tzinfo=ist), 1)[0] == datetime(
        2026, 9, 14, tzinfo=UTC
    )
    assert trailing_window(datetime(2026, 9, 14, 9, 30), 1)[0] == datetime(
        2026, 9, 14, tzinfo=UTC
    )


def test_window_needs_at_least_one_day():
    with pytest.raises(ValueError):
        trailing_window(NOW, 0)


# ─── One run ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_builds_features_then_detects_those_users_over_the_same_window():
    stages = FakeStages(users=("alice", "bob"))

    result = await _pipeline(stages).run_once(trigger="manual")

    start, end = trailing_window(NOW, 2)
    assert stages.calls == [
        ("features", start, end),
        ("detect", start, end, ("alice", "bob")),
    ]
    assert result.succeeded
    assert result.trigger == "manual"
    assert (result.window_start, result.window_end) == (start, end)
    assert result.feature_rows == 4
    assert result.users_with_features == 2
    assert result.anomaly_results == 2
    assert result.anomalies_flagged == 1
    assert result.high_risk_results == 1
    assert result.alerts_created == 1
    assert result.finished_at is not None


@pytest.mark.asyncio
async def test_detection_is_skipped_when_there_is_no_activity():
    stages = FakeStages(users=())

    result = await _pipeline(stages).run_once()

    assert [c[0] for c in stages.calls] == ["features"]
    assert result.succeeded
    assert result.detection_skipped_reason == NO_ACTIVITY


@pytest.mark.asyncio
async def test_missing_model_skips_detection_without_failing_the_run():
    stages = FakeStages(detect_error=ModelLoadError("artifact not found"))

    result = await _pipeline(stages).run_once()

    assert result.succeeded
    assert result.feature_rows == 2, "features are still built and kept"
    assert "model unavailable" in result.detection_skipped_reason


@pytest.mark.asyncio
async def test_unexpected_failure_is_captured_not_raised():
    stages = FakeStages(feature_error=ConnectionError("mongo unreachable"))

    result = await _pipeline(stages).run_once()

    assert not result.succeeded
    assert result.error == "ConnectionError: mongo unreachable"
    assert result.finished_at is not None


# ─── Coordinator ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_coordinator_records_successes_and_failures():
    coordinator = PipelineCoordinator()

    await coordinator.run(_pipeline(FakeStages()), trigger="manual")
    await coordinator.run(
        _pipeline(FakeStages(feature_error=RuntimeError("boom"))), trigger="schedule"
    )

    status = coordinator.status
    assert status.runs_completed == 1
    assert status.runs_failed == 1
    assert status.last_success_at is not None
    assert status.last_run.error == "RuntimeError: boom"
    assert status.running is False


@pytest.mark.asyncio
async def test_overlapping_run_in_the_same_process_is_refused():
    coordinator = PipelineCoordinator()
    gate = asyncio.Event()
    first = asyncio.create_task(
        coordinator.run(_pipeline(FakeStages(gate=gate)), trigger="schedule")
    )
    await asyncio.sleep(0)
    assert coordinator.status.running

    with pytest.raises(PipelineBusyError):
        await coordinator.run(_pipeline(FakeStages()), trigger="manual")

    gate.set()
    assert (await first).succeeded


@pytest.mark.asyncio
async def test_run_is_skipped_while_another_process_holds_the_lock():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.set(PipelineCoordinator.LOCK_KEY, "another-worker")
    stages = FakeStages()

    result = await PipelineCoordinator().run(_pipeline(stages), trigger="schedule", redis=redis)

    assert result is None
    assert stages.calls == [], "the pipeline must not run"
    await redis.aclose()


@pytest.mark.asyncio
async def test_lock_is_released_after_a_run():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    await PipelineCoordinator().run(_pipeline(FakeStages()), trigger="manual", redis=redis)

    assert await redis.get(PipelineCoordinator.LOCK_KEY) is None
    await redis.aclose()


@pytest.mark.asyncio
async def test_unreachable_redis_does_not_prevent_detection():
    class BrokenRedis:
        async def set(self, *args, **kwargs):
            raise ConnectionError("redis down")

    result = await PipelineCoordinator().run(
        _pipeline(FakeStages()), trigger="schedule", redis=BrokenRedis()
    )

    assert result is not None and result.succeeded


# ─── Scheduler ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scheduler_runs_repeatedly_until_stopped():
    coordinator = PipelineCoordinator()
    scheduler = PipelineScheduler(
        coordinator, _pipeline(FakeStages()), interval_seconds=0.01, initial_delay_seconds=0
    )

    scheduler.start()
    assert coordinator.status.scheduler_enabled
    await asyncio.sleep(0.15)
    await scheduler.stop()

    assert coordinator.status.runs_completed >= 2
    assert not scheduler.running
    assert coordinator.status.scheduler_enabled is False
    assert coordinator.status.next_run_at is None


@pytest.mark.asyncio
async def test_scheduler_keeps_going_after_failed_runs():
    coordinator = PipelineCoordinator()
    failing = FakeStages(feature_error=ConnectionError("postgres down"))
    scheduler = PipelineScheduler(
        coordinator, _pipeline(failing), interval_seconds=0.01, initial_delay_seconds=0
    )

    scheduler.start()
    await asyncio.sleep(0.15)
    still_running = scheduler.running
    await scheduler.stop()

    assert still_running
    assert coordinator.status.runs_failed >= 2


def test_scheduler_rejects_a_non_positive_interval():
    with pytest.raises(ValueError):
        PipelineScheduler(PipelineCoordinator(), _pipeline(FakeStages()), interval_seconds=0)

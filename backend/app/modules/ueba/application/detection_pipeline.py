"""
ITBIS — UEBA: continuous detection pipeline

Turns raw activity into alerts without anyone pressing a button:

    canonical events -> behavioural features -> personal baselines
                     -> ML anomaly detection + category detectors
                     -> weighted insider risk scores -> alerts

Each run recomputes a trailing window of whole UTC days — today plus
`lookback_days - 1` earlier days, so late-arriving events are still picked up.
Every stage is idempotent: feature rows and anomaly results are upserted per
(user, window, day) and alerts are de-duplicated on an idempotency key, so
running the same window again only refreshes it. A user's personal baseline
is rebuilt (at most once a day) from the days *before* the window, so the
behaviour being judged never shapes its own yardstick. Alerts are created during
detection, through the anomaly service's alert observer.

Components
----------
DetectionPipeline    one run: features, then detection, summarised
PipelineCoordinator  one run at a time (per process, and across processes via
                     a Redis lock), plus the status every caller sees
PipelineScheduler    the background task that runs the pipeline on an interval
"""
from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog

from app.modules.activity.infrastructure.mongo_event_store import MongoActivityEventStore
from app.modules.alerts.application.risk_alert_service import RiskAlertService
from app.modules.alerts.infrastructure.mongo_alert_repository import MongoAlertRepository
from app.modules.anomaly.application.anomaly_detection_service import AnomalyDetectionService
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel
from app.modules.anomaly.domain.exceptions import (
    FeatureIncompatibilityError,
    ModelLoadError,
    ModelNotLoadedError,
    NoDataForDetectionError,
)
from app.modules.anomaly.infrastructure.mongo_result_store import MongoAnomalyResultStore
from app.modules.behavioral.application.services.feature_engineering_service import (
    FeatureEngineeringService,
)
from app.modules.behavioral.domain.enums import FEATURE_VERSION
from app.modules.behavioral.domain.exceptions import NoDataForBaselineError
from app.modules.behavioral.infrastructure.repositories import (
    MongoBehavioralFeatureStore,
    SQLBehavioralBaselineRepository,
)
from app.modules.detection.application.detection_service import DetectionService
from app.modules.detection.infrastructure.mongo_finding_store import MongoFindingStore
from app.modules.employees.application.directory_service import detection_context
from app.modules.employees.infrastructure.repository import SQLEmployeeRepository
from app.modules.risk.application.risk_service import RiskService
from app.modules.risk.infrastructure.mongo_risk_store import MongoRiskScoreStore
from app.modules.risk.infrastructure.mongo_signal_source import MongoRiskSignalSource

log = structlog.get_logger(__name__)

HIGH_RISK_LEVELS = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})
#: Detection can't run without a usable model; that skips the stage, it isn't a failure.
MODEL_UNAVAILABLE_ERRORS = (ModelLoadError, ModelNotLoadedError, FeatureIncompatibilityError)
NO_ACTIVITY = "no activity in window"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _baseline_settings() -> dict[str, int]:
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "baseline_history_days": settings.PIPELINE_BASELINE_HISTORY_DAYS,
        "baseline_min_days": settings.PIPELINE_BASELINE_MIN_DAYS,
    }


def trailing_window(now: datetime, lookback_days: int) -> tuple[datetime, datetime]:
    """
    [start of the earliest day, start of tomorrow) in UTC, spanning `lookback_days` days.

    Whole days, because behavioural features are daily: recomputing only part
    of a day would overwrite that day's feature row with partial counts.
    """
    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1")
    now = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=lookback_days - 1), today + timedelta(days=1)


# ─── Stage contract ─────────────────────────────────────────


@dataclass
class FeatureSummary:
    rows: int
    user_ids: list[str]


@dataclass
class DetectionSummary:
    results: int = 0
    anomalies: int = 0
    high_risk: int = 0
    alerts_created: int = 0
    baselines_built: int = 0
    findings: int = 0
    risk_scores: int = 0
    high_priority_employees: int = 0


class PipelineStages(Protocol):
    async def generate_features(self, start: datetime, end: datetime) -> FeatureSummary:
        """Build behavioural features for the window; report which users had activity."""

    async def detect(
        self, start: datetime, end: datetime, user_ids: list[str]
    ) -> DetectionSummary:
        """Score those users' windows (creating alerts as a side effect) and summarise."""


StagesFactory = Callable[[], AbstractAsyncContextManager[PipelineStages]]


@dataclass
class PipelineRunResult:
    run_id: str
    trigger: str  # "schedule" | "manual"
    started_at: datetime
    window_start: datetime
    window_end: datetime
    finished_at: datetime | None = None
    feature_rows: int = 0
    users_with_features: int = 0
    anomaly_results: int = 0
    anomalies_flagged: int = 0
    high_risk_results: int = 0
    alerts_created: int = 0
    baselines_built: int = 0
    findings: int = 0
    risk_scores: int = 0
    high_priority_employees: int = 0
    detection_skipped_reason: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 3)


# ─── One run ────────────────────────────────────────────────


class DetectionPipeline:
    """Runs features then detection over the trailing window, and never raises."""

    def __init__(
        self,
        stages_factory: StagesFactory,
        *,
        lookback_days: int = 2,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if lookback_days < 1:
            raise ValueError("lookback_days must be at least 1")
        self._stages_factory = stages_factory
        self.lookback_days = lookback_days
        self._clock = clock

    async def run_once(self, *, trigger: str = "schedule") -> PipelineRunResult:
        started = self._clock()
        start, end = trailing_window(started, self.lookback_days)
        result = PipelineRunResult(
            run_id=uuid.uuid4().hex,
            trigger=trigger,
            started_at=started,
            window_start=start,
            window_end=end,
        )
        try:
            async with self._stages_factory() as stages:
                features = await stages.generate_features(start, end)
                result.feature_rows = features.rows
                result.users_with_features = len(features.user_ids)

                if not features.user_ids:
                    result.detection_skipped_reason = NO_ACTIVITY
                else:
                    try:
                        summary = await stages.detect(start, end, features.user_ids)
                    except MODEL_UNAVAILABLE_ERRORS as exc:
                        result.detection_skipped_reason = f"model unavailable: {exc}"
                        log.warning("pipeline.detection_skipped", reason=str(exc))
                    else:
                        result.anomaly_results = summary.results
                        result.anomalies_flagged = summary.anomalies
                        result.high_risk_results = summary.high_risk
                        result.alerts_created = summary.alerts_created
                        result.baselines_built = summary.baselines_built
                        result.findings = summary.findings
                        result.risk_scores = summary.risk_scores
                        result.high_priority_employees = summary.high_priority_employees
        except Exception as exc:  # noqa: BLE001 - a failed run must not kill the scheduler
            result.error = f"{type(exc).__name__}: {exc}"
            log.exception("pipeline.run_failed", run_id=result.run_id, trigger=trigger)
        finally:
            result.finished_at = self._clock()

        log.info(
            "pipeline.run_finished",
            run_id=result.run_id,
            trigger=trigger,
            succeeded=result.succeeded,
            duration_seconds=result.duration_seconds,
            window_start=start.isoformat(),
            window_end=end.isoformat(),
            feature_rows=result.feature_rows,
            users=result.users_with_features,
            anomaly_results=result.anomaly_results,
            high_risk=result.high_risk_results,
            alerts_created=result.alerts_created,
            skipped=result.detection_skipped_reason,
        )
        return result


# ─── Live stages (MongoDB + PostgreSQL + model) ─────────────


class _CountingAlertRepository:
    """Wraps the alert repository to count alerts actually created, not de-duplicated."""

    def __init__(self, inner: MongoAlertRepository) -> None:
        self._inner = inner
        self.created = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def upsert(self, alert):  # type: ignore[no-untyped-def]
        saved, created = await self._inner.upsert(alert)
        if created:
            self.created += 1
        return saved, created


class LivePipelineStages:
    """The real stages, built from one SQL session and one MongoDB handle."""

    def __init__(
        self,
        session: Any,
        mongo_db: Any,
        model_service: Any,
        *,
        baseline_history_days: int = 28,
        baseline_min_days: int = 5,
        detection_history_days: int = 60,
    ) -> None:
        self._session = session
        self._db = mongo_db
        self._model_service = model_service
        self._baseline_history_days = baseline_history_days
        self._baseline_min_days = baseline_min_days
        self._detection_history_days = detection_history_days

    def _features(self) -> FeatureEngineeringService:
        return FeatureEngineeringService(
            feature_store=MongoBehavioralFeatureStore(self._db),
            baseline_repo=SQLBehavioralBaselineRepository(self._session),
            event_source=MongoActivityEventStore(self._db),
        )

    async def refresh_baseline(
        self, service: FeatureEngineeringService, user_id: str, before: datetime
    ) -> bool:
        """Rebuild the user's baseline from the history before `before`, if stale."""
        existing = await service.get_baseline(user_id, FEATURE_VERSION)
        if existing is not None and _as_utc(existing.window_end) >= before:
            return False
        try:
            await service.build_baseline(
                user_id=user_id,
                history_start=before - timedelta(days=self._baseline_history_days),
                history_end=before,
                min_observation_days=self._baseline_min_days,
            )
        except NoDataForBaselineError:
            return False  # still learning; an older baseline, if any, stays in use
        return True

    async def generate_features(self, start: datetime, end: datetime) -> FeatureSummary:
        service = self._features()
        rows = await service.generate_features(
            start=start, end=end, source_dataset="all", window="daily"
        )
        return FeatureSummary(rows=len(rows), user_ids=sorted({r.user_id for r in rows}))

    async def detect(
        self, start: datetime, end: datetime, user_ids: list[str]
    ) -> DetectionSummary:
        alert_repo = _CountingAlertRepository(MongoAlertRepository(self._db))
        # The ML model's results are one input to the insider risk score; alerts
        # come from the risk engine, which also weighs the category detectors.
        detection = AnomalyDetectionService(
            model_service=self._model_service,
            feature_store=MongoBehavioralFeatureStore(self._db),
            baseline_repo=SQLBehavioralBaselineRepository(self._session),
            result_store=MongoAnomalyResultStore(self._db),
        )

        features = self._features()
        baselines_built = 0
        results = []
        for user_id in user_ids:
            if await self.refresh_baseline(features, user_id, start):
                baselines_built += 1
            try:
                results.extend(
                    await detection.detect_for_user(
                        user_id=user_id,
                        start=start,
                        end=end,
                        source_dataset="all",
                        window="daily",
                    )
                )
            except NoDataForDetectionError:
                continue

        org = await detection_context(SQLEmployeeRepository(self._session))
        findings = await DetectionService(
            MongoActivityEventStore(self._db),
            MongoFindingStore(self._db),
            history_days=self._detection_history_days,
            context_provider=lambda: org,
        ).detect_window(start, end, user_ids)
        scores = await RiskService(
            MongoRiskSignalSource(self._db), MongoRiskScoreStore(self._db)
        ).score_window(start, end, user_ids)
        risk_alerts = RiskAlertService(alert_repo)
        for score in scores:
            try:
                await risk_alerts.raise_for(score, findings)
            except Exception:  # noqa: BLE001 - one bad alert must not stop the run
                log.exception("pipeline.risk_alert_failed", user_id=score.user_id)

        return DetectionSummary(
            results=len(results),
            anomalies=sum(1 for r in results if r.prediction == AnomalyPrediction.ANOMALY),
            high_risk=sum(1 for r in results if RiskLevel(r.risk_level) in HIGH_RISK_LEVELS),
            alerts_created=alert_repo.created,
            baselines_built=baselines_built,
            findings=len(findings),
            risk_scores=len(scores),
            high_priority_employees=len({s.user_id for s in scores if s.priority >= 60}),
        )


def stages_factory_for(session: Any, mongo_db: Any, model_service: Any) -> StagesFactory:
    """Stages over resources someone else owns (e.g. a request's session)."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[PipelineStages]:
        yield LivePipelineStages(session, mongo_db, model_service, **_baseline_settings())

    return factory


@asynccontextmanager
async def live_stages() -> AsyncIterator[PipelineStages]:
    """Stages with their own SQL session, for the background scheduler."""
    from app.core.database import AsyncSessionLocal
    from app.core.mongo_client import get_mongo_db
    from app.modules.anomaly.presentation.dependencies import get_model_service

    async with AsyncSessionLocal() as session:
        try:
            yield LivePipelineStages(
                session, await get_mongo_db(), get_model_service(), **_baseline_settings()
            )
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


# ─── Coordination and status ────────────────────────────────


class PipelineBusyError(RuntimeError):
    """A pipeline run is already in progress in this process."""


@dataclass
class PipelineStatus:
    scheduler_enabled: bool = False
    interval_seconds: int | None = None
    lookback_days: int | None = None
    running: bool = False
    runs_completed: int = 0
    runs_failed: int = 0
    last_run: PipelineRunResult | None = None
    last_success_at: datetime | None = None
    next_run_at: datetime | None = None


class PipelineCoordinator:
    """
    One pipeline run at a time, and the status every caller sees.

    Within a process an asyncio lock prevents overlap. Across processes (several
    API workers each running a scheduler) a Redis lock does; if Redis can't be
    reached the run proceeds without it and that is logged once.
    """

    LOCK_KEY = "itbis:detection-pipeline:lock"

    def __init__(self, lock_ttl_seconds: int = 900) -> None:
        self.status = PipelineStatus()
        self._lock = asyncio.Lock()
        self._lock_ttl = lock_ttl_seconds
        self._redis_warning_logged = False

    async def run(
        self, pipeline: DetectionPipeline, *, trigger: str, redis: Any | None = None
    ) -> PipelineRunResult | None:
        """Run the pipeline; None if another process holds the run lock."""
        if self._lock.locked():
            raise PipelineBusyError("a detection pipeline run is already in progress")
        async with self._lock:
            token = uuid.uuid4().hex
            acquired, held_redis = await self._acquire(redis, token)
            if not acquired:
                log.info("pipeline.skipped_running_elsewhere", trigger=trigger)
                return None
            self.status.running = True
            try:
                result = await pipeline.run_once(trigger=trigger)
            finally:
                self.status.running = False
                if held_redis is not None:
                    await self._release(held_redis, token)
            self._record(result)
            return result

    async def _acquire(self, redis: Any | None, token: str) -> tuple[bool, Any | None]:
        if redis is None:
            return True, None
        try:
            acquired = await redis.set(self.LOCK_KEY, token, nx=True, ex=self._lock_ttl)
        except Exception as exc:  # noqa: BLE001
            if not self._redis_warning_logged:
                self._redis_warning_logged = True
                log.warning(
                    "pipeline.lock_unavailable",
                    error=str(exc),
                    hint="Running without a cross-process lock; use a single API worker.",
                )
            return True, None
        return (True, redis) if acquired else (False, None)

    async def _release(self, redis: Any, token: str) -> None:
        try:
            if await redis.get(self.LOCK_KEY) == token:
                await redis.delete(self.LOCK_KEY)
        except Exception as exc:  # noqa: BLE001 - the TTL frees it eventually
            log.warning("pipeline.lock_release_failed", error=str(exc))

    def _record(self, result: PipelineRunResult) -> None:
        self.status.last_run = result
        if result.succeeded:
            self.status.runs_completed += 1
            self.status.last_success_at = result.finished_at
        else:
            self.status.runs_failed += 1


class PipelineScheduler:
    """Background task running the pipeline every `interval_seconds`."""

    def __init__(
        self,
        coordinator: PipelineCoordinator,
        pipeline: DetectionPipeline,
        *,
        interval_seconds: float,
        initial_delay_seconds: float = 30.0,
        redis_provider: Callable[[], Awaitable[Any]] | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._coordinator = coordinator
        self._pipeline = pipeline
        self._interval = interval_seconds
        self._initial_delay = max(0.0, initial_delay_seconds)
        self._redis_provider = redis_provider
        self._clock = clock
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is not None:
            return
        status = self._coordinator.status
        status.scheduler_enabled = True
        status.interval_seconds = int(self._interval)
        status.lookback_days = self._pipeline.lookback_days
        status.next_run_at = self._clock() + timedelta(seconds=self._initial_delay)
        self._task = asyncio.create_task(self._loop(), name="itbis-detection-pipeline")
        log.info(
            "pipeline.scheduler_started",
            interval_seconds=self._interval,
            lookback_days=self._pipeline.lookback_days,
            first_run_in_seconds=self._initial_delay,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._coordinator.status.scheduler_enabled = False
        self._coordinator.status.next_run_at = None
        log.info("pipeline.scheduler_stopped")

    async def _loop(self) -> None:
        await asyncio.sleep(self._initial_delay)
        while True:
            try:
                redis = await self._redis_provider() if self._redis_provider else None
            except Exception:  # noqa: BLE001 - the coordinator copes without a lock
                redis = None
            try:
                await self._coordinator.run(self._pipeline, trigger="schedule", redis=redis)
            except PipelineBusyError:
                log.info("pipeline.scheduled_run_skipped", reason="a manual run is in progress")
            except Exception:  # noqa: BLE001 - run_once never raises; this guards the loop
                log.exception("pipeline.scheduler_iteration_failed")
            self._coordinator.status.next_run_at = self._clock() + timedelta(
                seconds=self._interval
            )
            await asyncio.sleep(self._interval)


#: Shared by the background scheduler and the manual-run API.
pipeline_coordinator = PipelineCoordinator()


def build_scheduler(settings: Any) -> PipelineScheduler:
    """The production scheduler, configured from application settings."""
    from app.core.redis_client import get_redis

    pipeline = DetectionPipeline(live_stages, lookback_days=settings.PIPELINE_LOOKBACK_DAYS)
    return PipelineScheduler(
        pipeline_coordinator,
        pipeline,
        interval_seconds=settings.PIPELINE_INTERVAL_SECONDS,
        initial_delay_seconds=settings.PIPELINE_INITIAL_DELAY_SECONDS,
        redis_provider=get_redis,
    )

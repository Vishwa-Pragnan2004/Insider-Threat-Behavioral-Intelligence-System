"""
ITBIS — Alerts Module: Alert Generation Service

Converts `AnomalyResult` documents into `Alert` documents, with
two responsibilities:

1. **Policy** — decide whether the anomaly deserves an alert.  The
   default policy is HIGH/CRITICAL-only (see `policy.py`).
2. **Deduplication** — collapse repeated detections of the same
   `(user_id, window, window_start, model_version)` into a single
   alert.  The idempotency key is enforced by a MongoDB unique
   index on the `idempotency_key` field (see `MongoAlertRepository`),
   so the dedup is durable across restarts and safe to call
    concurrently.

The service is invoked by the Phase-5 `AnomalyDetectionService` via
an observer callback (see `AlertObserver`) and also exposes a
`generate_for_anomaly` method used by the manual
`POST /api/v1/alerts/generate` backfill endpoint.
"""
from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import datetime, UTC

import structlog

from app.modules.alerts.application.dtos import AlertGenerateResponse


def _make_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (assumes UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
from app.modules.alerts.application.policy import DEFAULT_POLICY, AlertPolicy
from app.modules.alerts.domain.entities import Alert, AlertDeviation
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.alerts.domain.repositories import IAlertRepository
from app.modules.anomaly.domain.entities import AnomalyResult
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel
from app.modules.anomaly.domain.repositories import IAnomalyResultStore

log = structlog.get_logger(__name__)


# ─── Idempotency key ──────────────────────────────────────


def compute_idempotency_key(
    *,
    user_id: str,
    window: str,
    window_start: datetime,
    model_version: str,
) -> str:
    """
    Deterministic, content-based dedup key.

    Format:
        <user_id>|<window>|<window_start_iso>|<model_version-sha256-12>

    The hash suffix prevents absurdly long user_ids from breaking
    log/metric pipelines while preserving full determinism.
    """
    h = hashlib.sha256(model_version.encode("utf-8")).hexdigest()[:12]
    return f"{user_id}|{window}|{window_start.isoformat()}|{h}"


# ─── Title / description builders ──────────────────────────


def _build_title(user_id: str, severity: AlertSeverity) -> str:
    return f"{severity.value.title()} behavioral anomaly detected for {user_id}"


def _build_description(
    risk_score: float,
    prediction: AnomalyPrediction,
    deviations: list[AlertDeviation],
) -> str:
    parts: list[str] = [
        f"User activity significantly deviated from the established "
        f"behavioral baseline. "
        f"Risk score: {risk_score:.1f}/100. "
        f"Prediction: {prediction.value}."
    ]
    if deviations:
        top = ", ".join(
            f"{d.feature} ({d.zscore:+.1f}σ)" for d in deviations[:3]
        )
        parts.append(f" Top deviations: {top}.")
    return "".join(parts)


# ─── Service ─────────────────────────────────────────────


class AlertGenerationService:
    """Converts anomaly results to alerts under a configurable policy."""

    def __init__(
        self,
        alert_repo: IAlertRepository,
        anomaly_repo: IAnomalyResultStore,
        policy: AlertPolicy | None = None,
    ) -> None:
        self.alert_repo = alert_repo
        self.anomaly_repo = anomaly_repo
        self.policy = policy or DEFAULT_POLICY

    # ─── Public API ─────────────────────────────────────

    async def generate_for_anomaly(self, anomaly: AnomalyResult) -> Alert | None:
        """
        Generate an alert for a single anomaly result.

        Returns:
            The newly created Alert, or the existing Alert if an alert
            with the same idempotency_key already exists (dedup hit).
            Returns None if the anomaly is below the policy threshold
            (no alert should be created).
        """
        risk_level = RiskLevel(anomaly.risk_level)

        if not self.policy.should_alert(
            risk_level=risk_level,
            risk_score=float(anomaly.risk_score),
            prediction=anomaly.prediction,
        ):
            log.info(
                "alerts.skipped_below_threshold",
                anomaly_id=str(anomaly.id),
                user_id=anomaly.user_id,
                risk_level=anomaly.risk_level,
                risk_score=anomaly.risk_score,
            )
            return None

        alert = self._build_alert(anomaly)
        saved, created = await self.alert_repo.upsert(alert)
        if created:
            log.info(
                "alerts.created",
                alert_id=str(saved.id),
                user_id=saved.user_id,
                severity=saved.severity.value,
                idempotency_key=saved.idempotency_key,
            )
        else:
            log.info(
                "alerts.duplicate_suppressed",
                alert_id=str(saved.id),
                user_id=saved.user_id,
                idempotency_key=saved.idempotency_key,
            )
        return saved

    async def generate_for_existing_anomalies(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        user_id: str | None = None,
        risk_level: str | None = None,
        source_dataset: str | None = None,
        limit: int = 1000,
    ) -> AlertGenerateResponse:
        """
        Scan the existing anomaly_results collection and generate
        alerts per the policy.  Used by the manual backfill
        endpoint.
        """
        anomalies = await self.anomaly_repo.list_recent(
            risk_level=RiskLevel(risk_level) if risk_level else None,
            limit=limit,
        )

        created = 0
        skipped_dupes = 0
        skipped_below = 0
        start_aware = _make_aware(start) if start is not None else None
        end_aware = _make_aware(end) if end is not None else None
        for an in anomalies:
            # Apply ad-hoc filters that list_recent doesn't support
            if user_id is not None and an.user_id != user_id:
                continue
            if source_dataset is not None and an.source_dataset != source_dataset:
                continue
            window_start_aware = _make_aware(an.window_start)
            if start_aware is not None and window_start_aware < start_aware:
                continue
            if end_aware is not None and window_start_aware >= end_aware:
                continue
            risk_level = RiskLevel(an.risk_level)
            if not self.policy.should_alert(
                risk_level=risk_level,
                risk_score=float(an.risk_score),
                prediction=an.prediction,
            ):
                skipped_below += 1
                continue
            alert = self._build_alert(an)
            _, was_created = await self.alert_repo.upsert(alert)
            if was_created:
                created += 1
            else:
                skipped_dupes += 1

        total = created + skipped_dupes + skipped_below
        log.info(
            "alerts.backfill_completed",
            created=created,
            skipped_dupes=skipped_dupes,
            skipped_below=skipped_below,
            total=total,
        )
        return AlertGenerateResponse(
            created=created,
            skipped_duplicates=skipped_dupes,
            skipped_below_threshold=skipped_below,
            total_processed=total,
        )

    # ─── Internals ──────────────────────────────────────

    def _build_alert(self, an: AnomalyResult) -> Alert:
        risk_level = RiskLevel(an.risk_level)
        severity = self.policy.severity_for(risk_level)
        deviations = [
            AlertDeviation(
                feature=d.feature,
                value=d.value,
                baseline_mean=d.baseline_mean,
                baseline_std=d.baseline_std,
                zscore=d.zscore,
            )
            for d in an.top_behavioral_deviations
        ]
        idem = compute_idempotency_key(
            user_id=an.user_id,
            window=an.window,
            window_start=an.window_start,
            model_version=an.model_version,
        )
        return Alert(
            idempotency_key=idem,
            anomaly_result_id=an.id,
            user_id=an.user_id,
            source_dataset=an.source_dataset,
            window=an.window,
            window_start=an.window_start,
            window_end=an.window_end,
            model_version=an.model_version,
            feature_version=an.feature_version,
            title=_build_title(an.user_id, severity),
            description=_build_description(
                float(an.risk_score), an.prediction, deviations
            ),
            risk_score=float(an.risk_score),
            risk_level=an.risk_level,
            severity=severity,
            status=AlertStatus.OPEN,
            top_behavioral_deviations=deviations,
        )


# ─── Observer type for Phase-5 integration ────────────────


# An observer is a callable that takes a persisted AnomalyResult and
# is fired by the anomaly service after persistence.  The alerts
# module provides an implementation that wraps AlertGenerationService
# (in `application/alert_service.py`).  Keeping this protocol local
# to the alerts module avoids a circular import with anomaly.
AnomalyResultObserver = Callable[[AnomalyResult], Awaitable[None]]

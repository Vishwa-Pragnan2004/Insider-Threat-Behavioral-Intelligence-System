"""
ITBIS — Anomaly Module: AnomalyDetectionService

Top-level orchestrator that ties together:

  1. Loading the model artifact (`ModelService`)
  2. Building the 32-feature input (`feature_prep.build_32_features`)
  3. Running the Isolation Forest (`ModelService.score`)
  4. Converting the raw score to a 0-100 risk + RiskLevel
  5. Producing the top-3 deviation explanation
  6. Persisting the `AnomalyResult`
"""
from __future__ import annotations

from datetime import datetime

import structlog

from app.modules.anomaly.application.explainability import top_deviations
from app.modules.anomaly.application.feature_prep import build_32_features
from app.modules.anomaly.application.model_service import ModelService
from app.modules.anomaly.application.risk_scoring import (
    classify_risk_level,
    normalize_to_risk_score,
)
from app.modules.anomaly.domain.entities import AnomalyResult, BehavioralDeviation
from app.modules.anomaly.domain.enums import AnomalyPrediction
from app.modules.anomaly.domain.exceptions import (
    NoDataForDetectionError,
)
from app.modules.anomaly.domain.repositories import IAnomalyResultStore
from app.modules.behavioral.domain.enums import FEATURE_VERSION
from app.modules.behavioral.domain.repositories import (
    IBehavioralBaselineRepository,
    IBehavioralFeatureStore,
)

log = structlog.get_logger(__name__)


# An observer is a callable that takes a persisted AnomalyResult and
# is fired by the service after a successful persistence.  The alerts
# module (Phase 6) provides an implementation that wires in
# AlertGenerationService.  The type is intentionally a Protocol-free
# Callable so the anomaly module does not import from the alerts
# module (one-way dependency: alerts → anomaly, not the reverse).
from typing import Awaitable, Callable, Optional

AnomalyResultObserver = Callable[["AnomalyResult"], Awaitable[None]]


class AnomalyDetectionService:
    """Orchestrate end-to-end anomaly detection on Phase 4 features."""

    def __init__(
        self,
        model_service: ModelService,
        feature_store: IBehavioralFeatureStore,
        baseline_repo: IBehavioralBaselineRepository,
        result_store: IAnomalyResultStore,
        *,
        alert_observer: Optional[AnomalyResultObserver] = None,
    ) -> None:
        self.model_service = model_service
        self.feature_store = feature_store
        self.baseline_repo = baseline_repo
        self.result_store = result_store
        # Phase 6 integration: invoked with each successfully persisted
        # AnomalyResult so downstream consumers (e.g. alert generation)
        # can react.  Failures in the observer must NOT fail the
        # detection request (the observer is expected to swallow its
        # own errors — see alerts.presentation.dependencies).
        self.alert_observer = alert_observer

    # ─── Public API ─────────────────────────────────────────

    async def detect_for_user_window(
        self,
        *,
        user_id: str,
        window_start: datetime,
        window_end: datetime,
        source_dataset: str = "all",
        window: str = "daily",
        persist: bool = True,
    ) -> AnomalyResult:
        """Run anomaly detection for one (user, window_start) row."""
        if self.model_service.get_artifact.__self__._artifact is None and False:
            # (the above is dead code — we just want to lazy-load via access)
            pass
        art = self.model_service.get_artifact()
        self.model_service.validate_against_phase4()

        # 1. Pull the Phase 4 feature row for this exact (user, window, source)
        rows = await self.feature_store.list_for_user(
            user_id=user_id,
            start=window_start,
            end=window_end,
            source_dataset=None if source_dataset == "all" else source_dataset,
        )
        if not rows:
            raise NoDataForDetectionError(
                f"No Phase 4 features for user={user_id!r} "
                f"in [{window_start.isoformat()}, {window_end.isoformat()}) "
                f"source={source_dataset!r}."
            )
        # If multiple rows fall in the same exact window (e.g. two daily
        # windows for the same user at midnight), the feature store
        # returns them in ascending order; we use the one whose
        # window_start matches exactly.
        match = next(
            (r for r in rows if r.window_start == window_start and r.window == window),
            None,
        )
        if match is None:
            # Fall back to the first row in the [start, end) range.
            match = rows[0]
        feature_row = match

        # 2. Pull the per-user baseline (Phase 4 stores `behavioral_features_v1`).
        baseline = await self.baseline_repo.get(user_id, FEATURE_VERSION)

        # 3. Build the 32-feature vector.
        prepared = build_32_features(feature_row, baseline, art)

        # 4. Run the Isolation Forest.
        pred_int, raw_score = self.model_service.score([prepared.vector])
        prediction = (
            AnomalyPrediction.ANOMALY if pred_int == -1 else AnomalyPrediction.NORMAL
        )

        # 5. Risk score + level.
        risk_score = normalize_to_risk_score(
            raw_score, art.score_low, art.score_high
        )
        risk_level = classify_risk_level(risk_score)

        # 6. Top-3 deviations.
        observed: dict[str, float] = {
            name: float(feature_row.features.get(name, 0.0)) for name in art.feature_columns
        }
        deviations: list[BehavioralDeviation] = top_deviations(
            prepared.zscores,
            prepared.baseline_means,
            prepared.baseline_stds,
            observed,
            top_n=3,
        )

        result = AnomalyResult(
            user_id=user_id,
            source_dataset=feature_row.source_dataset,
            window=feature_row.window,
            window_start=feature_row.window_start,
            window_end=feature_row.window_end,
            model_version=art.model_version,
            feature_version=feature_row.feature_version,
            prediction=prediction,
            raw_anomaly_score=float(raw_score),
            risk_score=float(risk_score),
            risk_level=risk_level,
            top_behavioral_deviations=deviations,
            model_input={
                name: float(v) for name, v in zip(art.model_features, prepared.vector, strict=False)
            },
            baseline_source=prepared.baseline_source,
        )

        if persist:
            await self.result_store.upsert(result)
            log.info(
                "anomaly.detection.persisted",
                user_id=user_id,
                prediction=prediction.value,
                risk_score=float(risk_score),
                risk_level=risk_level.value,
                baseline_source=prepared.baseline_source,
            )
            # Phase 6 integration: notify the alert observer (if any)
            # about the freshly persisted result.  This is the single
            # integration point that wires the anomaly pipeline to
            # downstream consumers (alert generation, audit, etc.).
            if self.alert_observer is not None:
                try:
                    await self.alert_observer(result)
                except Exception:  # noqa: BLE001
                    # The observer is contractually required to swallow
            # its own errors, but we double-guard here so a buggy
                    # observer never breaks the anomaly pipeline.
                    log.exception(
                        "anomaly.alert_observer_raised",
                        user_id=user_id,
                    )
        return result

    async def detect_for_user(
        self,
        *,
        user_id: str,
        start: datetime,
        end: datetime,
        source_dataset: str = "all",
        window: str = "daily",
        persist: bool = True,
    ) -> list[AnomalyResult]:
        """Detect anomalies for every (window, window_start) row of a user
        within `[start, end)`.  Returns one AnomalyResult per row.
        """
        rows = await self.feature_store.list_for_user(
            user_id=user_id,
            start=start,
            end=end,
            source_dataset=None if source_dataset == "all" else source_dataset,
        )
        results: list[AnomalyResult] = []
        for r in rows:
            if r.window != window:
                continue
            res = await self.detect_for_user_window(
                user_id=user_id,
                window_start=r.window_start,
                window_end=r.window_end,
                source_dataset=source_dataset,
                window=window,
                persist=persist,
            )
            results.append(res)
        return results

    async def detect_for_window(
        self,
        *,
        start: datetime,
        end: datetime,
        source_dataset: str = "all",
        window: str = "daily",
        persist: bool = True,
    ) -> list[AnomalyResult]:
        """Detect anomalies for every user in `[start, end)`.

        Discovers users from the feature store, then runs per-user
        detection.  Suitable for batch jobs.
        """
        users = await self.feature_store.list_users_with_features(
            source_dataset=None if source_dataset == "all" else source_dataset
        )
        results: list[AnomalyResult] = []
        for user_id in users:
            try:
                user_results = await self.detect_for_user(
                    user_id=user_id,
                    start=start,
                    end=end,
                    source_dataset=source_dataset,
                    window=window,
                    persist=persist,
                )
                results.extend(user_results)
            except NoDataForDetectionError:
                continue
        return results

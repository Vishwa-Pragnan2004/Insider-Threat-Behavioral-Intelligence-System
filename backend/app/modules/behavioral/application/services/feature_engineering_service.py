"""
ITBIS — Behavioral Module: Application Service

Orchestrates feature generation and baseline management.

Both CERT and Windows-agent events flow through the same `CanonicalEvent`
schema and the same feature definitions.  Callers can scope the work
to one source dataset or to all combined.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from app.modules.behavioral.application.aggregator import (
    aggregate_empty_row,
    aggregate_features,
    iter_daily_windows,
    normalise_window,
)
from app.modules.behavioral.application.baseline import build_baseline
from app.modules.behavioral.domain.entities import BehavioralBaseline, BehavioralFeatures
from app.modules.behavioral.domain.enums import FEATURE_VERSION
from app.modules.behavioral.domain.exceptions import NoDataForBaselineError
from app.modules.behavioral.domain.repositories import (
    IBehavioralBaselineRepository,
    IBehavioralEventSource,
    IBehavioralFeatureStore,
)

log = structlog.get_logger(__name__)


class FeatureEngineeringService:
    """Generate user-level behavioral features and per-user baselines."""

    def __init__(
        self,
        feature_store: IBehavioralFeatureStore,
        baseline_repo: IBehavioralBaselineRepository,
        event_source: IBehavioralEventSource,
    ) -> None:
        self.feature_store = feature_store
        self.baseline_repo = baseline_repo
        self.event_source = event_source

    # ─── Feature generation ─────────────────────────────────

    async def generate_features(
        self,
        *,
        start: datetime,
        end: datetime,
        source_dataset: str = "all",
        user_ids: list[str] | None = None,
        window: str = "daily",
    ) -> list[BehavioralFeatures]:
        """
        Build per-user daily features for every user with events in [start, end).

        If `user_ids` is None, every user with events in the window is processed.
        """
        start, end = normalise_window(start, end)
        if source_dataset == "all":
            users = user_ids or await self._discover_users(None, start, end)
        else:
            users = user_ids or await self._discover_users(source_dataset, start, end)

        log.info(
            "behavioral.generate_features",
            n_users=len(users),
            start=start.isoformat(),
            end=end.isoformat(),
            source=source_dataset,
            window=window,
        )

        results: list[BehavioralFeatures] = []
        for user_id in users:
            if source_dataset == "all":
                events = await self.event_source.find_events(
                    user_id=user_id, start=start, end=end
                )
            else:
                events = await self.event_source.find_events(
                    user_id=user_id, source_dataset=source_dataset, start=start, end=end
                )

            if window == "daily":
                results.extend(
                    self._features_daily(user_id, events, source_dataset, start, end)
                )
            elif window in ("rolling_7d", "rolling_30d"):
                days = 7 if window == "rolling_7d" else 30
                results.extend(
                    self._features_rolling(
                        user_id, events, source_dataset, days, start, end
                    )
                )
            else:
                raise ValueError(f"Unsupported window: {window!r}")

        if results:
            await self.feature_store.upsert_many(results)
        return results

    def _features_daily(
        self,
        user_id: str,
        events: list[dict],
        source_dataset: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[BehavioralFeatures]:
        """One feature row per UTC day in [window_start, window_end)."""
        rows: list[BehavioralFeatures] = []
        for day_start, day_end in iter_daily_windows(window_start, window_end):
            day_events = [e for e in events if day_start <= _ts(e) < day_end]
            feats = (
                aggregate_features(day_events) if day_events else aggregate_empty_row()
            )
            rows.append(
                BehavioralFeatures(
                    user_id=user_id,
                    window="daily",
                    window_start=day_start,
                    window_end=day_end,
                    source_dataset=source_dataset,
                    features=feats,
                    event_count=len(day_events),
                )
            )
        return rows

    def _features_rolling(
        self,
        user_id: str,
        events: list[dict],
        source_dataset: str,
        days: int,
        window_start: datetime,
        window_end: datetime,
    ) -> list[BehavioralFeatures]:
        """Rolling N-day window features computed at the END of each day."""
        rows: list[BehavioralFeatures] = []
        for _day_start, day_end in iter_daily_windows(window_start, window_end):
            rolling_start = day_end - timedelta(days=days)
            windowed = [e for e in events if rolling_start <= _ts(e) < day_end]
            feats = (
                aggregate_features(windowed) if windowed else aggregate_empty_row()
            )
            rows.append(
                BehavioralFeatures(
                    user_id=user_id,
                    window=f"rolling_{days}d",
                    window_start=rolling_start,
                    window_end=day_end,
                    source_dataset=source_dataset,
                    features=feats,
                    event_count=len(windowed),
                )
            )
        return rows

    # ─── Baseline management ────────────────────────────────

    async def build_baseline(
        self,
        *,
        user_id: str,
        history_start: datetime,
        history_end: datetime,
        source_dataset: str = "all",
    ) -> BehavioralBaseline:
        """
        Build a per-user baseline from historical events.

        `history_end` is the EXCLUSIVE end of the historical window — it
        also serves as the start of the evaluation period.  The builder
        will refuse to use any event with timestamp >= history_end.
        """
        history_start, history_end = normalise_window(history_start, history_end)
        if source_dataset == "all":
            events = await self.event_source.find_events(
                user_id=user_id,
                start=history_start,
                end=history_end,
            )
        else:
            events = await self.event_source.find_events(
                user_id=user_id,
                source_dataset=source_dataset,
                start=history_start,
                end=history_end,
            )
        if not events:
            raise NoDataForBaselineError(
                f"No events for user {user_id!r} in [{history_start}, {history_end})."
            )

        # Build per-day features then aggregate to baseline stats.
        daily_rows: list[dict] = []
        for day_start, day_end in iter_daily_windows(history_start, history_end):
            day_events = [e for e in events if day_start <= _ts(e) < day_end]
            feats = (
                aggregate_features(day_events) if day_events else aggregate_empty_row()
            )
            daily_rows.append(
                {"window_start": day_start, "window_end": day_end, "features": feats}
            )

        stats = build_baseline(
            daily_rows,
            history_start=history_start,
            history_end=history_end,
        )
        observation_days = sum(
            1 for r in daily_rows if any(v > 0 for v in r["features"].values())
        )
        baseline = BehavioralBaseline(
            user_id=user_id,
            feature_version=FEATURE_VERSION,
            stats=stats,
            window_start=history_start,
            window_end=history_end,
            observation_days=observation_days,
            source_dataset=source_dataset,
        )
        return await self.baseline_repo.save(baseline)

    async def get_baseline(
        self, user_id: str, feature_version: str = FEATURE_VERSION
    ) -> BehavioralBaseline | None:
        return await self.baseline_repo.get(user_id, feature_version)

    async def list_features_for_user(
        self,
        user_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        source_dataset: str | None = None,
    ) -> list[BehavioralFeatures]:
        return await self.feature_store.list_for_user(
            user_id, start=start, end=end, source_dataset=source_dataset
        )

    # ─── Training dataset export (Phase 5) ───────────────────

    async def export_training_dataset(
        self,
        *,
        start: datetime,
        end: datetime,
        source_dataset: str = "all",
        window: str = "daily",
        output_dir: str = "./itbis_training_export",
    ):
        """Run a training dataset export (Phase 5).

        Returns an :class:`ExportResult` describing the artefacts written
        to `output_dir`.  See :class:`TrainingDatasetExporter` for the
        contract guarantees.
        """
        from app.modules.behavioral.application.training_export import (
            ExportRequest,
            TrainingDatasetExporter,
        )

        exporter = TrainingDatasetExporter(self.feature_store)
        return await exporter.export(
            ExportRequest(
                start=start,
                end=end,
                source_dataset=source_dataset,
                window=window,
                output_dir=output_dir,
                feature_version=FEATURE_VERSION,
            )
        )

    # ─── Helpers ────────────────────────────────────────────

    async def _discover_users(
        self,
        source_dataset: str | None,
        start: datetime,
        end: datetime,
    ) -> list[str]:
        # We can't efficiently ask Mongo for distinct user_ids filtered by
        # timestamp via the existing find_events API, so we walk the
        # canonical events for the window.  In Phase 5+ this becomes a
        # Mongo aggregation; for Phase 4 the in-memory dedup is fine for
        # CERT-sized datasets.
        events = await self.event_source.find_events(
            source_dataset=source_dataset,
            start=start,
            end=end,
            limit=500_000,
        )
        users: set[str] = set()
        for e in events:
            uid = e.get("user_id")
            if uid:
                users.add(uid)
        return sorted(users)


# ─── Internal helpers ───────────────────────────────────────


def _ts(ev: dict) -> datetime:
    """Parse a Mongo-stored event timestamp into a datetime."""
    from datetime import datetime as _dt

    value = ev.get("timestamp")
    if isinstance(value, _dt):
        return value
    if isinstance(value, str):
        return _dt.fromisoformat(value.replace("Z", "+00:00"))
    return _dt.fromtimestamp(0, tz=UTC)

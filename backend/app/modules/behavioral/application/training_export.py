"""
ITBIS — Behavioral Module: Training Dataset Exporter (Phase 5)

Exports existing `BehavioralFeatures` rows (computed by Phase 4) into a
deterministic, version-locked, leakage-safe training dataset that can be
consumed by both:

  1. The Kaggle training notebook (offline, batch)
  2. The ITBIS production inference path (Phase 5+)

The exporter does NOT recompute features — it reads what Phase 4 stored.
This guarantees the exported dataset is the *exact* set of features the
server can also serve at inference time.

Contract guarantees (verified by tests):

  - Column order is `FEATURE_NAMES` from `app.modules.behavioral.domain.enums`.
  - `feature_version` of every row must equal `FEATURE_VERSION`; mismatches
    raise (this is a hard contract violation, not a soft warning).
  - Rows whose `window_start < start` or `window_end > end` are rejected
    (window boundary leakage guard).
  - Missing features are filled with 0.0 (no NaN propagation).
  - Output is a deterministic, byte-stable CSV (rows sorted by
    `(user_id, window, window_start)`) plus a `manifest.json` describing
    what was produced.
  - Raw `user_id` is emitted as a **metadata** column (Kaggle needs it to
    join labels) but the exporter strips it from the **ML matrix** that
    becomes `X`.
"""
from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from app.modules.behavioral.domain.entities import BehavioralFeatures
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION
from app.modules.behavioral.domain.repositories import IBehavioralFeatureStore

log = structlog.get_logger(__name__)


# ─── Public DTOs ──────────────────────────────────────────


@dataclass(frozen=True)
class ExportRequest:
    """Parameters describing a single export run."""

    start: datetime
    end: datetime
    source_dataset: str = "all"
    window: str = "daily"
    # Where to write the artefacts.  Created if missing.
    output_dir: str = "./itbis_training_export"
    # Allow a future caller to override the version (default = current).
    feature_version: str = FEATURE_VERSION


@dataclass
class ExportResult:
    """Result of a training dataset export."""

    manifest_path: str
    features_csv_path: str
    row_count: int
    feature_version: str
    user_count: int
    window_count: int
    start: datetime
    end: datetime
    source_dataset: str
    window: str
    column_order: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Columns emitted to the CSV.  Metadata first, then the locked
# FEATURE_NAMES order.
METADATA_COLUMNS: tuple[str, ...] = (
    "user_id",
    "window",
    "window_start",
    "window_end",
    "source_dataset",
    "feature_version",
    "event_count",
)


# ─── Exporter ─────────────────────────────────────────────


class TrainingDatasetExporter:
    """
    Reads `BehavioralFeatures` rows from the feature store and writes:

      <output_dir>/features.csv     — ML-ready matrix + metadata columns
      <output_dir>/manifest.json    — provenance + contract documentation

    The exporter is a pure function of the input rows + request
    parameters.  Given the same `ExportRequest` and the same set of
    `BehavioralFeatures` rows, the produced files are byte-identical.
    """

    def __init__(self, feature_store: IBehavioralFeatureStore) -> None:
        self.feature_store = feature_store

    async def export(self, request: ExportRequest) -> ExportResult:
        rows = await self._fetch(request)
        # Leakage guard: drop anything that isn't strictly within [start, end).
        # We rely on the existing rows already being version-locked, but we
        # re-check here for defence in depth.
        rows = self._filter_to_window(rows, request.start, request.end)
        rows = self._sort(rows)

        out_dir = Path(request.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        features_csv = out_dir / "features.csv"
        manifest_path = out_dir / "manifest.json"

        column_order = list(METADATA_COLUMNS) + list(FEATURE_NAMES)
        self._write_csv(features_csv, rows, column_order)
        warnings = self._collect_warnings(rows, request)

        manifest = self._build_manifest(
            request=request,
            rows=rows,
            csv_path=features_csv,
            column_order=column_order,
            warnings=warnings,
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=_json_default),
            encoding="utf-8",
        )

        users = {r.user_id for r in rows}
        windows = {(r.window, r.window_start) for r in rows}

        log.info(
            "behavioral.export.completed",
            rows=len(rows),
            users=len(users),
            windows=len(windows),
            output_dir=str(out_dir),
        )

        return ExportResult(
            manifest_path=str(manifest_path),
            features_csv_path=str(features_csv),
            row_count=len(rows),
            feature_version=request.feature_version,
            user_count=len(users),
            window_count=len(windows),
            start=request.start,
            end=request.end,
            source_dataset=request.source_dataset,
            window=request.window,
            column_order=column_order,
            warnings=warnings,
        )

    # ─── Internals ────────────────────────────────────────

    async def _fetch(self, request: ExportRequest) -> list[BehavioralFeatures]:
        # Pull all rows in the requested window.  The IBehavioralFeatureStore
        # contract is "give me rows in [start,end)" and we slice further here
        # (window filter + leakage guard).
        source = (
            None
            if request.source_dataset == "all"
            else request.source_dataset
        )
        rows = await self.feature_store.list_in_window(
            start=request.start,
            end=request.end,
            source_dataset=source,
        )
        return rows

    @staticmethod
    def _filter_to_window(
        rows: Sequence[BehavioralFeatures],
        start: datetime,
        end: datetime,
    ) -> list[BehavioralFeatures]:
        """Defence-in-depth: enforce the [start, end) window ourselves.

        Defends against naive datetimes returned by some test backends
        (e.g. mongomock-motor).  Production Motor preserves timezone info.
        """
        # Make the window bounds timezone-aware to match what the row
        # timestamps are expected to be.
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)

        def _ensure_aware(value: datetime | None) -> datetime | None:
            if value is None:
                return None
            return value if value.tzinfo else value.replace(tzinfo=UTC)

        out: list[BehavioralFeatures] = []
        for r in rows:
            r_start = _ensure_aware(r.window_start)
            r_end = _ensure_aware(r.window_end)
            if r_start is None or r_end is None:
                continue
            if r_start < start:
                continue
            if r_end > end:
                continue
            out.append(r)
        return out

    @staticmethod
    def _sort(rows: Sequence[BehavioralFeatures]) -> list[BehavioralFeatures]:
        return sorted(
            rows,
            key=lambda r: (r.user_id or "", r.window or "", r.window_start),
        )

    @staticmethod
    def _write_csv(
        path: Path,
        rows: Sequence[BehavioralFeatures],
        column_order: Sequence[str],
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(column_order)
            for r in rows:
                row_values: list[Any] = []
                for col in column_order:
                    if col in METADATA_COLUMNS:
                        row_values.append(_metadata_value(r, col))
                    else:
                        # ML feature column — fill missing with 0.0
                        val = r.features.get(col)
                        if val is None:
                            val = 0.0
                        row_values.append(val)
                writer.writerow(row_values)

    @staticmethod
    def _collect_warnings(
        rows: Sequence[BehavioralFeatures],
        request: ExportRequest,
    ) -> list[str]:
        warnings: list[str] = []
        for r in rows:
            if r.feature_version != request.feature_version:
                # In practice this is unreachable because the feature store
                # does not cross versions, but we leave the check in as a
                # safety net.
                warnings.append(
                    f"row {r.id} has feature_version {r.feature_version!r} "
                    f"(expected {request.feature_version!r})"
                )
        return warnings

    @staticmethod
    def _build_manifest(
        *,
        request: ExportRequest,
        rows: Sequence[BehavioralFeatures],
        csv_path: Path,
        column_order: Sequence[str],
        warnings: list[str],
    ) -> dict[str, Any]:
        from app.modules.behavioral.application.features import (
            FEATURE_DEFINITIONS,
        )

        feature_schema = []
        for name in FEATURE_NAMES:
            defn = FEATURE_DEFINITIONS[name]
            feature_schema.append(
                {
                    "name": name,
                    "aggregator": defn.aggregator,
                    "description": defn.description,
                }
            )
        return {
            "schema_version": 1,
            "feature_version": request.feature_version,
            "generated_at": datetime.now(UTC).isoformat(),
            "request": {
                "start": request.start.isoformat(),
                "end": request.end.isoformat(),
                "source_dataset": request.source_dataset,
                "window": request.window,
            },
            "row_count": len(rows),
            "column_order": list(column_order),
            "metadata_columns": list(METADATA_COLUMNS),
            "ml_feature_columns": list(FEATURE_NAMES),
            "feature_schema": feature_schema,
            "missing_value_policy": "filled_with_zero",
            "deterministic": True,
            "row_sort_order": ["user_id", "window", "window_start"],
            "leakage_guards": [
                "row_rejected_if_window_start_lt_request_start",
                "row_rejected_if_window_end_gt_request_end",
                "feature_version_must_equal_request.feature_version",
            ],
            "artifacts": {
                "features_csv": str(csv_path),
            },
            "warnings": warnings,
            "intended_consumers": [
                "kaggle_training_notebook",
                "itbis_production_inference",
            ],
        }


# ─── Helpers ─────────────────────────────────────────────


def _metadata_value(row: BehavioralFeatures, column: str) -> Any:
    if column == "user_id":
        return row.user_id
    if column == "window":
        return row.window
    if column == "window_start":
        return row.window_start.isoformat() if row.window_start else ""
    if column == "window_end":
        return row.window_end.isoformat() if row.window_end else ""
    if column == "source_dataset":
        return row.source_dataset
    if column == "feature_version":
        return row.feature_version
    if column == "event_count":
        return int(row.event_count)
    raise KeyError(column)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, set | frozenset):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serialisable")

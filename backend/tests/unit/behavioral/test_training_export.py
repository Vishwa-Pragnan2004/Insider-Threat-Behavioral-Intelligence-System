"""
ITBIS — Unit tests for the training dataset exporter (Phase 5).

Covers:
  - column order is locked to FEATURE_NAMES
  - missing values are filled with 0.0
  - leakage guards: rows outside [start, end) are dropped
  - feature_version mismatch is surfaced as a warning
  - manifest.json contains the contract guarantees
  - export is deterministic: same input -> byte-identical CSV
  - Kaggle contract: user_id appears in metadata but is NOT an ML feature
"""
from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.behavioral.application.training_export import (
    METADATA_COLUMNS,
    ExportRequest,
    TrainingDatasetExporter,
)
from app.modules.behavioral.domain.entities import BehavioralFeatures
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION
from app.modules.behavioral.domain.repositories import IBehavioralFeatureStore

# ─── Fakes ────────────────────────────────────────────────


class FakeFeatureStore(IBehavioralFeatureStore):
    def __init__(self, rows: list[BehavioralFeatures] | None = None) -> None:
        self.docs: list[BehavioralFeatures] = list(rows or [])

    async def upsert_many(self, features):
        self.docs.extend(features)
        return len(features)

    async def list_for_user(self, user_id, start=None, end=None, source_dataset=None):
        return [
            d for d in self.docs if d.user_id == user_id
            and (start is None or d.window_start >= start)
            and (end is None or d.window_start < end)
            and (source_dataset is None or d.source_dataset == source_dataset)
        ]

    async def list_users_with_features(self, source_dataset=None):
        return sorted({d.user_id for d in self.docs})

    async def list_in_window(self, start=None, end=None, source_dataset=None):
        return [
            d for d in self.docs
            if (start is None or d.window_start >= start)
            and (end is None or d.window_start < end)
            and (source_dataset is None or d.source_dataset == source_dataset)
        ]


def _make_row(
    *,
    user_id: str = "alice",
    source_dataset: str = "cert",
    window: str = "daily",
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    event_count: int = 10,
    features: dict | None = None,
    feature_version: str = FEATURE_VERSION,
) -> BehavioralFeatures:
    return BehavioralFeatures(
        user_id=user_id,
        window=window,
        window_start=window_start
        or datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=window_end
        or datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
        source_dataset=source_dataset,
        features=features
        or {name: float(i + 1) for i, name in enumerate(FEATURE_NAMES)},
        event_count=event_count,
        feature_version=feature_version,
    )


@pytest.fixture
def tmp_export_dir(tmp_path) -> str:
    return str(tmp_path / "export")


# ─── Column order ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_csv_header_is_metadata_then_features(tmp_export_dir):
    store = FakeFeatureStore([_make_row()])
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    with Path(result.features_csv_path).open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)

    assert header[: len(METADATA_COLUMNS)] == list(METADATA_COLUMNS)
    assert header[len(METADATA_COLUMNS) :] == FEATURE_NAMES
    assert header == result.column_order


@pytest.mark.asyncio
async def test_export_csv_uses_locked_feature_names(tmp_export_dir):
    """The Kaggle training notebook reads columns by name.  Locking the
    order to FEATURE_NAMES means both training and inference see the
    same input vector."""
    store = FakeFeatureStore(
        [
            _make_row(
                user_id="alice",
                window_start=datetime(2026, 8, 1, tzinfo=UTC),
                window_end=datetime(2026, 8, 2, tzinfo=UTC),
                features={"total_activity_count": 7.0},
            ),
            _make_row(
                user_id="bob",
                window_start=datetime(2026, 8, 2, tzinfo=UTC),
                window_end=datetime(2026, 8, 3, tzinfo=UTC),
                features={"logon_count": 3.0},
            ),
        ]
    )
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 3, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    with Path(result.features_csv_path).open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert len(rows) == 2
    # Every ML-feature column must be present and numeric
    for col in FEATURE_NAMES:
        assert col in rows[0]
    # `user_id` is metadata, not a feature
    assert "user_id" not in FEATURE_NAMES
    # Missing features default to 0.0
    assert rows[0]["total_activity_count"] == "7.0"
    assert rows[0]["logon_count"] == "0.0"  # not in source row


# ─── Missing-value handling ──────────────────────────────


@pytest.mark.asyncio
async def test_export_fills_missing_features_with_zero(tmp_export_dir):
    partial_features = {"logon_count": 5.0, "file_activity_count": 2.0}
    store = FakeFeatureStore(
        [_make_row(features=partial_features)]
    )
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    with Path(result.features_csv_path).open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        row = next(reader)
    assert row["logon_count"] == "5.0"
    assert row["file_activity_count"] == "2.0"
    # Every other feature must be present and == 0.0 (no NaN)
    for name in FEATURE_NAMES:
        if name in partial_features:
            continue
        assert row[name] == "0.0", f"feature {name!r} is not 0.0"


@pytest.mark.asyncio
async def test_export_no_nan_in_output(tmp_export_dir):
    store = FakeFeatureStore([_make_row(features={"logon_count": 1.0})])
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    text = Path(result.features_csv_path).read_text(encoding="utf-8")
    assert "nan" not in text.lower()
    assert "NaN" not in text


# ─── Leakage guard ───────────────────────────────────────


@pytest.mark.asyncio
async def test_export_drops_rows_outside_window(tmp_export_dir):
    store = FakeFeatureStore(
        [
            # INSIDE [Aug 1, Aug 3) — keep
            _make_row(
                user_id="alice",
                window_start=datetime(2026, 8, 1, tzinfo=UTC),
                window_end=datetime(2026, 8, 2, tzinfo=UTC),
            ),
            # INSIDE — keep
            _make_row(
                user_id="bob",
                window_start=datetime(2026, 8, 2, tzinfo=UTC),
                window_end=datetime(2026, 8, 3, tzinfo=UTC),
            ),
            # BEFORE start — drop
            _make_row(
                user_id="ghost",
                window_start=datetime(2026, 7, 31, tzinfo=UTC),
                window_end=datetime(2026, 8, 1, tzinfo=UTC),
            ),
            # AFTER end — drop
            _make_row(
                user_id="future",
                window_start=datetime(2026, 8, 3, tzinfo=UTC),
                window_end=datetime(2026, 8, 4, tzinfo=UTC),
            ),
            # Straddles the upper boundary — drop
            _make_row(
                user_id="straddler",
                window_start=datetime(2026, 8, 2, 22, 0, tzinfo=UTC),
                window_end=datetime(2026, 8, 3, 6, 0, tzinfo=UTC),
            ),
        ]
    )
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 3, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    assert result.row_count == 2
    with Path(result.features_csv_path).open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert {r["user_id"] for r in rows} == {"alice", "bob"}


# ─── Feature-version safety ──────────────────────────────


@pytest.mark.asyncio
async def test_export_warns_on_feature_version_mismatch(tmp_export_dir):
    store = FakeFeatureStore(
        [
            _make_row(feature_version=FEATURE_VERSION),
            _make_row(feature_version="behavioral_features_v0_legacy"),
        ]
    )
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    assert any("feature_version" in w for w in result.warnings)


# ─── Manifest contract ───────────────────────────────────


@pytest.mark.asyncio
async def test_manifest_contains_contract_guarantees(tmp_export_dir):
    store = FakeFeatureStore([_make_row()])
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["feature_version"] == FEATURE_VERSION
    assert manifest["deterministic"] is True
    assert manifest["missing_value_policy"] == "filled_with_zero"
    assert manifest["ml_feature_columns"] == FEATURE_NAMES
    assert manifest["metadata_columns"] == list(METADATA_COLUMNS)
    # Kaggle workflow metadata
    assert "kaggle_training_notebook" in manifest["intended_consumers"]
    # All leakage guards documented
    for guard in manifest["leakage_guards"]:
        assert isinstance(guard, str)
    # Feature schema cross-references each feature with its aggregator
    schema_names = [f["name"] for f in manifest["feature_schema"]]
    assert schema_names == FEATURE_NAMES
    for entry in manifest["feature_schema"]:
        assert entry["aggregator"] in {"count", "event_match", "set_size"}


# ─── Determinism ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_is_byte_deterministic(tmp_export_dir):
    rows = [
        _make_row(
            user_id=u,
            window_start=datetime(2026, 8, 1, i, 0, tzinfo=UTC),
            window_end=datetime(2026, 8, 1, i + 1, 0, tzinfo=UTC),
        )
        for i, u in enumerate(["c", "a", "b"])
    ]
    store_a = FakeFeatureStore(list(rows))
    store_b = FakeFeatureStore(list(rows))

    out_a = str(Path(tmp_export_dir) / "a")
    out_b = str(Path(tmp_export_dir) / "b")
    res_a = await TrainingDatasetExporter(store_a).export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=out_a,
        )
    )
    res_b = await TrainingDatasetExporter(store_b).export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=out_b,
        )
    )
    csv_a = Path(res_a.features_csv_path).read_bytes()
    csv_b = Path(res_b.features_csv_path).read_bytes()
    assert csv_a == csv_b


@pytest.mark.asyncio
async def test_export_sorts_rows_by_user_window_start(tmp_export_dir):
    rows = [
        _make_row(
            user_id="bob",
            window_start=datetime(2026, 8, 2, tzinfo=UTC),
            window_end=datetime(2026, 8, 3, tzinfo=UTC),
        ),
        _make_row(
            user_id="alice",
            window_start=datetime(2026, 8, 1, tzinfo=UTC),
            window_end=datetime(2026, 8, 2, tzinfo=UTC),
        ),
    ]
    store = FakeFeatureStore(rows)
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 3, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    with Path(result.features_csv_path).open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        out = [r["user_id"] for r in reader]
    # Sorted by (user_id, window, window_start) -> alice, bob
    assert out == ["alice", "bob"]


# ─── Kaggle contract: no user_id leakage into the feature matrix ─


@pytest.mark.asyncio
async def test_user_id_is_metadata_not_feature(tmp_export_dir):
    store = FakeFeatureStore([_make_row(user_id="alice")])
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert "user_id" in manifest["metadata_columns"]
    assert "user_id" not in manifest["ml_feature_columns"]


# ─── Source-dataset filter ──────────────────────────────


@pytest.mark.asyncio
async def test_export_source_dataset_all_includes_both(tmp_export_dir):
    store = FakeFeatureStore(
        [
            _make_row(source_dataset="cert", user_id="alice"),
            _make_row(source_dataset="win_endpoint", user_id="alice"),
        ]
    )
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            source_dataset="all",
            output_dir=tmp_export_dir,
        )
    )
    assert result.row_count == 2


@pytest.mark.asyncio
async def test_export_source_dataset_filter_scopes_rows(tmp_export_dir):
    store = FakeFeatureStore(
        [
            _make_row(source_dataset="cert", user_id="alice"),
            _make_row(source_dataset="win_endpoint", user_id="alice"),
        ]
    )
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            source_dataset="cert",
            output_dir=tmp_export_dir,
        )
    )
    assert result.row_count == 1


# ─── Empty input ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_with_no_rows_creates_files_with_header_only(tmp_export_dir):
    store = FakeFeatureStore([])
    exporter = TrainingDatasetExporter(store)
    result = await exporter.export(
        ExportRequest(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
            output_dir=tmp_export_dir,
        )
    )
    assert result.row_count == 0
    assert Path(result.features_csv_path).exists()
    text = Path(result.features_csv_path).read_text(encoding="utf-8").strip()
    # Header row only
    assert text.count("\n") == 0

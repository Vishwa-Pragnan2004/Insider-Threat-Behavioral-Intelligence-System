"""
ITBIS — Unit tests: behavioural feature store upserts.

Regression: `upsert_many` `$set` a freshly generated `_id` on every call. The
first generation of a window worked, but re-generating the same window — which
the continuous detection pipeline does on every run — failed with MongoDB's
"immutable field '_id' was found to have been altered" WriteError.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.modules.behavioral.domain.entities import BehavioralFeatures
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION
from app.modules.behavioral.infrastructure.repositories import MongoBehavioralFeatureStore

DAY = datetime(2026, 9, 14, tzinfo=UTC)
NEXT_DAY = datetime(2026, 9, 15, tzinfo=UTC)


def _row(event_count: int, window_start: datetime = DAY) -> BehavioralFeatures:
    return BehavioralFeatures(
        id=uuid.uuid4(),
        user_id="alice",
        window="daily",
        window_start=window_start,
        window_end=window_start.replace(day=window_start.day + 1),
        source_dataset="all",
        features={name: float(event_count) for name in FEATURE_NAMES},
        feature_version=FEATURE_VERSION,
        event_count=event_count,
        generated_at=datetime.now(UTC),
    )


@pytest.fixture
def store():
    client = AsyncMongoMockClient()
    yield MongoBehavioralFeatureStore(client["itbis_test"])
    client.close()


@pytest.mark.asyncio
async def test_regenerating_a_window_updates_it_in_place(store):
    await store.upsert_many([_row(event_count=10)])
    await store.upsert_many([_row(event_count=25)])  # raised WriteError before the fix

    rows = await store.list_for_user("alice")

    assert len(rows) == 1
    assert rows[0].event_count == 25
    assert rows[0].features[FEATURE_NAMES[0]] == 25.0


@pytest.mark.asyncio
async def test_document_id_stays_stable_across_regenerations(store):
    first = _row(event_count=1)
    await store.upsert_many([first])
    await store.upsert_many([_row(event_count=2)])
    await store.upsert_many([_row(event_count=3)])

    docs = await store.db[store.COLLECTION].find({}).to_list(None)

    assert [d["_id"] for d in docs] == [str(first.id)]


@pytest.mark.asyncio
async def test_different_days_remain_separate_rows(store):
    await store.upsert_many([_row(event_count=5, window_start=DAY)])
    await store.upsert_many([_row(event_count=7, window_start=NEXT_DAY)])
    await store.upsert_many([_row(event_count=9, window_start=DAY)])

    rows = sorted(await store.list_for_user("alice"), key=lambda r: r.window_start)

    # MongoDB hands datetimes back without tzinfo, so compare calendar days.
    assert [(r.window_start.date(), r.event_count) for r in rows] == [
        (DAY.date(), 9),
        (NEXT_DAY.date(), 7),
    ]

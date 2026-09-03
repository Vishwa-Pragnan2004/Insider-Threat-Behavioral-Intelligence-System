"""Tests for the local persistent queue."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from itbis_agent.config import QueueConfig
from itbis_agent.queue import PersistentQueue
from itbis_agent.schemas import CanonicalEvent, EventType


@pytest.fixture
def queue(tmp_path) -> PersistentQueue:
    return PersistentQueue(
        QueueConfig(db_path=str(tmp_path / "queue.db"), max_pending_events=1000),
        agent_id="TEST-DEVICE",
    )


def _make_event(raw_event_id: str = "1", source: str = "win_endpoint") -> CanonicalEvent:
    return CanonicalEvent(
        event_id=uuid.uuid4(),
        event_type=EventType.LOGON,
        source_dataset=source,
        raw_event_id=raw_event_id,
        timestamp=datetime.now(UTC),
        user_id="DOMAIN\\alice",
        device_id="WS-DEV-001",
    )


def test_enqueue_returns_true_for_new_event(queue):
    assert queue.enqueue(_make_event("e1")) is True


def test_enqueue_returns_false_for_duplicate(queue):
    queue.enqueue(_make_event("e1"))
    assert queue.enqueue(_make_event("e1")) is False


def test_enqueue_different_raw_ids_are_independent(queue):
    assert queue.enqueue(_make_event("a")) is True
    assert queue.enqueue(_make_event("b")) is True
    assert queue.count_pending() == 2


def test_peek_returns_events_in_order(queue):
    queue.enqueue(_make_event("a"))
    queue.enqueue(_make_event("b"))
    queue.enqueue(_make_event("c"))
    queued = queue.peek()
    assert [q.idem_key for q in queued] == [
        "win_endpoint:a", "win_endpoint:b", "win_endpoint:c"
    ]


def test_peek_respects_limit(queue):
    for i in range(5):
        queue.enqueue(_make_event(str(i)))
    assert len(queue.peek(limit=3)) == 3


def test_mark_sent_removes_from_pending(queue):
    queue.enqueue(_make_event("a"))
    queue.enqueue(_make_event("b"))
    queued = queue.peek()
    queue.mark_sent([queued[0].id])
    assert queue.count_pending() == 1


def test_mark_failed_increments_attempts(queue):
    queue.enqueue(_make_event("a"))
    queued = queue.peek()
    queue.mark_failed([queued[0].id], reason="boom", delay_seconds=60)
    assert queue.peek() == []  # not ready yet (backoff)
    assert queue.count_pending() == 1


def test_mark_dead_drops_event(queue):
    queue.enqueue(_make_event("a"))
    queued = queue.peek()
    queue.mark_dead([queued[0].id], reason="permanent")
    assert queue.count_pending() == 0
    assert queue.count_dead() == 1


def test_stats(queue):
    queue.enqueue(_make_event("a"))
    queued = queue.peek()
    queue.mark_sent([queued[0].id])
    queue.enqueue(_make_event("b"))
    queue.mark_dead([queue.peek()[0].id], "perm")
    stats = queue.stats()
    assert stats["sent"] == 1
    assert stats["dead"] == 1
    assert stats["pending"] == 0


def test_queue_survives_restart(tmp_path):
    cfg = QueueConfig(db_path=str(tmp_path / "queue.db"), max_pending_events=1000)
    q1 = PersistentQueue(cfg, agent_id="x")
    q1.enqueue(_make_event("persistent-1"))
    q1.close()

    q2 = PersistentQueue(cfg, agent_id="x")
    queued = q2.peek()
    assert len(queued) == 1
    assert queued[0].idem_key == "win_endpoint:persistent-1"
    q2.close()


def test_peek_skips_events_with_future_next_attempt(queue):
    queue.enqueue(_make_event("a"))
    queued = queue.peek()
    queue.mark_failed([queued[0].id], reason="transient", delay_seconds=60)
    assert queue.peek() == []  # backoff window


def test_concurrent_enqueue_does_not_corrupt(tmp_path):
    import threading

    cfg = QueueConfig(db_path=str(tmp_path / "queue.db"), max_pending_events=10_000)
    q = PersistentQueue(cfg, agent_id="x")
    n = 200

    def produce(offset):
        for i in range(n):
            q.enqueue(_make_event(f"{offset}-{i}"))

    threads = [threading.Thread(target=produce, args=(t,)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert q.count_pending() == n * 4
    q.close()

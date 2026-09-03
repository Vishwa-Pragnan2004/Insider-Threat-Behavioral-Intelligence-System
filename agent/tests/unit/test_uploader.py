"""Tests for the HTTPS uploader (using respx to mock HTTP)."""
from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from itbis_agent.config import QueueConfig, ServerConfig, UploadConfig
from itbis_agent.queue import PersistentQueue
from itbis_agent.schemas import CanonicalEvent, EventType
from itbis_agent.uploader import (
    Uploader,
)


@pytest.fixture
def server_cfg() -> ServerConfig:
    return ServerConfig(
        base_url="https://itbis.test",
        api_key="test-key",
        events_path="/api/v1/ingestion/events",
        verify_tls=False,
        timeout_seconds=5.0,
    )


@pytest.fixture
def upload_cfg() -> UploadConfig:
    return UploadConfig(
        batch_size=10,
        flush_interval_seconds=0.5,
        max_retries=3,
        initial_backoff_seconds=0.05,
        max_backoff_seconds=1.0,
    )


@pytest.fixture
def queue(tmp_path) -> PersistentQueue:
    return PersistentQueue(
        QueueConfig(db_path=str(tmp_path / "u.db"), max_pending_events=1000),
        agent_id="TEST-DEVICE",
    )


def _seed(queue, n=3):
    events = []
    for i in range(n):
        ev = CanonicalEvent(
            event_type=EventType.LOGON,
            source_dataset="win_endpoint",
            raw_event_id=f"seed-{i}",
            timestamp=datetime.now(UTC),
            user_id=f"u{i}",
            device_id="WS-DEV-001",
        )
        queue.enqueue(ev)
        events.append(ev)
    return events


# ─── Happy path ─────────────────────────────────────────────


def test_tick_sends_pending_and_marks_sent(server_cfg, upload_cfg, queue):
    _seed(queue, n=2)
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="TEST-DEVICE")

    with respx.mock(base_url=server_cfg.base_url) as mock:
        route = mock.post(server_cfg.events_path).mock(
            return_value=httpx.Response(200, json={
                "accepted": 2, "duplicates": 0, "rejected": 0, "results": []
            })
        )
        stats = uploader.tick()

    assert route.called
    assert stats["sent"] == 2
    assert stats["rejected"] == 0
    assert queue.count_pending() == 0
    uploader.stop()


def test_tick_sends_zero_when_queue_empty(server_cfg, upload_cfg, queue):
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x")
    stats = uploader.tick()
    assert stats == {"sent": 0, "duplicates": 0, "rejected": 0, "retries": 0}
    uploader.stop()


def test_request_payload_shape(server_cfg, upload_cfg, queue):
    _seed(queue, n=1)
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="AGENT-007")

    with respx.mock(base_url=server_cfg.base_url) as mock:
        route = mock.post(server_cfg.events_path).mock(
            return_value=httpx.Response(200, json={
                "accepted": 1, "duplicates": 0, "rejected": 0, "results": []
            })
        )
        uploader.tick()

    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer test-key"
    assert sent.headers["Content-Type"] == "application/json"
    body = sent.read().decode()
    import json
    parsed = json.loads(body)
    assert parsed["agent_id"] == "AGENT-007"
    assert len(parsed["events"]) == 1
    assert parsed["events"][0]["user_id"].startswith("u")
    uploader.stop()


# ─── Retry on transient errors ──────────────────────────────


def test_5xx_triggers_retry_and_marks_failed(server_cfg, upload_cfg, queue):
    _seed(queue, n=1)
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x")

    with respx.mock(base_url=server_cfg.base_url) as mock:
        mock.post(server_cfg.events_path).mock(return_value=httpx.Response(503, text="busy"))
        stats = uploader.tick()

    assert stats == {"sent": 0, "duplicates": 0, "rejected": 0, "retries": 1}
    # Event is still pending (waiting on backoff)
    assert queue.count_pending() == 1
    # Force the queue to release the backoff so we can inspect attempts
    with queue._tx() as conn:
        conn.execute("UPDATE events SET next_attempt_at = NULL")
    queued = queue.peek()
    assert len(queued) == 1
    assert queued[0].attempts == 1
    uploader.stop()


def test_429_triggers_retry(server_cfg, upload_cfg, queue):
    _seed(queue, n=1)
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x")

    with respx.mock(base_url=server_cfg.base_url) as mock:
        mock.post(server_cfg.events_path).mock(return_value=httpx.Response(429))
        stats = uploader.tick()

    assert stats["retries"] == 1
    uploader.stop()


def test_timeout_triggers_retry(server_cfg, upload_cfg, queue):
    _seed(queue, n=1)
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x")

    with respx.mock(base_url=server_cfg.base_url) as mock:
        mock.post(server_cfg.events_path).mock(side_effect=httpx.ConnectTimeout("timeout"))
        stats = uploader.tick()

    assert stats["retries"] == 1
    uploader.stop()


# ─── Permanent failures ─────────────────────────────────────


def test_400_marks_dead(server_cfg, upload_cfg, queue):
    _seed(queue, n=2)
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x")

    with respx.mock(base_url=server_cfg.base_url) as mock:
        mock.post(server_cfg.events_path).mock(return_value=httpx.Response(400, text="bad"))
        stats = uploader.tick()

    assert stats["rejected"] == 2
    assert queue.count_pending() == 0
    assert queue.count_dead() == 2
    uploader.stop()


def test_401_is_permanent(server_cfg, upload_cfg, queue):
    _seed(queue, n=1)
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x")

    with respx.mock(base_url=server_cfg.base_url) as mock:
        mock.post(server_cfg.events_path).mock(return_value=httpx.Response(401, text="nope"))
        stats = uploader.tick()

    assert stats["rejected"] == 1
    assert queue.count_dead() == 1
    uploader.stop()


# ─── Backoff calculation ────────────────────────────────────


def test_backoff_grows_then_caps(server_cfg, upload_cfg, queue):
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x")
    assert uploader._compute_backoff(1) == pytest.approx(0.05)
    assert uploader._compute_backoff(2) == pytest.approx(0.10)
    assert uploader._compute_backoff(3) == pytest.approx(0.20)
    # Capped at max_backoff_seconds = 1.0
    assert uploader._compute_backoff(20) == pytest.approx(1.0)
    uploader.stop()


# ─── Unparseable ack ────────────────────────────────────────


def test_unparseable_ack_is_treated_as_transient(server_cfg, upload_cfg, queue):
    _seed(queue, n=1)
    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x")

    with respx.mock(base_url=server_cfg.base_url) as mock:
        mock.post(server_cfg.events_path).mock(
            return_value=httpx.Response(200, text="not json")
        )
        stats = uploader.tick()

    assert stats["retries"] == 1
    uploader.stop()


# ─── Verify client_factory hook ─────────────────────────────


def test_custom_client_factory(server_cfg, upload_cfg, queue, tmp_path):
    _seed(queue, n=1)

    def factory() -> httpx.Client:
        client = httpx.Client(
            base_url=server_cfg.base_url,
            headers={"X-Custom": "yes"},
            verify=False,
        )
        return client

    uploader = Uploader(server_cfg, upload_cfg, queue, agent_id="x", client_factory=factory)
    with respx.mock(base_url=server_cfg.base_url) as mock:
        route = mock.post(server_cfg.events_path).mock(
            return_value=httpx.Response(200, json={
                "accepted": 1, "duplicates": 0, "rejected": 0, "results": []
            })
        )
        uploader.tick()

    sent = route.calls.last.request
    assert sent.headers.get("X-Custom") == "yes"
    uploader.stop()

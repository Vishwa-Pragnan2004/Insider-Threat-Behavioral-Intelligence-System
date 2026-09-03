"""Tests for the agent runtime orchestrator."""
from __future__ import annotations

import time
from datetime import UTC

import httpx
import respx

from itbis_agent.collectors.mock import MockCollector
from itbis_agent.runtime import AgentRuntime
from itbis_agent.schemas import EventType


def _make_logon_event(raw_id: str = "4624-1"):
    import uuid
    from datetime import datetime

    from itbis_agent.schemas import CanonicalEvent

    return CanonicalEvent(
        event_id=uuid.uuid4(),
        event_type=EventType.LOGON,
        source_dataset="win_endpoint",
        raw_event_id=raw_id,
        timestamp=datetime.now(UTC),
        user_id="DOMAIN\\alice",
    )


def test_runtime_orchestration_collects_and_uploads(base_config):
    """End-to-end (in-process): collectors -> queue -> uploader -> server."""
    base_config.upload.flush_interval_seconds = 0.1
    base_config.upload.batch_size = 5

    from itbis_agent.runtime import COLLECTOR_REGISTRY

    class _PreloadedMock(MockCollector):
        def __init__(self, poll_interval_seconds: float = 0.05):
            super().__init__(poll_interval_seconds=poll_interval_seconds)
            for i in range(3):
                self.submit(
                    {
                        "source": "windows_security",
                        "event_id": 4624,
                        "record_number": i,
                        "time_generated": "2026-08-30T08:00:00+00:00",
                        "computer": "WS-DEV-001",
                        "category": "logon_success",
                        "strings": (
                            ["x"] * 5 + ["alice", "DOMAIN", "0x1"] + ["x"] * 4 + ["WS-DEV-001"]
                        ),
                    }
                )

    COLLECTOR_REGISTRY["preloaded"] = _PreloadedMock
    base_config.agent.enabled_collectors = ["preloaded"]
    runtime = AgentRuntime(base_config)

    received_batches: list[dict] = []

    def responder(request: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(request.content)
        received_batches.append(body)
        return httpx.Response(
            200,
            json={"accepted": len(body["events"]), "duplicates": 0, "rejected": 0, "results": []},
        )

    with respx.mock(base_url=base_config.server.base_url) as mock_route:
        mock_route.post(base_config.server.events_path).mock(side_effect=responder)

        import threading
        t = threading.Thread(target=runtime.start, daemon=True)
        t.start()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not received_batches:
            time.sleep(0.05)
        runtime.stop()
        t.join(timeout=5)

    assert received_batches, "no batches were uploaded"
    body = received_batches[0]
    assert body["agent_id"] == "TEST-DEVICE-001"
    assert len(body["events"]) == 3
    assert all(e["event_type"] == EventType.LOGON for e in body["events"])


def test_runtime_skips_unknown_collector(base_config):
    base_config.agent.enabled_collectors = ["nonexistent"]
    runtime = AgentRuntime(base_config)
    import threading
    t = threading.Thread(target=runtime.start, daemon=True)
    t.start()
    time.sleep(0.3)
    runtime.stop()
    t.join(timeout=2)
    # No exception is the assertion

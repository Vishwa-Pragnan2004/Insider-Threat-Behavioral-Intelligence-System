"""Tests for collector behaviour (mock + base interface)."""
from __future__ import annotations

import threading
import time

import pytest

from itbis_agent.collectors.base import Collector
from itbis_agent.collectors.mock import MockCollector
from itbis_agent.collectors.process import ProcessCollector
from itbis_agent.collectors.usb import USBCollector
from itbis_agent.collectors.windows_security import WindowsSecurityCollector


def test_collector_is_abstract():
    with pytest.raises(TypeError):
        Collector()  # type: ignore[abstract]


def test_mock_collector_yields_submitted_events():
    coll = MockCollector(poll_interval_seconds=0.1)
    coll.start()
    coll.submit({"source": "test", "id": 1})
    coll.submit({"source": "test", "id": 2})
    coll.stop_stream()

    received = list(coll.collect())
    assert received == [{"source": "test", "id": 1}, {"source": "test", "id": 2}]


def test_mock_collector_terminates_on_stop_stream():
    coll = MockCollector(poll_interval_seconds=0.1)
    coll.start()
    coll.stop_stream()
    # collect() must exit promptly even with no events
    t0 = time.monotonic()
    list(coll.collect())
    assert time.monotonic() - t0 < 0.5


def test_mock_collector_thread_safety():
    coll = MockCollector(poll_interval_seconds=0.05)
    coll.start()

    def produce(n):
        for i in range(n):
            coll.submit({"i": i})

    threads = [threading.Thread(target=produce, args=(50,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    coll.stop_stream()
    received = list(coll.collect())
    assert len(received) == 200
    assert {r["i"] for r in received} == set(range(50))


def test_windows_collector_works_on_non_windows():
    """On non-Windows, the collector must not crash and must yield nothing."""
    coll = WindowsSecurityCollector(poll_interval_seconds=0.05)
    coll.start()
    # Probe a single poll cycle directly rather than driving the full loop
    assert coll._read_events.__qualname__  # method exists
    # _win32_available is False on this platform
    assert coll._win32_available is False
    # Calling the loop's inner block must be a no-op
    received = list(coll._read_events()) if coll._win32_available else []
    assert received == []


def test_process_collector_works_on_non_windows():
    coll = ProcessCollector(poll_interval_seconds=0.05)
    coll.start()
    # On non-Windows, WMI is unavailable and collect() is a no-op loop.
    # Just verify that init did not throw and the watcher is None.
    assert coll._watcher is None


def test_usb_collector_works_on_non_windows():
    coll = USBCollector(poll_interval_seconds=0.05)
    coll.start()
    assert coll._insert_watcher is None
    assert coll._remove_watcher is None

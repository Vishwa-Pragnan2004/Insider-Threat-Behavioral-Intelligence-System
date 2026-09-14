"""Tests for collector behaviour (mock + base interface)."""
from __future__ import annotations

import sys
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


def _without_pywin32(monkeypatch, collector_cls) -> None:
    """
    Simulate a host without pywin32/WMI.

    These tests used to rely on the libraries simply not being installed, so
    they failed on any Windows dev machine with the `windows` extras.  Forcing
    the probe makes them test the fallback path deterministically everywhere.
    """
    monkeypatch.setattr(collector_cls, "_probe_windows", staticmethod(lambda: False))


def test_windows_collector_works_without_pywin32(monkeypatch):
    """Without pywin32 the collector must not crash and must yield nothing."""
    _without_pywin32(monkeypatch, WindowsSecurityCollector)
    coll = WindowsSecurityCollector(poll_interval_seconds=0.05)
    coll.start()
    assert coll._win32_available is False
    # The poll loop must not touch the event log at all.
    received = list(coll._read_events()) if coll._win32_available else []
    assert received == []


def test_process_collector_works_without_pywin32(monkeypatch):
    _without_pywin32(monkeypatch, ProcessCollector)
    coll = ProcessCollector(poll_interval_seconds=0.05)
    coll.start()
    # Without WMI, collect() is a no-op loop: init must not throw and no
    # watcher may be created.
    assert coll._watcher is None


def test_usb_collector_works_without_pywin32(monkeypatch):
    _without_pywin32(monkeypatch, USBCollector)
    coll = USBCollector(poll_interval_seconds=0.05)
    coll.start()
    assert coll._insert_watcher is None
    assert coll._remove_watcher is None


# ─── Windows Security: privilege handling ───────────────────


def test_security_collector_disables_itself_without_elevation(monkeypatch):
    """
    Without Administrator rights the collector must go inert and say so,
    not spin on an access-denied exception every poll.
    """
    coll = WindowsSecurityCollector(poll_interval_seconds=0.05)
    monkeypatch.setattr(coll, "_win32_available", True)
    monkeypatch.setattr(type(coll), "_is_elevated", staticmethod(lambda: False))

    coll.start()

    assert coll._readable is False


def test_security_collector_stays_enabled_when_elevated(monkeypatch):
    coll = WindowsSecurityCollector(poll_interval_seconds=0.05)
    monkeypatch.setattr(coll, "_win32_available", True)
    monkeypatch.setattr(type(coll), "_is_elevated", staticmethod(lambda: True))

    coll.start()

    assert coll._readable is True


def test_security_collector_goes_inert_on_runtime_access_denied(monkeypatch):
    """A mid-run PermissionError disables the collector instead of looping."""
    coll = WindowsSecurityCollector(poll_interval_seconds=0.01)
    monkeypatch.setattr(coll, "_win32_available", True)
    monkeypatch.setattr(type(coll), "_is_elevated", staticmethod(lambda: True))

    calls = {"read": 0, "sleep": 0}

    def _boom():
        calls["read"] += 1
        raise PermissionError("access is denied")
        yield  # pragma: no cover - makes this a generator function

    def _fake_sleep(seconds=None):
        # Drive a bounded number of poll cycles, then end the loop so the
        # generator terminates instead of blocking the test run.
        calls["sleep"] += 1
        if calls["sleep"] >= 3:
            coll._running = False

    monkeypatch.setattr(coll, "_read_events", _boom)
    monkeypatch.setattr(coll, "_sleep", _fake_sleep)
    coll.start()

    assert list(coll.collect()) == []
    # Three poll cycles, but the source is consulted only once: after the
    # access-denied the collector is inert rather than retrying every poll.
    assert calls["sleep"] == 3
    assert calls["read"] == 1
    assert coll._readable is False


def test_is_elevated_probe_is_safe_on_every_platform():
    """
    The probe must return a bool and never raise, on Windows or otherwise.

    On non-Windows the shell32 call is unavailable and the probe reports True
    so the cross-platform test path is unaffected; on Windows it reports the
    real elevation state of the process.
    """
    result = WindowsSecurityCollector._is_elevated()
    assert isinstance(result, bool)
    if sys.platform != "win32":
        assert result is True

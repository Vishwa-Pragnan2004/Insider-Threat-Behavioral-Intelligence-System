# ruff: noqa: N802
# FakeCom mirrors real COM/WMI method names (CoInitialize, GetObject,
# ExecNotificationQuery, NextEvent) so the collectors can call it unchanged.
"""
Thread-affinity and error-visibility tests for the WMI collectors.

Regression: the runtime calls `collector.start()` on the main thread and
`collector.collect()` on a worker thread. The process and USB collectors
built their WMI watchers in start() and polled them in collect(), so every
poll failed with CO_E_NOTINITIALIZED — and the failure was swallowed. Both
collectors reported "started" and produced no events, ever.

`FakeCom` enforces COM's threading rules the way real COM does, so these
tests fail against that design and pass only when WMI objects are created and
used on the collecting thread.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
import types
from types import SimpleNamespace

import pytest
from structlog.testing import capture_logs

from itbis_agent.collectors.process import ProcessCollector
from itbis_agent.collectors.usb import USBCollector

WBEM_E_TIMED_OUT = -2147209215
CO_E_NOTINITIALIZED = -2147221008
RPC_E_WRONG_THREAD = -2147417842


def _com_error(scode: int) -> Exception:
    """Shaped like pywintypes.com_error: (hresult, text, excepinfo, argerr)."""
    return Exception(
        -2147352567,
        "Exception occurred.",
        (0, "SWbemEventSource", None, None, 0, scode),
        None,
    )


# ─── Fake COM layer ─────────────────────────────────────────


class FakeCom:
    """Stand-in for `pythoncom` + `win32com.client` that enforces thread rules."""

    def __init__(self, events_by_query=None, poll_error: int | None = None) -> None:
        self.events_by_query = events_by_query or {}
        self.poll_error = poll_error
        self.initialized: set[int] = set()
        self.calls: list[tuple[str, int]] = []
        self._lock = threading.Lock()

    def record(self, name: str) -> None:
        with self._lock:
            self.calls.append((name, threading.get_ident()))

    # pythoncom
    def CoInitialize(self) -> None:
        self.record("CoInitialize")
        self.initialized.add(threading.get_ident())

    def CoUninitialize(self) -> None:
        self.record("CoUninitialize")
        self.initialized.discard(threading.get_ident())

    # win32com.client
    def GetObject(self, moniker: str):
        self.record("GetObject")
        if threading.get_ident() not in self.initialized:
            raise _com_error(CO_E_NOTINITIALIZED)
        return FakeServices(self, owner=threading.get_ident())

    def install(self, monkeypatch) -> None:
        pythoncom = types.ModuleType("pythoncom")
        pythoncom.CoInitialize = self.CoInitialize
        pythoncom.CoUninitialize = self.CoUninitialize
        client = types.ModuleType("win32com.client")
        client.GetObject = self.GetObject
        package = types.ModuleType("win32com")
        package.client = client
        monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
        monkeypatch.setitem(sys.modules, "win32com", package)
        monkeypatch.setitem(sys.modules, "win32com.client", client)

    def threads_that_used_wmi(self) -> set[int]:
        wmi_calls = {"GetObject", "ExecNotificationQuery", "NextEvent"}
        return {tid for name, tid in self.calls if name in wmi_calls}


class FakeServices:
    def __init__(self, com: FakeCom, owner: int) -> None:
        self.com = com
        self.owner = owner

    def ExecNotificationQuery(self, query: str):
        self.com.record("ExecNotificationQuery")
        event_class = query.split()[3]  # "Select * From <class> Within ..."
        events = list(self.com.events_by_query.get(event_class, []))
        return FakeWatcher(self.com, self.owner, events)


class FakeWatcher:
    def __init__(self, com: FakeCom, owner: int, events: list) -> None:
        self.com = com
        self.owner = owner
        self.events = events

    def NextEvent(self, timeout_ms: int):
        self.com.record("NextEvent")
        tid = threading.get_ident()
        if tid not in self.com.initialized:
            raise _com_error(CO_E_NOTINITIALIZED)
        if tid != self.owner:
            raise _com_error(RPC_E_WRONG_THREAD)
        if self.com.poll_error is not None:
            raise _com_error(self.com.poll_error)
        if self.events:
            target = self.events.pop(0)
            return SimpleNamespace(Properties_=lambda _name: SimpleNamespace(Value=target))
        time.sleep(timeout_ms / 10_000)
        raise _com_error(WBEM_E_TIMED_OUT)


# ─── Helpers ────────────────────────────────────────────────


def _force_windows(monkeypatch, collector_cls) -> None:
    monkeypatch.setattr(collector_cls, "_probe_windows", staticmethod(lambda: True))


def _drive(collector, *, stop_after_events: int | None = None, max_seconds: float = 3.0):
    """Run collect() on a worker thread, exactly as AgentRuntime does."""
    received: list[dict] = []

    def run() -> None:
        for raw in collector.collect():
            received.append(raw)
            if stop_after_events is not None and len(received) >= stop_after_events:
                collector.stop()

    timer = threading.Timer(max_seconds, collector.stop)
    worker = threading.Thread(target=run, name=f"collector-{collector.name}", daemon=True)
    timer.start()
    worker.start()
    worker.join(max_seconds + 5)
    timer.cancel()
    assert not worker.is_alive(), "collector did not stop"
    return received


def _process(name: str = "notepad.exe"):
    return SimpleNamespace(
        CreationDate="20260914140608.000000+330",
        Name=name,
        ProcessId=4242,
        ParentProcessId=1,
        CommandLine=f"{name} report.docx",
    )


def _disk(drive_type: int, device_id: str = "E:"):
    return SimpleNamespace(
        DriveType=drive_type,
        DeviceID=device_id,
        VolumeName="SANDISK",
        FileSystem="exFAT",
        Size="30000000000",
    )


# ─── The fake is faithful ───────────────────────────────────


def test_fake_com_rejects_the_old_cross_thread_design(monkeypatch):
    """Build on one thread, poll on another: must fail like real COM did."""
    com = FakeCom()
    com.install(monkeypatch)
    com.CoInitialize()
    watcher = com.GetObject("winmgmts:").ExecNotificationQuery(
        "Select * From __InstanceCreationEvent Within 2"
    )

    failures: list[int] = []

    def poll() -> None:
        try:
            watcher.NextEvent(10)
        except Exception as exc:  # noqa: BLE001
            failures.append(exc.args[2][5])

    worker = threading.Thread(target=poll)
    worker.start()
    worker.join()
    com.CoUninitialize()
    assert failures == [CO_E_NOTINITIALIZED]


# ─── Process collector ──────────────────────────────────────


def test_process_collector_start_does_not_touch_com(monkeypatch):
    com = FakeCom()
    com.install(monkeypatch)
    _force_windows(monkeypatch, ProcessCollector)

    ProcessCollector(poll_interval_seconds=0.01).start()

    assert com.calls == [], "start() runs on the main thread and must not use COM"


def test_process_collector_uses_wmi_only_on_its_own_thread(monkeypatch):
    com = FakeCom(events_by_query={"__InstanceCreationEvent": [_process()]})
    com.install(monkeypatch)
    _force_windows(monkeypatch, ProcessCollector)
    collector = ProcessCollector(poll_interval_seconds=0.01)
    collector.start()

    received = _drive(collector, stop_after_events=1)

    assert [r["process_name"] for r in received] == ["notepad.exe"]
    wmi_threads = com.threads_that_used_wmi()
    assert len(wmi_threads) == 1
    assert threading.get_ident() not in wmi_threads
    assert com.initialized == set(), "COM must be uninitialised when collect() ends"


def test_real_poll_errors_are_reported_once_and_timeouts_not_at_all(monkeypatch):
    # Timeouts only: nothing to report.
    quiet = FakeCom()
    quiet.install(monkeypatch)
    _force_windows(monkeypatch, ProcessCollector)
    collector = ProcessCollector(poll_interval_seconds=0.01)
    collector.start()
    with capture_logs() as logs:
        _drive(collector, max_seconds=0.4)
    assert not [e for e in logs if e["event"] == "collector.wmi_poll_error"]

    # A persistent real failure: visible, but logged once rather than per poll.
    broken = FakeCom(poll_error=RPC_E_WRONG_THREAD)
    broken.install(monkeypatch)
    collector = ProcessCollector(poll_interval_seconds=0.01)
    collector.start()
    with capture_logs() as logs:
        _drive(collector, max_seconds=0.4)
    errors = [e for e in logs if e["event"] == "collector.wmi_poll_error"]
    assert len(errors) == 1
    assert errors[0]["log_level"] == "error"


# ─── USB collector ──────────────────────────────────────────


def test_usb_collector_reports_insert_and_remove_on_its_own_thread(monkeypatch):
    com = FakeCom(
        events_by_query={
            "__InstanceCreationEvent": [_disk(2)],
            "__InstanceDeletionEvent": [_disk(2)],
        }
    )
    com.install(monkeypatch)
    _force_windows(monkeypatch, USBCollector)
    collector = USBCollector(poll_interval_seconds=0.01)
    collector.start()
    assert com.calls == [], "start() must not use COM"

    received = _drive(collector, stop_after_events=2)

    assert [r["kind"] for r in received] == ["insert", "remove"]
    assert all(r["device_id"] == "E:" for r in received)
    assert all(r["time_generated"] for r in received)
    wmi_threads = com.threads_that_used_wmi()
    assert len(wmi_threads) == 1
    assert threading.get_ident() not in wmi_threads


def test_usb_collector_logs_drives_it_ignores(monkeypatch):
    """A USB drive reporting as a fixed disk must not disappear silently."""
    com = FakeCom(events_by_query={"__InstanceCreationEvent": [_disk(3)]})
    com.install(monkeypatch)
    _force_windows(monkeypatch, USBCollector)
    collector = USBCollector(poll_interval_seconds=0.01)
    collector.start()

    with capture_logs() as logs:
        received = _drive(collector, max_seconds=0.4)

    assert received == []
    ignored = [e for e in logs if e["event"] == "collector.usb_ignored_non_removable"]
    assert len(ignored) == 1
    assert ignored[0]["drive_type"] == 3
    assert ignored[0]["drive"] == "E:"


# ─── Real WMI (Windows only) ────────────────────────────────


@pytest.mark.skipif(sys.platform != "win32", reason="requires real Windows WMI")
def test_process_collector_receives_real_wmi_events():
    """The actual collector, on a worker thread, must see a real process start."""
    pytest.importorskip("win32com.client")
    collector = ProcessCollector(poll_interval_seconds=0.2)
    collector.start()

    seen = threading.Event()
    names: list[str] = []

    def run() -> None:
        for raw in collector.collect():
            names.append(str(raw["process_name"]))
            if str(raw["process_name"]).lower() == "ping.exe":
                seen.set()
                collector.stop()

    worker = threading.Thread(target=run, name="collector-process", daemon=True)
    worker.start()
    time.sleep(3)  # let the subscription settle (WMI polls "Within 2")
    ping = subprocess.Popen(["ping", "-n", "5", "127.0.0.1"], stdout=subprocess.DEVNULL)
    try:
        got_it = seen.wait(15)
    finally:
        collector.stop()
        ping.wait()
        worker.join(5)

    assert got_it, f"no ping.exe creation event received; saw {names[:10]}"

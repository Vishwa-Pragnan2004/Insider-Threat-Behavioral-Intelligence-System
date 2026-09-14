"""Network connection tracking and the network collector's poll."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
import structlog

from itbis_agent.collectors._wmi import PollErrorReporter
from itbis_agent.collectors.network import (
    TCP_STATE_ESTABLISHED,
    TCP_STATE_LISTEN,
    ConnectionTracker,
    NetworkCollector,
    TcpConnection,
    is_uninteresting_remote,
    process_identity,
)

USER_SID = "S-1-5-21-823331484-1016666011-1433572944-1001"
PUBLIC = "93.184.216.34"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _conn(
    remote=PUBLIC,
    remote_port=443,
    local_port=50000,
    pid=100,
    state=TCP_STATE_ESTABLISHED,
    local="10.0.0.2",
):
    return TcpConnection(local, local_port, remote, remote_port, state, pid)


# ─── ConnectionTracker ──────────────────────────────────────


def test_first_poll_is_a_baseline():
    assert ConnectionTracker().update([_conn()]) == []


def test_new_outbound_connection_is_reported_once():
    tracker = ConnectionTracker()
    tracker.update([])

    [new] = tracker.update([_conn()])

    assert new.connection.remote_address == PUBLIC
    assert new.direction == "outbound"
    assert tracker.update([_conn()]) == [], "still open, so not new"


@pytest.mark.parametrize("remote", ["127.0.0.1", "::1", "0.0.0.0", "::", "::ffff:127.0.0.1"])
def test_traffic_that_never_leaves_the_host_is_ignored(remote):
    tracker = ConnectionTracker()
    tracker.update([])
    assert tracker.update([_conn(remote=remote)]) == []


def test_lan_and_link_local_peers_are_kept():
    assert is_uninteresting_remote("192.168.1.20") is False
    assert is_uninteresting_remote("fe80::1%12") is False
    assert is_uninteresting_remote("not-an-address") is True


def test_inbound_connection_is_recognised_by_its_listening_socket():
    tracker = ConnectionTracker()
    tracker.update([])
    listener = _conn(remote="0.0.0.0", remote_port=0, local_port=3389, pid=900,
                     state=TCP_STATE_LISTEN)
    session = _conn(remote="203.0.113.7", remote_port=61000, local_port=3389, pid=900)

    [new] = tracker.update([listener, session])

    assert new.direction == "inbound"


def test_only_established_connections_count():
    tracker = ConnectionTracker()
    tracker.update([])
    time_wait = 11
    assert tracker.update([_conn(state=time_wait)]) == []


def test_repeat_connections_to_one_endpoint_are_suppressed_within_the_window():
    clock = FakeClock()
    tracker = ConnectionTracker(repeat_window_seconds=300, clock=clock)
    tracker.update([])

    assert len(tracker.update([_conn(local_port=50001)])) == 1
    tracker.update([])  # connection closed
    clock.now += 60
    assert tracker.update([_conn(local_port=50002)]) == [], "same process and server, 1 min later"
    tracker.update([])
    clock.now += 400
    assert len(tracker.update([_conn(local_port=50003)])) == 1, "window has elapsed"


def test_many_parallel_connections_to_one_endpoint_are_one_event():
    tracker = ConnectionTracker()
    tracker.update([])
    rows = [_conn(local_port=port) for port in range(50000, 50006)]
    assert len(tracker.update(rows)) == 1


def test_kernel_connections_are_system_without_querying_wmi():
    assert process_identity(None, 4) == ("System", "NT AUTHORITY\\SYSTEM", "S-1-5-18")


# ─── NetworkCollector._poll with a fake WMI ─────────────────


class FakeWmiNamespace:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.processes: dict[int, SimpleNamespace] = {}
        self.fail_tcp = False

    def ExecQuery(self, query):  # noqa: N802 - mirrors the WMI COM method name
        if "MSFT_NetTCPConnection" in query:
            if self.fail_tcp:
                raise RuntimeError("WMI provider failure")
            return [SimpleNamespace(**row) for row in self.rows]
        pid = int(query.rsplit("=", 1)[1])
        return [self.processes[pid]] if pid in self.processes else []


def _row(remote=PUBLIC, remote_port=443, local_port=50000, pid=100, state=TCP_STATE_ESTABLISHED):
    return {
        "LocalAddress": "10.0.0.2",
        "LocalPort": local_port,
        "RemoteAddress": remote,
        "RemotePort": remote_port,
        "State": state,
        "OwningProcess": pid,
    }


def _process(name="chrome.exe", user="vishw", domain="VISHWA"):
    def exec_method(method):
        if method == "GetOwner":
            return SimpleNamespace(ReturnValue=0, User=user, Domain=domain)
        return SimpleNamespace(ReturnValue=0, Sid=USER_SID)

    return SimpleNamespace(Name=name, ParentProcessId=1, ExecMethod_=exec_method)


@pytest.fixture
def errors():
    return PollErrorReporter(structlog.get_logger(), "network")


def test_poll_reports_a_new_connection_with_its_process_and_user(errors):
    wmi = FakeWmiNamespace()
    wmi.processes[100] = _process()
    collector = NetworkCollector()
    wmi.rows = [_row(remote="198.51.100.9")]
    assert collector._poll(wmi, wmi, errors) == [], "baseline"

    wmi.rows.append(_row())
    [event] = collector._poll(wmi, wmi, errors)

    assert event["source"] == "network"
    assert event["remote_address"] == PUBLIC
    assert event["remote_port"] == 443
    assert event["direction"] == "outbound"
    assert event["process_name"] == "chrome.exe"
    assert event["user"] == "VISHWA\\vishw"
    assert event["owner_sid"] == USER_SID


def test_poll_survives_a_wmi_failure(errors):
    wmi = FakeWmiNamespace()
    wmi.fail_tcp = True
    assert NetworkCollector()._poll(wmi, wmi, errors) == []


def test_connection_of_an_exited_process_has_no_owner(errors):
    wmi = FakeWmiNamespace()
    collector = NetworkCollector()
    collector._poll(wmi, wmi, errors)
    wmi.rows = [_row(pid=4242)]

    [event] = collector._poll(wmi, wmi, errors)

    assert event["process_name"] is None
    assert event["user"] is None


@pytest.mark.skipif(sys.platform != "win32", reason="real MSFT_NetTCPConnection")
def test_real_connection_table_can_be_read():
    pytest.importorskip("win32com.client")
    import win32com.client

    from itbis_agent.collectors._wmi import com_apartment
    from itbis_agent.collectors.network import read_connection_table

    with com_apartment():
        namespace = win32com.client.GetObject("winmgmts:root/StandardCimv2")
        try:
            rows = read_connection_table(namespace)
        finally:
            namespace = None

    assert isinstance(rows, list)
    assert all(isinstance(row, TcpConnection) for row in rows)

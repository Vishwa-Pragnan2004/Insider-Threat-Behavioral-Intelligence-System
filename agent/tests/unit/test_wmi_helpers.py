"""Unit tests for the shared WMI helpers."""
from __future__ import annotations

import pytest

from itbis_agent.collectors._wmi import WBEM_E_TIMED_OUT, PollErrorReporter, is_timeout

CO_E_NOTINITIALIZED = -2147221008
RPC_E_WRONG_THREAD = -2147417842


def _com_error(scode: int) -> Exception:
    return Exception(
        -2147352567,
        "Exception occurred.",
        (0, "SWbemEventSource", None, None, 0, scode),
        None,
    )


def test_is_timeout_recognises_wbem_timeout():
    assert is_timeout(_com_error(WBEM_E_TIMED_OUT)) is True


@pytest.mark.parametrize(
    "exc",
    [
        _com_error(CO_E_NOTINITIALIZED),
        _com_error(RPC_E_WRONG_THREAD),
        RuntimeError("boom"),
        Exception(),
        Exception(-1, "short args"),
    ],
)
def test_is_timeout_rejects_real_failures(exc):
    """The thread-affinity bug surfaced as CO_E_NOTINITIALIZED — never a timeout."""
    assert is_timeout(exc) is False


class RecordingLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def error(self, event: str, **kw) -> None:
        self.records.append(("error", event, kw))

    def info(self, event: str, **kw) -> None:
        self.records.append(("info", event, kw))


def test_reporter_logs_each_distinct_error_once():
    log = RecordingLog()
    reporter = PollErrorReporter(log, "process")

    for _ in range(5):
        reporter.failed(RuntimeError("wrong thread"))
    reporter.failed(RuntimeError("access denied"))

    errors = [r for r in log.records if r[0] == "error"]
    assert [r[2]["error"] for r in errors] == ["wrong thread", "access denied"]
    assert all(r[2]["name"] == "process" for r in errors)


def test_reporter_announces_recovery_only_after_a_failure():
    log = RecordingLog()
    reporter = PollErrorReporter(log, "usb")

    reporter.recovered()
    assert log.records == []

    reporter.failed(RuntimeError("wrong thread"), watcher="insert")
    reporter.recovered()
    reporter.recovered()
    assert [r[:2] for r in log.records] == [
        ("error", "collector.wmi_poll_error"),
        ("info", "collector.wmi_poll_recovered"),
    ]
    assert log.records[0][2]["watcher"] == "insert"

    # After recovery the same error is news again.
    reporter.failed(RuntimeError("wrong thread"))
    assert len([r for r in log.records if r[0] == "error"]) == 2

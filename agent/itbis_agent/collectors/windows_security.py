"""
ITBIS Endpoint Agent — Windows Security Event Log collector

Reads the Windows Security event log for the following Event IDs:

  4624 — successful logon
  4625 — failed logon
  4634 — logoff
  4647 — user-initiated logoff

A bookmark (last seen record number) is kept in memory across polls; the
collector only yields events newer than the bookmark.

The collector imports `win32evtlog` lazily so the module is importable on
non-Windows platforms (used by the test suite).
"""
from __future__ import annotations

from collections.abc import Iterator

import structlog

from itbis_agent.collectors.base import Collector

log = structlog.get_logger(__name__)

# EventIDs the collector cares about
WANTED_EVENT_IDS: dict[int, str] = {
    4624: "logon_success",
    4625: "logon_failed",
    4634: "logoff",
    4647: "logoff_user_initiated",
}


class WindowsSecurityCollector(Collector):
    """
    Polls the Windows Security event log for authentication events.

    Falls back to a no-op iterator on non-Windows platforms so the agent can
    be developed and tested cross-platform.
    """

    name = "windows_security"
    LOG_NAME = "Security"

    def __init__(self, poll_interval_seconds: float = 2.0) -> None:
        super().__init__(poll_interval_seconds=poll_interval_seconds)
        self._bookmark: int | None = None
        self._win32_available: bool = self._probe_windows()

    # ─── Windows probe ──────────────────────────────────────

    @staticmethod
    def _probe_windows() -> bool:
        try:
            import win32evtlog  # type: ignore # noqa: F401
            return True
        except ImportError:
            return False

    # ─── Lifecycle ──────────────────────────────────────────

    def start(self) -> None:
        super().start()
        if not self._win32_available:
            log.warning(
                "collector.windows_unavailable",
                name=self.name,
                hint="Install pywin32 on a Windows host to enable this collector.",
            )

    # ─── Polling ────────────────────────────────────────────

    def collect(self) -> Iterator[dict]:
        while self._running:
            if self._win32_available:
                try:
                    yield from self._read_events()
                except Exception:  # noqa: BLE001
                    log.exception("collector.error", name=self.name)
            self._sleep()

    # ─── Windows event log access ───────────────────────────

    def _read_events(self) -> Iterator[dict]:
        import win32evtlog

        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        handle = win32evtlog.OpenEventLog(None, self.LOG_NAME)
        try:
            events = win32evtlog.ReadEventLog(handle, flags, 0)
            for ev in events:
                record_number = int(ev[0])  # EventLogRecord.RecordNumber
                if self._bookmark is not None and record_number <= self._bookmark:
                    continue
                self._bookmark = record_number
                event_id = int(ev[1])
                if event_id not in WANTED_EVENT_IDS:
                    continue

                # String inserts (event-specific) are in ev[9] (Strings)
                strings = list(ev[9]) if ev[9] else []
                yield {
                    "source": "windows_security",
                    "event_id": event_id,
                    "record_number": record_number,
                    "time_generated": ev[6].isoformat() if ev[6] else None,
                    "computer": ev[10] if len(ev) > 10 else None,
                    "strings": strings,
                    "category": WANTED_EVENT_IDS[event_id],
                }
        finally:
            win32evtlog.CloseEventLog(handle)

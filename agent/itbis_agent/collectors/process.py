"""
ITBIS Endpoint Agent — Process creation collector

Subscribes to process creation events. On Windows this is implemented via
Win32 WMI's `Win32_ProcessTrace` (requires the `WMI` package). The collector
yields one raw event per new process.

The collector is a no-op on non-Windows platforms.
"""
from __future__ import annotations

from collections.abc import Iterator

import structlog

from itbis_agent.collectors.base import Collector

log = structlog.get_logger(__name__)


class ProcessCollector(Collector):
    """Watches the host for new processes (Event ID 4688 equivalent)."""

    name = "process"

    def __init__(self, poll_interval_seconds: float = 2.0) -> None:
        super().__init__(poll_interval_seconds=poll_interval_seconds)
        self._wmi = None
        self._watcher = None
        self._win32_available: bool = self._probe_windows()

    @staticmethod
    def _probe_windows() -> bool:
        try:
            import win32com.client  # type: ignore # noqa: F401
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
            return
        try:
            import win32com.client  # type: ignore

            self._wmi = win32com.client.GetObject("winmgmts:")
            # __InstanceCreationEvent on Win32_Process — fires when a new
            # process is created.
            self._watcher = self._wmi.ExecNotificationQuery(
                "Select * From __InstanceCreationEvent "
                "Within 2 "
                "Where TargetInstance ISA 'Win32_Process'"
            )
        except Exception:  # noqa: BLE001
            log.exception("collector.wmi_init_failed", name=self.name)
            self._watcher = None

    def stop(self) -> None:
        super().stop()
        self._watcher = None

    # ─── Polling ────────────────────────────────────────────

    def collect(self) -> Iterator[dict]:
        if self._watcher is None:
            # No Windows WMI: nothing to do. Sleep so we don't busy-loop.
            while self._running:
                self._sleep()
            return

        while self._running:
            try:
                ev = self._watcher.NextEvent(1000)  # 1s timeout (ms)
            except Exception:  # noqa: BLE001
                # Timeout or transient — try again
                continue
            try:
                target = ev.Properties_("TargetInstance").Value
                yield {
                    "source": "process",
                    "event_id": 4688,
                    "time_generated": target.CreationDate,
                    "process_name": target.Name,
                    "process_id": target.ProcessId,
                    "parent_process_id": target.ParentProcessId,
                    "command_line": target.CommandLine,
                    "user": _parse_process_user(target),
                }
            except Exception:  # noqa: BLE001
                log.exception("collector.parse_error", name=self.name)
                continue


def _parse_process_user(target) -> str | None:
    """Best-effort user extraction from a Win32_Process target."""
    try:
        # Win32_Process doesn't carry the owner; query it lazily
        # (kept simple here — owner resolution is OS-level and racy).
        return None
    except Exception:  # noqa: BLE001
        return None

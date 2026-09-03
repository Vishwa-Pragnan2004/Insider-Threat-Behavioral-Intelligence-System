"""
ITBIS Endpoint Agent — USB / removable device collector

Watches for USB device insertion events. On Windows, the standard
mechanism is WMI's `Win32_VolumeChangeEvent` (drive letter appearance) plus
`__InstanceCreationEvent` on `Win32_USBHub`.

This collector:
  - emits a USB_INSERT raw event when a new removable drive appears
  - emits a USB_REMOVE raw event when a removable drive disappears

It is a no-op on non-Windows platforms.

NOTE: deep USB serial / vendor info can be unreliable on locked-down hosts
without admin rights. We emit the minimum useful identifiers here.
"""
from __future__ import annotations

from collections.abc import Iterator

import structlog

from itbis_agent.collectors.base import Collector

log = structlog.get_logger(__name__)


class USBCollector(Collector):
    name = "usb"

    def __init__(self, poll_interval_seconds: float = 3.0) -> None:
        super().__init__(poll_interval_seconds=poll_interval_seconds)
        self._wmi = None
        self._insert_watcher = None
        self._remove_watcher = None
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
            self._insert_watcher = self._wmi.ExecNotificationQuery(
                "Select * From __InstanceCreationEvent "
                "Within 3 "
                "Where TargetInstance ISA 'Win32_LogicalDisk'"
            )
            self._remove_watcher = self._wmi.ExecNotificationQuery(
                "Select * From __InstanceDeletionEvent "
                "Within 3 "
                "Where TargetInstance ISA 'Win32_LogicalDisk'"
            )
        except Exception:  # noqa: BLE001
            log.exception("collector.wmi_init_failed", name=self.name)
            self._insert_watcher = None
            self._remove_watcher = None

    def stop(self) -> None:
        super().stop()
        self._insert_watcher = None
        self._remove_watcher = None

    # ─── Polling ────────────────────────────────────────────

    def collect(self) -> Iterator[dict]:
        if self._insert_watcher is None or self._remove_watcher is None:
            while self._running:
                self._sleep()
            return

        while self._running:
            for watcher, kind in (
                (self._insert_watcher, "insert"),
                (self._remove_watcher, "remove"),
            ):
                try:
                    ev = watcher.NextEvent(500)  # 500ms
                except Exception:  # noqa: BLE001
                    continue
                try:
                    target = ev.Properties_("TargetInstance").Value
                    if int(target.DriveType) != 2:  # 2 = Removable
                        continue
                    yield {
                        "source": "usb",
                        "event_id": 2003 if kind == "insert" else 2100,
                        "kind": kind,
                        "device_id": target.DeviceID,
                        "volume_name": target.VolumeName,
                        "file_system": target.FileSystem,
                        "size_bytes": int(target.Size) if target.Size else None,
                    }
                except Exception:  # noqa: BLE001
                    log.exception("collector.parse_error", name=self.name)
                    continue

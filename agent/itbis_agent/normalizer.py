"""
ITBIS Endpoint Agent — Event normaliser

Converts raw event dicts produced by collectors into CanonicalEvent
documents ready for the persistent queue + upload.
"""
from __future__ import annotations

import os
import socket
import uuid
from datetime import UTC, datetime

import structlog

from itbis_agent._utils import _parse_iso
from itbis_agent.config import AgentConfig
from itbis_agent.schemas import CanonicalEvent, EventType

log = structlog.get_logger(__name__)


class Normaliser:
    """
    Stateless (apart from agent config) raw-event → CanonicalEvent mapper.

    Each collector's raw shape is well-defined and small, so we dispatch on
    `raw["source"]`. New collectors are added by registering a new method.
    """

    def __init__(self, agent_config: AgentConfig) -> None:
        self.cfg = agent_config
        self._host_ip = self._resolve_host_ip()
        self._os_version = self._resolve_os_version()

    # ─── Public API ─────────────────────────────────────────

    def normalise(self, raw: dict) -> CanonicalEvent | None:
        """Return a CanonicalEvent or None if the raw event can't be mapped."""
        source = raw.get("source")
        try:
            if source == "windows_security":
                return self._from_windows_security(raw)
            if source == "process":
                return self._from_process(raw)
            if source == "usb":
                return self._from_usb(raw)
            log.warning("normaliser.unknown_source", source=source)
            return None
        except Exception:  # noqa: BLE001
            log.exception("normaliser.error", source=source, raw=raw)
            return None

    # ─── Source: windows_security ───────────────────────────

    def _from_windows_security(self, raw: dict) -> CanonicalEvent | None:
        category = raw.get("category")
        strings = raw.get("strings") or []

        # Windows Security event string layout (EventID-specific):
        #   4624: [SubjectUserSid, SubjectUserName, SubjectDomainName,
        #          SubjectLogonId, TargetUserSid, TargetUserName,
        #          TargetDomainName, TargetLogonId, LogonType,
        #          LogonProcessName, AuthenticationPackageName,
        #          WorkstationName, LogonGuid, TransmittedServices,
        #          LmPackageName, KeyLength, ProcessId, ProcessName,
        #          IpAddress, IpPort]
        #   4625: similar but with Status / SubStatus / FailureReason
        #   4634: [SubjectUserSid, SubjectUserName, SubjectDomainName,
        #          SubjectLogonId, TargetUserSid, TargetUserName,
        #          TargetDomainName, TargetLogonId, LogonType]
        #   4647: [SubjectUserSid, SubjectUserName, SubjectDomainName,
        #          SubjectLogonId]
        if category in ("logon_success", "logon_failed"):
            target_user = strings[5] if len(strings) > 5 else None
            domain = strings[6] if len(strings) > 6 else None
        elif category in ("logoff", "logoff_user_initiated"):
            # 4634: SubjectUserName, SubjectDomainName at 1,2
            # 4647: same
            target_user = strings[1] if len(strings) > 1 else None
            domain = strings[2] if len(strings) > 2 else None
        else:
            return None

        if not target_user:
            return None

        user_id = self._format_user(target_user, domain)

        logon_categories = ("logon_success", "logon_failed")
        logon_type = strings[8] if len(strings) > 8 and category in logon_categories else None
        ip_address = strings[18] if len(strings) > 18 and category in logon_categories else None
        workstation = strings[11] if len(strings) > 11 and category in logon_categories else None

        event_type_map = {
            "logon_success": EventType.LOGON,
            "logon_failed": EventType.LOGON_FAILED,
            "logoff": EventType.LOGOFF,
            "logoff_user_initiated": EventType.LOGOFF,
        }
        event_type = event_type_map.get(category, EventType.UNKNOWN)

        return CanonicalEvent(
            event_id=uuid.uuid4(),
            event_type=event_type,
            source_dataset=self.cfg.source_dataset,
            raw_event_id=f"{raw.get('event_id')}-{raw.get('record_number')}",
            timestamp=_parse_iso(raw.get("time_generated")),
            user_id=user_id,
            username=user_id,
            device_id=self.cfg.device_id,
            device_name=workstation or self.cfg.device_name,
            device_type=self.cfg.device_type,
            ip_address=ip_address or self._host_ip,
            operating_system=self._os_version or self.cfg.operating_system,
            target_resource=workstation,
            target_type="workstation",
            action=str(raw.get("event_id")),
            result="success" if category == "logon_success" else (
                "failure" if category == "logon_failed" else "success"
            ),
            raw_payload={
                "category": category,
                "strings": strings,
                "computer": raw.get("computer"),
            },
            enrichments={"logon_type": logon_type} if logon_type else None,
            tags=[self.cfg.source_dataset, category],
        )

    # ─── Source: process ────────────────────────────────────

    def _from_process(self, raw: dict) -> CanonicalEvent | None:
        process_name = raw.get("process_name") or ""
        if not process_name:
            return None

        user = raw.get("user") or "SYSTEM"

        return CanonicalEvent(
            event_id=uuid.uuid4(),
            event_type=EventType.APP_LAUNCH,
            source_dataset=self.cfg.source_dataset,
            raw_event_id=f"4688-{raw.get('process_id')}",
            timestamp=_parse_iso(raw.get("time_generated")),
            user_id=user,
            username=user,
            device_id=self.cfg.device_id,
            device_name=self.cfg.device_name,
            device_type=self.cfg.device_type,
            ip_address=self._host_ip,
            operating_system=self._os_version or self.cfg.operating_system,
            target_resource=raw.get("command_line") or process_name,
            target_type="process",
            action=str(raw.get("event_id")),
            result="success",
            raw_payload={
                "process_name": process_name,
                "process_id": raw.get("process_id"),
                "parent_process_id": raw.get("parent_process_id"),
                "command_line": raw.get("command_line"),
            },
            tags=[self.cfg.source_dataset, "process", "app_launch"],
        )

    # ─── Source: usb ────────────────────────────────────────

    def _from_usb(self, raw: dict) -> CanonicalEvent | None:
        kind = raw.get("kind")
        device_id = raw.get("device_id") or "unknown"
        event_type = EventType.USB_INSERT if kind == "insert" else EventType.USB_REMOVE
        return CanonicalEvent(
            event_id=uuid.uuid4(),
            event_type=event_type,
            source_dataset=self.cfg.source_dataset,
            raw_event_id=f"{raw.get('event_id')}-{device_id}",
            timestamp=datetime.now(UTC),
            user_id=os.environ.get("USERNAME", "unknown"),
            device_id=self.cfg.device_id,
            device_name=self.cfg.device_name,
            device_type=self.cfg.device_type,
            ip_address=self._host_ip,
            operating_system=self._os_version or self.cfg.operating_system,
            target_resource=device_id,
            target_type="usb_device",
            action=str(raw.get("event_id")),
            result="success",
            raw_payload={
                "device_id": device_id,
                "volume_name": raw.get("volume_name"),
                "file_system": raw.get("file_system"),
                "size_bytes": raw.get("size_bytes"),
            },
            tags=[self.cfg.source_dataset, "usb"],
        )

    # ─── Helpers ────────────────────────────────────────────

    @staticmethod
    def _format_user(username: str, domain: str | None) -> str:
        username = (username or "").strip()
        if not username:
            return "unknown"
        if domain and "\\" not in username and "@" not in username:
            return f"{domain}\\{username}"
        return username

    @staticmethod
    def _resolve_host_ip() -> str | None:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _resolve_os_version() -> str | None:
        # Best-effort; on Windows, `platform.win32_ver()` returns a tuple
        return None  # set in start() hook if needed

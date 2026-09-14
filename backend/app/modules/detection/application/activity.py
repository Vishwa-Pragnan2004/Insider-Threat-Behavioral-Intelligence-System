"""
ITBIS — Detection Module: one person's activity for one day

`EventView` normalises a stored canonical event (agent telemetry or a CERT
row) into the handful of fields detectors use. `DailyActivity` summarises a
day of them, and `ActivityProfile` is that person's rolling history: what
their normal day looks like, learned incrementally one day at a time.

The same profile code serves the live pipeline (rebuilt from recent history
on each run) and dataset replays (carried forward in memory), so both judge
behaviour identically.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.modules.detection.application.web_categories import WebCategory, classify_url

LOGON = "logon"
LOGON_FAILED = "logon_failed"
USB_INSERT = "usb_insert"
REMOVABLE_COPY_TYPES = frozenset({"file_copy", "usb_file_copy", "data_transfer"})
UPLOAD_TYPES = frozenset({"http_upload", "file_upload"})
DOWNLOAD_TYPES = frozenset({"http_download", "file_download"})
WEB_TYPES = frozenset({"http_request", "http_upload", "http_download"})
EXTERNAL_EMAIL = "email_external"
EXECUTABLE_SUFFIXES = (".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".dll", ".scr")

#: Agent risk indicators that mean an account's privileges were changed.
PRIVILEGE_INDICATORS: dict[str, float] = {
    "privileged_group_member_added": 70.0,
    "sensitive_user_right_assigned": 70.0,
    "password_reset_of_other_account": 65.0,
    "account_created": 50.0,
}


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def is_executable(name: str | None) -> bool:
    return (name or "").lower().endswith(EXECUTABLE_SUFFIXES)


@dataclass(slots=True)
class EventView:
    event_type: str
    timestamp: datetime
    device_id: str | None = None
    target: str | None = None
    indicators: tuple[str, ...] = ()
    file_count: int = 0
    bytes: int = 0
    web_category: WebCategory | None = None
    event_id: str | None = None

    @property
    def hour(self) -> int:
        return self.timestamp.hour

    @classmethod
    def from_doc(cls, doc: dict) -> EventView | None:
        when = _as_utc(doc.get("timestamp"))
        event_type = (doc.get("event_type") or "").lower()
        if when is None or not event_type:
            return None
        target = doc.get("target_resource")
        category = None
        if event_type in WEB_TYPES:
            category = classify_url(target)
        elif event_type in DOWNLOAD_TYPES:
            enrichments = doc.get("enrichments") or {}
            category = classify_url(enrichments.get("host_url") or enrichments.get("source_host"))
        event_id = doc.get("event_id") or doc.get("_id")
        return cls(
            event_type=event_type,
            timestamp=when,
            device_id=doc.get("device_id"),
            target=target,
            indicators=tuple(doc.get("risk_indicators") or ()),
            file_count=int(doc.get("file_count") or 0),
            bytes=int(doc.get("bytes_transferred") or 0),
            web_category=category,
            event_id=str(event_id) if event_id is not None else None,
        )


@dataclass
class DailyActivity:
    """What one person did on one day, in the terms detectors reason about."""

    day: date
    events: list[EventView]
    logon_hours: list[int] = field(default_factory=list)
    logon_pcs: Counter = field(default_factory=Counter)
    failed_logons: int = 0
    usb_inserts: list[EventView] = field(default_factory=list)
    removable_copies: list[EventView] = field(default_factory=list)
    external_attachment_emails: int = 0
    uploads: list[EventView] = field(default_factory=list)
    downloads: list[EventView] = field(default_factory=list)
    web: dict[WebCategory, list[EventView]] = field(default_factory=dict)
    privilege_events: list[EventView] = field(default_factory=list)

    @classmethod
    def from_events(cls, day: date, events: list[EventView]) -> DailyActivity:
        events = sorted(events, key=lambda e: e.timestamp)
        a = cls(day=day, events=events)
        for ev in events:
            t = ev.event_type
            if t == LOGON:
                a.logon_hours.append(ev.hour)
                if ev.device_id:
                    a.logon_pcs[ev.device_id] += 1
            elif t == LOGON_FAILED:
                a.failed_logons += 1
            elif t == USB_INSERT:
                a.usb_inserts.append(ev)
            elif t in REMOVABLE_COPY_TYPES:
                a.removable_copies.append(ev)
            elif t == EXTERNAL_EMAIL and ev.file_count > 0:
                a.external_attachment_emails += 1
            if t in UPLOAD_TYPES:
                a.uploads.append(ev)
            if t in DOWNLOAD_TYPES:
                a.downloads.append(ev)
            if ev.web_category is not None:
                a.web.setdefault(ev.web_category, []).append(ev)
            if any(i in PRIVILEGE_INDICATORS for i in ev.indicators):
                a.privilege_events.append(ev)
        return a

    @property
    def active(self) -> bool:
        return bool(self.events)

    def web_count(self, category: WebCategory) -> int:
        return len(self.web.get(category, ()))


@dataclass
class Ewma:
    """Exponentially weighted mean and variance of a daily count."""

    mean: float = 0.0
    var: float = 0.0
    n: int = 0

    def update(self, value: float, alpha: float) -> None:
        if self.n == 0:
            self.mean, self.var = float(value), 0.0
        else:
            diff = value - self.mean
            increment = alpha * diff
            self.mean += increment
            self.var = (1 - alpha) * (self.var + diff * increment)
        self.n += 1

    def std(self, floor: float) -> float:
        return max(math.sqrt(max(self.var, 0.0)), floor)

    def zscore(self, value: float, floor: float = 1.0) -> float:
        return (value - self.mean) / self.std(floor)


@dataclass
class ActivityProfile:
    """
    A person's normal behaviour, learned over their active days.

    Counts use exponentially weighted averages so behaviour that changes
    gradually becomes the new normal, while sudden changes stand out.
    """

    alpha: float = 0.05  # ~ the last 20 active days dominate
    active_days: int = 0
    logon_hours: dict[int, float] = field(default_factory=dict)
    logon_total: float = 0.0
    pcs: dict[str, int] = field(default_factory=dict)
    days_with: dict[str, float] = field(default_factory=dict)  # EWMA share of days with >0
    counts: dict[str, Ewma] = field(default_factory=dict)
    last_day: date | None = None

    # ─── Reading ───────────────────────────────────────────

    def hour_share(self, hour: int) -> float:
        return self.logon_hours.get(hour, 0.0) / self.logon_total if self.logon_total else 0.0

    def usual_hours(self, coverage: float = 0.9) -> list[int]:
        """The smallest set of hours covering `coverage` of past logons."""
        if not self.logon_total:
            return []
        ranked = sorted(self.logon_hours.items(), key=lambda kv: -kv[1])
        hours, covered = [], 0.0
        for hour, weight in ranked:
            hours.append(hour)
            covered += weight
            if covered / self.logon_total >= coverage:
                break
        return sorted(hours)

    def usual_span(self, coverage: float = 0.95) -> tuple[int, int] | None:
        """
        Earliest and latest of the person's usual logon hours. Screen unlocks
        are recorded as logons, so anything inside this span is ordinary.
        (A night shift that wraps past midnight spans the whole day, so it is
        never judged by time of day — conservative rather than noisy.)
        """
        hours = self.usual_hours(coverage)
        return (min(hours), max(hours)) if hours else None

    def share_of_days_with(self, measure: str) -> float:
        return self.days_with.get(measure, 0.0)

    def stat(self, measure: str) -> Ewma:
        return self.counts.get(measure) or Ewma()

    def knows_pc(self, pc: str) -> bool:
        return pc in self.pcs

    # ─── Learning ──────────────────────────────────────────

    def update(self, activity: DailyActivity, extra: Mapping[str, float] | None = None) -> None:
        """
        Fold a finished day into the profile. Inactive days are skipped.
        `extra` carries measures that need organisation context (e.g. use of
        other people's machines), which the day's events alone can't tell.
        """
        if not activity.active:
            return
        decay = 1 - self.alpha
        for hour in list(self.logon_hours):
            self.logon_hours[hour] *= decay
        self.logon_total *= decay
        for hour in activity.logon_hours:
            self.logon_hours[hour] = self.logon_hours.get(hour, 0.0) + 1.0
            self.logon_total += 1.0
        for pc, n in activity.logon_pcs.items():
            self.pcs[pc] = self.pcs.get(pc, 0) + n

        for measure, value in {**measures(activity), **(extra or {})}.items():
            self.counts.setdefault(measure, Ewma()).update(value, self.alpha)
            previous = self.days_with.get(measure, 0.0) if self.active_days else float(value > 0)
            self.days_with[measure] = previous + self.alpha * (float(value > 0) - previous)
        self.active_days += 1
        self.last_day = activity.day


def measures(activity: DailyActivity) -> dict[str, float]:
    return {
        "failed_logons": activity.failed_logons,
        "usb_inserts": len(activity.usb_inserts),
        "removable_copies": len(activity.removable_copies),
        "executable_copies": sum(1 for e in activity.removable_copies if is_executable(e.target)),
        "external_attachment_emails": activity.external_attachment_emails,
        "uploads": len(activity.uploads),
        "downloads": len(activity.downloads),
        "cloud_storage": activity.web_count(WebCategory.CLOUD_STORAGE),
        "leak_site": activity.web_count(WebCategory.LEAK_SITE),
        "job_search": activity.web_count(WebCategory.JOB_SEARCH),
        "hacking_tools": activity.web_count(WebCategory.HACKING_TOOLS),
    }

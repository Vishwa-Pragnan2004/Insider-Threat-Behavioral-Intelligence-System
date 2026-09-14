"""
ITBIS — Detection Module: category detectors

One detector per anomaly category. Each looks at a person's day against their
own history (`ActivityProfile`) and either stays silent or returns a finding
explaining what stood out.

Detectors that judge "unusual for this person" stay silent until the profile
has enough history, so new starters aren't flagged just for being new.
Signals that are concerning for anyone (leak sites, hacking tools, privilege
grants, bursts of failed logons) don't wait.

Habits are learned, not assumed suspicious: someone who routinely uses other
people's machines (an IT administrator), copies executables or plugs in USB
drives is judged against that routine, and only a change stands out.

Severity is 0-100 on the same scale as the risk score. When several reasons
point at the same category on the same day they combine into one finding: the
strongest reason sets the severity and each extra reason adds a little.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.modules.detection.application.activity import (
    LOGON,
    PRIVILEGE_INDICATORS,
    ActivityProfile,
    DailyActivity,
    EventView,
    is_executable,
)
from app.modules.detection.application.web_categories import WebCategory, url_host
from app.modules.detection.domain.categories import AnomalyCategory
from app.modules.detection.domain.finding import Finding


@dataclass(frozen=True)
class DetectionSettings:
    #: History needed before "unusual for this person" judgements.
    min_active_days: int = 10
    min_active_days_for_hours: int = 20
    min_active_days_for_indicators: int = 30
    min_logons_for_hours: float = 10.0
    #: An hour holding less than this share of someone's past logons is rare for them…
    rare_hour_share: float = 0.02
    #: …and only counts when it also falls outside their usual span by this many hours.
    hour_margin: int = 1
    usual_span_coverage: float = 0.95
    failed_logon_burst: int = 5
    #: Something done on fewer than this share of active days isn't a habit.
    rare_usage_share: float = 0.05
    job_search_rare_share: float = 0.10
    spike_z: float = 3.0
    min_removable_copies: int = 5
    copy_rate_multiple: float = 2.5
    min_external_attachment_emails: int = 8
    min_uploads: int = 3
    min_downloads: int = 10
    combine_step: float = 5.0


@dataclass(frozen=True)
class DetectionContext:
    """Organisation-wide facts detectors can't learn from one person's history."""

    settings: DetectionSettings = field(default_factory=DetectionSettings)
    #: Dedicated machine -> the person it belongs to.
    pc_owners: Mapping[str, str] = field(default_factory=dict)
    #: Accounts with administrative rights (e.g. IT administrators).
    privileged_users: frozenset[str] = frozenset()
    source_dataset: str = "all"


# ─── Helpers ────────────────────────────────────────────────


@dataclass
class _Reasons:
    """Reasons accumulated for one category on one day."""

    items: list[tuple[float, str]] = field(default_factory=list)
    events: list[EventView] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def add(self, severity: float, reason: str, events: Sequence[EventView] = ()) -> None:
        self.items.append((severity, reason))
        self.events.extend(events)

    def severity(self, step: float) -> float:
        if not self.items:
            return 0.0
        ranked = sorted((s for s, _ in self.items), reverse=True)
        return min(100.0, ranked[0] + step * (len(ranked) - 1))

    def finding(
        self,
        *,
        user_id: str,
        day: date,
        category: AnomalyCategory,
        detector: str,
        title: str,
        context: DetectionContext,
    ) -> Finding | None:
        if not self.items:
            return None
        reasons = [reason for _, reason in sorted(self.items, key=lambda r: -r[0])]
        return Finding(
            user_id=user_id,
            day=datetime(day.year, day.month, day.day, tzinfo=UTC),
            category=category,
            detector=detector,
            severity=self.severity(context.settings.combine_step),
            title=title,
            description=" ".join(f"{r[0].upper()}{r[1:]}." for r in reasons),
            evidence={**self.evidence, "reasons": reasons},
            event_ids=[e.event_id for e in self.events if e.event_id][:20],
            source_dataset=context.source_dataset,
        )


def _times(events: Sequence[EventView], limit: int = 5) -> str:
    shown = ", ".join(e.timestamp.strftime("%H:%M") for e in events[:limit])
    return shown + (f" and {len(events) - limit} more" if len(events) > limit else "")


def _span_label(span: tuple[int, int] | None) -> str:
    return f"{span[0]:02d}:00–{span[1] + 1:02d}:00" if span else "unknown"


def _has_history(profile: ActivityProfile, days: int) -> bool:
    return profile.active_days >= days


def _outside_hours(profile: ActivityProfile, hour: int, s: DetectionSettings) -> bool:
    """A time of day this person essentially never works, given enough history."""
    if (
        profile.active_days < s.min_active_days_for_hours
        or profile.logon_total < s.min_logons_for_hours
    ):
        return False
    span = profile.usual_span(s.usual_span_coverage)
    if span is None or profile.hour_share(hour) >= s.rare_hour_share:
        return False
    return hour < span[0] - s.hour_margin or hour > span[1] + s.hour_margin


def _spike(profile: ActivityProfile, measure: str, value: int, minimum: int, z: float) -> bool:
    stat = profile.stat(measure)
    return value >= max(minimum, stat.mean + z * stat.std(1.0))


def _rarely(profile: ActivityProfile, measure: str, s: DetectionSettings) -> bool:
    return profile.share_of_days_with(measure) < s.rare_usage_share


def _foreign(owner_of: Mapping[str, str], user_id: str, pc: str | None) -> str | None:
    """The owner of `pc` if it is someone else's dedicated machine."""
    owner = owner_of.get(pc or "")
    return owner if owner and owner != user_id else None


def _new_foreign_machines(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> list[tuple[str, str]]:
    """(machine, owner) for other people's dedicated machines this person hasn't used before."""
    out = []
    for pc in day.logon_pcs:
        owner = _foreign(context.pc_owners, user_id, pc)
        if owner and not profile.knows_pc(pc):
            out.append((pc, owner))
    return out


def context_measures(
    user_id: str, day: DailyActivity, context: DetectionContext
) -> dict[str, float]:
    """Daily measures that need organisation context, for the profile to learn."""
    return {
        "foreign_logons": sum(
            1 for pc in day.logon_pcs if _foreign(context.pc_owners, user_id, pc)
        ),
        "foreign_usb": sum(
            1 for e in day.usb_inserts if _foreign(context.pc_owners, user_id, e.device_id)
        ),
    }


# ─── Access engine ──────────────────────────────────────────


def unusual_login_time(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> Finding | None:
    s = context.settings
    rare = [e for e in day.events if e.event_type == LOGON and _outside_hours(profile, e.hour, s)]
    if not rare:
        return None
    span = profile.usual_span(s.usual_span_coverage)
    reasons = _Reasons(
        evidence={
            "logon_times": [e.timestamp.strftime("%H:%M") for e in rare],
            "usual_span": _span_label(span),
            "history_days": profile.active_days,
        }
    )
    night = [e for e in rare if e.hour < 6]
    severity = min(70.0, 45.0 + 10.0 * (len(rare) - 1)) + (10.0 if night else 0.0)
    detail = f", {len(night)} of them between 00:00 and 06:00" if night else ""
    reasons.add(
        severity,
        f"logged on at {_times(rare)}, outside their usual working hours "
        f"({_span_label(span)}){detail}",
        rare,
    )
    return reasons.finding(
        user_id=user_id,
        day=day.day,
        category=AnomalyCategory.UNUSUAL_LOGIN_TIME,
        detector="unusual_login_time",
        title="Unusual login time",
        context=context,
    )


def unauthorized_access(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> Finding | None:
    s = context.settings
    reasons = _Reasons()
    failed = [e for e in day.events if e.event_type == "logon_failed"]
    if len(failed) >= s.failed_logon_burst or (
        len(failed) >= 3
        and _has_history(profile, s.min_active_days)
        and _spike(profile, "failed_logons", len(failed), 3, s.spike_z)
    ):
        reasons.add(
            min(85.0, 50.0 + 5.0 * max(0, len(failed) - s.failed_logon_burst)),
            f"{len(failed)} failed logon attempts",
            failed,
        )
        reasons.evidence["failed_logons"] = len(failed)

    if (
        user_id not in context.privileged_users
        and _has_history(profile, s.min_active_days)
        and _rarely(profile, "foreign_logons", s)
    ):
        foreign = _new_foreign_machines(user_id, day, profile, context)
        if foreign:
            listed = ", ".join(f"{pc} (assigned to {owner})" for pc, owner in foreign)
            machines = dict(foreign)
            events = [e for e in day.events if e.event_type == LOGON and e.device_id in machines]
            reasons.add(60.0, f"logged on to another person's dedicated machine: {listed}", events)
            reasons.evidence["foreign_machines"] = [pc for pc, _ in foreign]
    return reasons.finding(
        user_id=user_id,
        day=day.day,
        category=AnomalyCategory.UNAUTHORIZED_ACCESS_ATTEMPT,
        detector="unauthorized_access",
        title="Unauthorized access attempt",
        context=context,
    )


# ─── Data exfiltration engine ───────────────────────────────


def suspicious_device_usage(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> Finding | None:
    s = context.settings
    inserts = day.usb_inserts
    if not inserts or not _has_history(profile, s.min_active_days):
        return None
    reasons = _Reasons(evidence={"connections": len(inserts)})
    share = profile.share_of_days_with("usb_inserts")
    stat = profile.stat("usb_inserts")
    if share < s.rare_usage_share:
        reasons.add(
            55.0,
            f"connected removable media {len(inserts)} time(s); they used removable media "
            f"on only {share:.0%} of past active days",
            inserts,
        )
    elif _spike(profile, "usb_inserts", len(inserts), 3, s.spike_z):
        reasons.add(
            50.0,
            f"connected removable media {len(inserts)} times, against a usual "
            f"{stat.mean:.1f} per day",
            inserts,
        )
    foreign = [e for e in inserts if _foreign(context.pc_owners, user_id, e.device_id)]
    if foreign and _rarely(profile, "foreign_usb", s):
        owners = sorted({context.pc_owners.get(e.device_id or "", "?") for e in foreign})
        reasons.add(55.0, f"removable media connected to a machine assigned to {', '.join(owners)}")
    if not reasons.items:
        # A regular USB user plugging in at an odd hour isn't device misuse on
        # its own; the login-time detector already covers the odd hour.
        return None
    after_hours = [e for e in inserts if _outside_hours(profile, e.hour, s)]
    if after_hours:
        reasons.add(50.0, f"removable media connected at unusual hours ({_times(after_hours)})")
    return reasons.finding(
        user_id=user_id,
        day=day.day,
        category=AnomalyCategory.SUSPICIOUS_DEVICE_USAGE,
        detector="suspicious_device_usage",
        title="Suspicious device usage",
        context=context,
    )


def excessive_file_transfer(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> Finding | None:
    s = context.settings
    if not _has_history(profile, s.min_active_days):
        return None
    reasons = _Reasons()
    copies = day.removable_copies
    if copies:
        stat = profile.stat("removable_copies")
        # Markedly higher than usual: well past normal variation and several
        # times the person's usual rate.
        threshold = max(
            s.min_removable_copies,
            stat.mean + s.spike_z * stat.std(1.0),
            s.copy_rate_multiple * stat.mean,
        )
        if len(copies) >= threshold:
            severity = 50.0 + min(35.0, 15.0 * math.log2(len(copies) / threshold + 1))
            reasons.add(
                severity,
                f"copied {len(copies)} files to removable media, against a usual "
                f"{stat.mean:.1f} per day",
                copies,
            )
        elif stat.mean < 0.1 and len(copies) >= 3:
            reasons.add(
                50.0, f"copied {len(copies)} files to removable media for the first time", copies
            )
        executables = [e for e in copies if is_executable(e.target)]
        if executables and _rarely(profile, "executable_copies", s):
            names = ", ".join(sorted({(e.target or "")[-40:] for e in executables})[:3])
            reasons.add(55.0, f"copied executable files to removable media ({names})", executables)
        reasons.evidence["removable_copies"] = len(copies)
        reasons.evidence["usual_per_day"] = round(stat.mean, 2)

    n = day.external_attachment_emails
    if n and _spike(
        profile, "external_attachment_emails", n, s.min_external_attachment_emails, s.spike_z
    ):
        stat = profile.stat("external_attachment_emails")
        reasons.add(
            50.0,
            f"sent {n} emails with attachments outside the organisation, against a usual "
            f"{stat.mean:.1f} per day",
        )
        reasons.evidence["external_attachment_emails"] = n
    return reasons.finding(
        user_id=user_id,
        day=day.day,
        category=AnomalyCategory.EXCESSIVE_FILE_TRANSFER,
        detector="excessive_file_transfer",
        title="Excessive file transfers",
        context=context,
    )


def abnormal_data_download(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> Finding | None:
    s = context.settings
    reasons = _Reasons()
    leaks = day.web.get(WebCategory.LEAK_SITE, [])
    if leaks:
        hosts = sorted({url_host(e.target) or "?" for e in leaks})
        reasons.add(80.0, f"visited leak site(s) {', '.join(hosts)} {len(leaks)} time(s)", leaks)
        reasons.evidence["leak_sites"] = hosts

    history = _has_history(profile, s.min_active_days)
    cloud = day.web.get(WebCategory.CLOUD_STORAGE, [])
    if cloud and history and _rarely(profile, "cloud_storage", s):
        hosts = sorted({url_host(e.target) or "?" for e in cloud})
        reasons.add(
            55.0, f"used personal cloud storage ({', '.join(hosts)}), which they rarely do", cloud
        )
    if (
        day.uploads
        and history
        and _spike(profile, "uploads", len(day.uploads), s.min_uploads, s.spike_z)
    ):
        stat = profile.stat("uploads")
        reasons.add(
            55.0,
            f"uploaded {len(day.uploads)} times, against a usual {stat.mean:.1f} per day",
            day.uploads,
        )
    if (
        day.downloads
        and history
        and _spike(profile, "downloads", len(day.downloads), s.min_downloads, s.spike_z)
    ):
        stat = profile.stat("downloads")
        reasons.add(
            45.0,
            f"downloaded {len(day.downloads)} files, against a usual {stat.mean:.1f} per day",
            day.downloads,
        )
    return reasons.finding(
        user_id=user_id,
        day=day.day,
        category=AnomalyCategory.ABNORMAL_DATA_DOWNLOAD,
        detector="abnormal_data_download",
        title="Abnormal data download / upload",
        context=context,
    )


# ─── Privilege abuse engine ─────────────────────────────────


def privilege_abuse(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> Finding | None:
    s = context.settings
    privileged = user_id in context.privileged_users
    reasons = _Reasons(evidence={"privileged_account": privileged})
    for ev in day.privilege_events:
        for indicator in ev.indicators:
            if indicator in PRIVILEGE_INDICATORS:
                severity = PRIVILEGE_INDICATORS[indicator]
                if _outside_hours(profile, ev.hour, s):
                    severity += 10.0
                reasons.add(
                    severity,
                    f"{indicator.replace('_', ' ')} ({ev.target or 'unknown target'}) "
                    f"at {ev.timestamp:%H:%M}",
                    [ev],
                )
    tools = day.web.get(WebCategory.HACKING_TOOLS, [])
    if tools:
        hosts = sorted({url_host(e.target) or "?" for e in tools})
        reasons.add(
            85.0 if privileged else 70.0,
            f"browsed keylogger / monitoring-tool sites ({', '.join(hosts[:4])})",
            tools,
        )
        reasons.evidence["tool_sites"] = hosts
    if privileged and _has_history(profile, s.min_active_days):
        # Administrators use other people's machines as part of the job. It
        # stands out when they don't normally, or when it happens outside
        # their working hours.
        routine = not _rarely(profile, "foreign_logons", s)
        logons = {e.device_id: e for e in day.events if e.event_type == LOGON and e.device_id}
        suspicious = [
            (pc, owner)
            for pc, owner in _new_foreign_machines(user_id, day, profile, context)
            if not routine or _outside_hours(profile, logons[pc].hour, s)
        ]
        if suspicious:
            listed = ", ".join(f"{pc} (assigned to {owner})" for pc, owner in suspicious)
            when = "outside their working hours " if routine else ""
            reasons.add(
                75.0, f"administrator account logged on {when}to another person's machine: {listed}"
            )
            reasons.evidence["foreign_machines"] = [pc for pc, _ in suspicious]
    return reasons.finding(
        user_id=user_id,
        day=day.day,
        category=AnomalyCategory.PRIVILEGE_ABUSE,
        detector="privilege_abuse",
        title="Privilege abuse",
        context=context,
    )


# ─── Behavioral engine: indicators ──────────────────────────


def insider_risk_indicators(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> Finding | None:
    s = context.settings
    jobs = day.web.get(WebCategory.JOB_SEARCH, [])
    if not jobs or not _has_history(profile, s.min_active_days_for_indicators):
        return None
    if profile.share_of_days_with("job_search") >= s.job_search_rare_share:
        return None
    reasons = _Reasons(evidence={"job_site_visits": len(jobs)})
    hosts = sorted({url_host(e.target) or "?" for e in jobs})
    reasons.add(
        min(50.0, 35.0 + len(jobs)),
        f"visited job-search sites {len(jobs)} time(s) ({', '.join(hosts[:4])}), "
        "which they rarely do",
        jobs,
    )
    return reasons.finding(
        user_id=user_id,
        day=day.day,
        category=AnomalyCategory.INSIDER_RISK_INDICATOR,
        detector="insider_risk_indicators",
        title="Job-search activity",
        context=context,
    )


DETECTORS = (
    unusual_login_time,
    unauthorized_access,
    suspicious_device_usage,
    excessive_file_transfer,
    abnormal_data_download,
    privilege_abuse,
    insider_risk_indicators,
)


def detect(
    user_id: str, day: DailyActivity, profile: ActivityProfile, context: DetectionContext
) -> list[Finding]:
    if not day.active:
        return []
    return [f for f in (d(user_id, day, profile, context) for d in DETECTORS) if f is not None]


class UserTimeline:
    """
    Walks one person's days in order: judge each day against the history so
    far, then learn from it. Judging before learning means a day is never
    compared with itself.
    """

    def __init__(
        self, user_id: str, context: DetectionContext, profile: ActivityProfile | None = None
    ) -> None:
        self.user_id = user_id
        self.context = context
        self.profile = profile or ActivityProfile()

    def process_day(
        self, day: date, events: list[EventView]
    ) -> tuple[DailyActivity, list[Finding]]:
        activity = DailyActivity.from_events(day, events)
        findings = detect(self.user_id, activity, self.profile, self.context)
        self.profile.update(activity, context_measures(self.user_id, activity, self.context))
        return activity, findings

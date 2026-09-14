"""
ITBIS — Unit tests: category detectors, activity profiles and web categories.

Each detector is exercised on a person with a stable, ordinary history and
then a day that departs from it the way the CERT scenarios describe.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.detection.application.activity import (
    ActivityProfile,
    DailyActivity,
    EventView,
    Ewma,
)
from app.modules.detection.application.detectors import (
    DetectionContext,
    UserTimeline,
    detect,
)
from app.modules.detection.application.web_categories import WebCategory, classify_url
from app.modules.detection.domain.categories import AnomalyCategory, DetectionEngine

USER = "ACM2278"
START = date(2010, 3, 1)


def _ev(day: date, hour: int, event_type: str, minute: int = 0, **extra) -> EventView:
    return EventView(
        event_type=event_type,
        timestamp=datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC),
        device_id=extra.pop("device_id", "PC-1"),
        event_id=f"{event_type}-{day}-{hour}-{minute}",
        **extra,
    )


def _ordinary_day(
    day: date, *, usb: int = 0, copies: int = 0, jobs: bool = False
) -> list[EventView]:
    events = [_ev(day, 8, "logon", 55), _ev(day, 12, "logon", 30), _ev(day, 17, "logoff")]
    events += [
        _ev(day, 9 + i % 7, "http_request", i, target=f"http://news.example.com/{i}")
        for i in range(10)
    ]
    events += [_ev(day, 10, "usb_insert", i) for i in range(usb)]
    events += [_ev(day, 11, "file_copy", i, target=f"report{i}.doc") for i in range(copies)]
    if jobs:
        events.append(_ev(day, 13, "http_request", target="http://monster.com/jobs/1"))
    return events


def _timeline(days: int = 30, context: DetectionContext | None = None, **ordinary) -> UserTimeline:
    timeline = UserTimeline(USER, context or DetectionContext())
    for offset in range(days):
        day = START + timedelta(days=offset)
        _, findings = timeline.process_day(day, _ordinary_day(day, **ordinary))
        assert findings == [], f"ordinary day {day} raised {findings}"
    return timeline


def _judge(timeline: UserTimeline, events: list[EventView]):
    day = START + timedelta(days=timeline.profile.active_days)
    events = [
        EventView(
            **{
                **{s: getattr(e, s) for s in EventView.__slots__},
                "timestamp": e.timestamp.replace(year=day.year, month=day.month, day=day.day),
            }
        )
        for e in events
    ]
    _, findings = timeline.process_day(day, events)
    return {f.category: f for f in findings}, day


BASE = date(2000, 1, 1)  # placeholder day; _judge moves events onto the next day


# ─── Quiet by default ───────────────────────────────────────


def test_a_stable_routine_raises_nothing():
    timeline = _timeline(45, usb=1, copies=2)
    assert timeline.profile.active_days == 45


def test_new_starters_are_not_judged_on_personal_history():
    timeline = UserTimeline(USER, DetectionContext())
    _, findings = timeline.process_day(START, [_ev(START, 2, "logon"), _ev(START, 2, "usb_insert")])
    assert findings == []


# ─── Access engine ──────────────────────────────────────────


def test_after_hours_logons_by_a_day_worker():
    """CERT scenario 1: someone who never worked after hours starts logging on at night."""
    found, _ = _judge(_timeline(), [_ev(BASE, 1, "logon", 34), _ev(BASE, 2, "logon", 10)])

    finding = found[AnomalyCategory.UNUSUAL_LOGIN_TIME]
    assert finding.engine == DetectionEngine.ACCESS
    assert finding.severity == 65.0  # 55 for two rare logons, +10 for the night hours
    assert finding.evidence["logon_times"] == ["01:34", "02:10"]
    assert "outside their usual working hours" in finding.description


def test_failed_logon_burst_is_flagged_even_without_history():
    timeline = UserTimeline(USER, DetectionContext())
    _, findings = timeline.process_day(START, [_ev(START, 9, "logon_failed", m) for m in range(7)])
    [finding] = findings
    assert finding.category == AnomalyCategory.UNAUTHORIZED_ACCESS_ATTEMPT
    assert finding.severity == 60.0


def test_logon_to_a_colleagues_dedicated_machine():
    context = DetectionContext(pc_owners={"PC-1": USER, "PC-9": "FAW0032"})
    found, _ = _judge(_timeline(context=context), [_ev(BASE, 10, "logon", device_id="PC-9")])
    finding = found[AnomalyCategory.UNAUTHORIZED_ACCESS_ATTEMPT]
    assert "PC-9 (assigned to FAW0032)" in finding.description


def test_administrator_on_a_colleagues_machine_is_privilege_abuse():
    """CERT scenario 3: an IT admin logs on to his supervisor's machine."""
    context = DetectionContext(
        pc_owners={"PC-1": USER, "PC-9": "FAW0032"}, privileged_users=frozenset({USER})
    )
    found, _ = _judge(_timeline(context=context), [_ev(BASE, 19, "logon", device_id="PC-9")])
    assert AnomalyCategory.UNAUTHORIZED_ACCESS_ATTEMPT not in found
    assert found[AnomalyCategory.PRIVILEGE_ABUSE].severity >= 75.0


# ─── Data exfiltration engine ───────────────────────────────


def test_first_time_removable_media_use():
    found, _ = _judge(_timeline(), [_ev(BASE, 10, "logon"), _ev(BASE, 10, "usb_insert", 5)])
    finding = found[AnomalyCategory.SUSPICIOUS_DEVICE_USAGE]
    assert finding.engine == DetectionEngine.DATA_EXFILTRATION
    assert "only 0% of past active days" in finding.description


def test_a_regular_usb_user_is_left_alone():
    found, _ = _judge(_timeline(usb=1), [_ev(BASE, 10, "logon"), _ev(BASE, 11, "usb_insert")])
    assert AnomalyCategory.SUSPICIOUS_DEVICE_USAGE not in found


def test_markedly_higher_file_copying():
    """CERT scenario 2: thumb-drive copying far above the person's normal rate."""
    found, _ = _judge(
        _timeline(copies=2),
        [_ev(BASE, 10, "logon")]
        + [_ev(BASE, 14, "file_copy", m, target=f"f{m}.pdf") for m in range(40)],
    )
    finding = found[AnomalyCategory.EXCESSIVE_FILE_TRANSFER]
    assert finding.evidence["removable_copies"] == 40
    assert finding.severity > 60.0


def test_executable_copied_to_removable_media():
    found, _ = _judge(
        _timeline(copies=1),
        [_ev(BASE, 14, "file_copy", target="GGX5KL22.exe")],
    )
    assert "executable" in found[AnomalyCategory.EXCESSIVE_FILE_TRANSFER].description


def test_leak_site_visit():
    timeline = UserTimeline(USER, DetectionContext())
    events = [_ev(START, 1, "http_request", target="http://wikileaks.org/submit/1")]
    events = [
        EventView(
            **{
                **{s: getattr(e, s) for s in EventView.__slots__},
                "web_category": classify_url(e.target),
            }
        )
        for e in events
    ]
    _, findings = timeline.process_day(START, events)
    [finding] = findings
    assert finding.category == AnomalyCategory.ABNORMAL_DATA_DOWNLOAD
    assert finding.severity == 80.0
    assert finding.evidence["leak_sites"] == ["wikileaks.org"]


# ─── Privilege abuse & indicators ───────────────────────────


def test_privileged_group_grant_from_agent_telemetry():
    doc = {
        "event_type": "privilege_change",
        "timestamp": "2026-09-14T03:12:00Z",
        "target_resource": "BUILTIN\\Administrators",
        "risk_indicators": ["privileged_group_member_added"],
    }
    timeline = UserTimeline(USER, DetectionContext())
    _, findings = timeline.process_day(date(2026, 9, 14), [EventView.from_doc(doc)])
    [finding] = findings
    assert finding.category == AnomalyCategory.PRIVILEGE_ABUSE
    assert finding.severity == 70.0


def test_keylogger_site_is_privilege_abuse_and_worse_for_admins():
    doc = {
        "event_type": "http_request",
        "timestamp": "2010-08-12T13:42:15",
        "target_resource": "http://www.dailykeylogger.com/wetest/x.html",
    }
    admin = DetectionContext(privileged_users=frozenset({USER}))
    _, as_admin = UserTimeline(USER, admin).process_day(
        date(2010, 8, 12), [EventView.from_doc(doc)]
    )
    _, as_user = UserTimeline(USER, DetectionContext()).process_day(
        date(2010, 8, 12), [EventView.from_doc(doc)]
    )
    assert as_admin[0].severity == 85.0 and as_user[0].severity == 70.0


def test_job_search_is_a_low_severity_indicator_only_when_new():
    found, _ = _judge(
        _timeline(),
        [
            EventView(
                **{
                    **{s: getattr(e, s) for s in EventView.__slots__},
                    "web_category": WebCategory.JOB_SEARCH,
                }
            )
            for e in [
                _ev(BASE, 13, "http_request", m, target="http://monster.com/x") for m in range(6)
            ]
        ],
    )
    finding = found[AnomalyCategory.INSIDER_RISK_INDICATOR]
    assert finding.engine == DetectionEngine.BEHAVIORAL
    assert finding.severity == 41.0
    found_again, _ = _judge(_timeline(jobs=True), [_ev(BASE, 13, "http_request", target="x")])
    assert AnomalyCategory.INSIDER_RISK_INDICATOR not in found_again


# ─── Building blocks ────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "category"),
    [
        ("http://wikileaks.org/Julian_Assange/x", WebCategory.LEAK_SITE),
        ("https://www.dropbox.com/s/abc", WebCategory.CLOUD_STORAGE),
        ("http://jobhuntersbible.com/a.aspx", WebCategory.JOB_SEARCH),
        ("https://www.linkedin.com/jobs/view/1", WebCategory.JOB_SEARCH),
        ("http://keylogpc.com/download", WebCategory.HACKING_TOOLS),
        ("http://msn.com/news", None),
        ("", None),
    ],
)
def test_web_categories(url, category):
    assert classify_url(url) == category


def test_findings_are_identified_by_person_day_and_detector():
    timeline = UserTimeline(USER, DetectionContext())
    events = [_ev(START, 9, "logon_failed", m) for m in range(6)]
    _, first = timeline.process_day(START, events)
    _, again = UserTimeline(USER, DetectionContext()).process_day(START, events)
    assert first[0].id == again[0].id
    assert first[0].key == f"{USER}|{START.isoformat()}|unauthorized_access"


def test_profile_learns_hours_and_ignores_inactive_days():
    profile = ActivityProfile()
    profile.update(DailyActivity.from_events(START, []))
    assert profile.active_days == 0
    for offset in range(20):
        day = START + timedelta(days=offset)
        profile.update(DailyActivity.from_events(day, _ordinary_day(day)))
    assert profile.usual_hours() == [8, 12]
    assert profile.hour_share(2) == 0.0


def test_ewma_tracks_mean_and_spread():
    stat = Ewma()
    for value in [2, 2, 2, 2, 2]:
        stat.update(value, 0.2)
    assert stat.mean == pytest.approx(2.0) and stat.std(1.0) == 1.0
    assert stat.zscore(12, 1.0) == pytest.approx(10.0)


def test_detect_skips_days_without_activity():
    assert (
        detect(USER, DailyActivity.from_events(START, []), ActivityProfile(), DetectionContext())
        == []
    )


# ─── Routine is learned, not flagged ────────────────────────


def _admin_routine(days: int = 30) -> tuple[UserTimeline, DetectionContext]:
    """An IT administrator who logs on to a different colleague's machine most days."""
    owners = {f"PC-{i}": f"EMP{i:04d}" for i in range(2, 60)}
    owners["PC-1"] = USER
    context = DetectionContext(pc_owners=owners, privileged_users=frozenset({USER}))
    timeline = UserTimeline(USER, context)
    for offset in range(days):
        day = START + timedelta(days=offset)
        events = _ordinary_day(day) + [_ev(day, 10, "logon", 15, device_id=f"PC-{offset + 2}")]
        _, findings = timeline.process_day(day, events)
        assert findings == [], findings
    return timeline, context


def test_an_administrators_routine_visits_to_other_machines_are_not_flagged():
    timeline, _ = _admin_routine()
    found, _ = _judge(timeline, [_ev(BASE, 11, "logon", device_id="PC-55")])
    assert found == {}


def test_but_an_administrator_on_a_colleagues_machine_out_of_hours_is():
    timeline, _ = _admin_routine()
    found, _ = _judge(timeline, [_ev(BASE, 19, "logon", 8, device_id="PC-55")])
    finding = found[AnomalyCategory.PRIVILEGE_ABUSE]
    assert "outside their working hours" in finding.description


def test_screen_unlocks_inside_the_working_day_are_ordinary():
    found, _ = _judge(_timeline(), [_ev(BASE, 10, "logon", 7), _ev(BASE, 13, "logon", 40)])
    assert AnomalyCategory.UNUSUAL_LOGIN_TIME not in found


def test_login_time_waits_for_enough_history():
    found, _ = _judge(_timeline(days=15), [_ev(BASE, 2, "logon")])
    assert AnomalyCategory.UNUSUAL_LOGIN_TIME not in found


def test_someone_who_routinely_copies_executables_is_not_flagged_for_it():
    timeline = UserTimeline(USER, DetectionContext())
    for offset in range(30):
        day = START + timedelta(days=offset)
        events = _ordinary_day(day) + [_ev(day, 11, "file_copy", target="tool.exe")]
        timeline.process_day(day, events)
    found, _ = _judge(timeline, [_ev(BASE, 11, "file_copy", target="setup.exe")])
    assert AnomalyCategory.EXCESSIVE_FILE_TRANSFER not in found

"""
ITBIS — CERT Insider Threat Test Dataset (r4.2): streaming readers

Reads the dataset without loading it: every log is strictly time-ordered, so
the five logs are merged into one chronological stream and handed out one day
at a time. Rows are mapped to the same event types and fields the ingestion
parsers store, so a replay exercises exactly the code live data goes through.

    logon.csv    Logon / Logoff                        -> logon / logoff
    device.csv   Connect / Disconnect (thumb drive)    -> usb_insert / usb_remove
    file.csv     a file copied to removable media      -> file_copy
    email.csv    sent email; external if any recipient
                 is outside the organisation            -> email_external / email_sent
    http.csv     a web page visit                       -> http_request

Also here: the LDAP employee directory (roles, departments, supervisors), each
dedicated machine's owner (inferred from who logs on to it), and the red-team
answer key used to label malicious user-days.

Timestamps in CERT carry no time zone; they are treated as UTC throughout.
"""

from __future__ import annotations

import csv
import heapq
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from app.modules.detection.application.activity import EventView
from app.modules.detection.application.web_categories import classify_url

ORGANISATION_DOMAIN = "dtaa.com"
LOG_FILES = ("logon.csv", "device.csv", "file.csv", "email.csv", "http.csv")
PRIVILEGED_ROLES = frozenset({"ITAdmin"})

# Content columns can be very long.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def parse_time(value: str) -> datetime:
    """'MM/DD/YYYY HH:MM:SS' -> aware UTC datetime (sliced, not strptime: it's hot)."""
    return datetime(
        int(value[6:10]),
        int(value[0:2]),
        int(value[3:5]),
        int(value[11:13]),
        int(value[14:16]),
        int(value[17:19]),
        tzinfo=UTC,
    )


@dataclass(slots=True)
class CertEvent:
    timestamp: datetime
    user_id: str
    event_type: str
    device_id: str | None = None
    target: str | None = None
    file_count: int = 0
    bytes: int = 0
    indicators: tuple[str, ...] = ()
    raw_id: str | None = None

    def as_doc(self) -> dict:
        """The stored canonical-event shape the feature aggregator reads."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "device_id": self.device_id,
            "target_resource": self.target,
            "risk_indicators": list(self.indicators),
            "file_count": self.file_count,
        }

    def as_view(self) -> EventView:
        return EventView(
            event_type=self.event_type,
            timestamp=self.timestamp,
            device_id=self.device_id,
            target=self.target,
            indicators=self.indicators,
            file_count=self.file_count,
            bytes=self.bytes,
            web_category=classify_url(self.target) if self.event_type == "http_request" else None,
            event_id=self.raw_id,
        )


def _rows(path: Path) -> Iterator[list[str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        yield from reader


def _int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def read_logon(path: Path) -> Iterator[CertEvent]:
    for row in _rows(path):
        event_type = "logon" if row[4].strip().lower() == "logon" else "logoff"
        yield CertEvent(parse_time(row[1]), row[2], event_type, row[3], raw_id=row[0])


def read_device(path: Path) -> Iterator[CertEvent]:
    for row in _rows(path):
        event_type = "usb_insert" if row[4].strip().lower() == "connect" else "usb_remove"
        yield CertEvent(parse_time(row[1]), row[2], event_type, row[3], raw_id=row[0])


def read_file(path: Path) -> Iterator[CertEvent]:
    for row in _rows(path):
        yield CertEvent(
            parse_time(row[1]),
            row[2],
            "file_copy",
            row[3],
            target=row[4],
            file_count=1,
            indicators=("file_copied_to_removable_media",),
            raw_id=row[0],
        )


def is_external(recipients: Iterable[str]) -> bool:
    return any(
        "@" in r and not r.strip().lower().endswith("@" + ORGANISATION_DOMAIN) for r in recipients
    )


def read_email(path: Path) -> Iterator[CertEvent]:
    for row in _rows(path):
        recipients = [a for col in (row[4], row[5], row[6]) for a in col.split(";") if a]
        external = is_external(recipients)
        attachments = _int(row[9])
        indicators = (("external_email",) if external else ()) + (
            ("has_attachments",) if attachments else ()
        )
        yield CertEvent(
            parse_time(row[1]),
            row[2],
            "email_external" if external else "email_sent",
            row[3],
            target=row[4],
            file_count=attachments,
            bytes=_int(row[8]),
            indicators=indicators,
            raw_id=row[0],
        )


def read_http(path: Path) -> Iterator[CertEvent]:
    for row in _rows(path):
        yield CertEvent(
            parse_time(row[1]), row[2], "http_request", row[3], target=row[4], raw_id=row[0]
        )


READERS = {
    "logon.csv": read_logon,
    "device.csv": read_device,
    "file.csv": read_file,
    "email.csv": read_email,
    "http.csv": read_http,
}


def merged_events(cert_dir: Path, logs: Iterable[str] = LOG_FILES) -> Iterator[CertEvent]:
    streams = [READERS[name](cert_dir / name) for name in logs if (cert_dir / name).exists()]
    return heapq.merge(*streams, key=lambda e: e.timestamp)


def by_day(
    events: Iterable[CertEvent], *, start: date | None = None, end: date | None = None
) -> Iterator[tuple[date, dict[str, list[CertEvent]]]]:
    """(day, {user: events}) for each day in [start, end), in order."""
    current: date | None = None
    users: dict[str, list[CertEvent]] = defaultdict(list)
    for event in events:
        day = event.timestamp.date()
        if start and day < start:
            continue
        if end and day >= end:
            break
        if day != current:
            if current is not None:
                yield current, users
            current, users = day, defaultdict(list)
        users[event.user_id].append(event)
    if current is not None:
        yield current, users


# ─── Organisation ───────────────────────────────────────────


@dataclass
class Employee:
    user_id: str
    name: str
    email: str
    role: str
    department: str
    team: str
    supervisor: str
    first_month: str
    last_month: str


def load_ldap(ldap_dir: Path) -> dict[str, Employee]:
    """The directory across all monthly snapshots; the latest snapshot wins."""
    employees: dict[str, Employee] = {}
    for path in sorted(ldap_dir.glob("*.csv")):
        month = path.stem
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                uid = row["user_id"]
                first = employees[uid].first_month if uid in employees else month
                employees[uid] = Employee(
                    user_id=uid,
                    name=row["employee_name"],
                    email=row["email"],
                    role=row["role"],
                    department=row.get("department", ""),
                    team=row.get("team", ""),
                    supervisor=row.get("supervisor", ""),
                    first_month=first,
                    last_month=month,
                )
    return employees


def privileged_users(employees: dict[str, Employee]) -> frozenset[str]:
    return frozenset(uid for uid, e in employees.items() if e.role in PRIVILEGED_ROLES)


def assigned_machines(
    logon_path: Path, *, min_share: float = 0.5, min_logons: int = 20
) -> dict[str, str]:
    """
    Each dedicated machine's owner: the person with most of its logons.

    The dataset gives everyone an assigned PC plus ~100 shared lab machines.
    A machine counts as dedicated when one person holds at least `min_share`
    of its logons; shared machines have no single owner and are left out.
    (This is organisational inventory, the kind an asset register supplies.)
    """
    per_pc: dict[str, Counter] = defaultdict(Counter)
    for event in read_logon(logon_path):
        if event.event_type == "logon" and event.device_id:
            per_pc[event.device_id][event.user_id] += 1
    owners = {}
    for pc, counts in per_pc.items():
        total = sum(counts.values())
        user, top = counts.most_common(1)[0]
        if total >= min_logons and top / total >= min_share:
            owners[pc] = user
    return owners


# ─── Answer key ─────────────────────────────────────────────


@dataclass
class Insider:
    user_id: str
    scenario: int
    start: datetime
    end: datetime
    malicious_days: set[date] = field(default_factory=set)


def load_insiders(answers_dir: Path, release: str = "4.2") -> dict[str, Insider]:
    """
    Red-team insiders of one release, with the days of their own malicious
    activity (rows logged under the insider's account in their answer file).
    """
    insiders: dict[str, Insider] = {}
    with (answers_dir / "insiders.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["dataset"].strip() != release:
                continue
            scenario = int(row["scenario"])
            user = row["user"].strip()
            insider = Insider(
                user_id=user,
                scenario=scenario,
                start=parse_time(_normalise_answer_time(row["start"])),
                end=parse_time(_normalise_answer_time(row["end"])),
            )
            detail = answers_dir / f"r{release}-{scenario}" / row["details"].strip()
            if detail.exists():
                with detail.open(newline="", encoding="utf-8", errors="replace") as dfh:
                    for record in csv.reader(dfh):
                        if len(record) > 3 and record[3] == user:
                            insider.malicious_days.add(
                                parse_time(_normalise_answer_time(record[2])).date()
                            )
            insiders[user] = insider
    return insiders


def _normalise_answer_time(value: str) -> str:
    """insiders.csv writes '3/6/2010 1:41:56' without padding; logs pad it."""
    value = value.strip()
    day_part, _, time_part = value.partition(" ")
    month, dom, year = day_part.split("/")
    hh, mm, ss = (time_part or "0:0:0").split(":")
    return f"{int(month):02d}/{int(dom):02d}/{year} {int(hh):02d}:{int(mm):02d}:{int(ss):02d}"

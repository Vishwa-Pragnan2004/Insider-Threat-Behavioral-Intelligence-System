"""
ITBIS — Unit tests: CERT r4.2 readers, answer key and replay pass A (tiny fixture dataset).
"""

from __future__ import annotations

import csv
import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from evaluation.cert.cert_io import (
    assigned_machines,
    by_day,
    is_external,
    load_insiders,
    load_ldap,
    merged_events,
    parse_time,
    privileged_users,
)
from evaluation.cert.replay import replay

START = datetime(2010, 1, 4, tzinfo=UTC)


def _stamp(when: datetime) -> str:
    return when.strftime("%m/%d/%Y %H:%M:%S")


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    """Three weeks of two office workers; on the last day AAA0001 misbehaves."""
    cert = tmp_path / "r4.2"
    logon, device, file_rows, email, http = [], [], [], [], []
    n = 0
    for offset in range(21):
        day = START + timedelta(days=offset)
        for user, pc in (("AAA0001", "PC-1"), ("BBB0002", "PC-2")):
            n += 1
            logon.append([f"{{L{n}}}", _stamp(day.replace(hour=8, minute=50)), user, pc, "Logon"])
            logon.append([f"{{O{n}}}", _stamp(day.replace(hour=17)), user, pc, "Logoff"])
            http.append(
                [
                    f"{{H{n}}}",
                    _stamp(day.replace(hour=10)),
                    user,
                    pc,
                    "http://news.example.com/a",
                    "words",
                ]
            )
            email.append(
                [
                    f"{{E{n}}}",
                    _stamp(day.replace(hour=11)),
                    user,
                    pc,
                    "Colleague@dtaa.com",
                    "",
                    "",
                    f"{user}@dtaa.com",
                    "2000",
                    "0",
                    "hi",
                ]
            )
    bad = START + timedelta(days=21)
    logon.append(["{BAD1}", _stamp(bad.replace(hour=1, minute=30)), "AAA0001", "PC-2", "Logon"])
    device.append(["{BAD2}", _stamp(bad.replace(hour=1, minute=35)), "AAA0001", "PC-2", "Connect"])
    http.append(
        [
            "{BAD3}",
            _stamp(bad.replace(hour=1, minute=40)),
            "AAA0001",
            "PC-2",
            "http://wikileaks.org/leak/1",
            "leak",
        ]
    )
    email.append(
        [
            "{BAD4}",
            _stamp(bad.replace(hour=1, minute=45)),
            "AAA0001",
            "PC-2",
            "someone@gmail.com",
            "",
            "",
            "AAA0001@dtaa.com",
            "9000",
            "2",
            "files",
        ]
    )

    _write(cert / "logon.csv", ["id", "date", "user", "pc", "activity"], logon)
    _write(cert / "device.csv", ["id", "date", "user", "pc", "activity"], device)
    _write(cert / "file.csv", ["id", "date", "user", "pc", "filename", "content"], file_rows)
    _write(
        cert / "email.csv",
        ["id", "date", "user", "pc", "to", "cc", "bcc", "from", "size", "attachments", "content"],
        email,
    )
    _write(cert / "http.csv", ["id", "date", "user", "pc", "url", "content"], http)
    ldap_header = [
        "employee_name",
        "user_id",
        "email",
        "role",
        "business_unit",
        "functional_unit",
        "department",
        "team",
        "supervisor",
    ]
    _write(
        cert / "LDAP" / "2010-01.csv",
        ldap_header,
        [
            ["Ann A", "AAA0001", "ann@dtaa.com", "ITAdmin", "1", "IT", "Ops", "Infra", "Bob B"],
            ["Bob B", "BBB0002", "bob@dtaa.com", "Manager", "1", "IT", "Ops", "Infra", ""],
        ],
    )

    answers = tmp_path / "answers"
    _write(
        answers / "insiders.csv",
        ["dataset", "scenario", "details", "user", "start", "end"],
        [
            ["4.2", "3", "r4.2-3-AAA0001.csv", "AAA0001", "1/25/2010 1:30:00", "1/25/2010 1:45:00"],
            ["2", "1", "r2.csv", "ZZZ0000", "3/6/2010 1:41:56", "3/20/2010 8:10:12"],
        ],
    )
    detail = answers / "r4.2-3" / "r4.2-3-AAA0001.csv"
    detail.parent.mkdir(parents=True)
    detail.write_text(
        f"logon,{{BAD1}},{_stamp(bad.replace(hour=1, minute=30))},AAA0001,PC-2,Logon\n"
        f"email,{{X}},{_stamp(bad.replace(hour=9))},BBB0002,PC-2,a@dtaa.com,,,b@dtaa.com,1,0,reply\n",
        encoding="utf-8",
    )
    return cert


def test_parse_time():
    assert parse_time("10/23/2010 01:34:19") == datetime(2010, 10, 23, 1, 34, 19, tzinfo=UTC)


def test_external_email_is_any_recipient_outside_the_organisation():
    assert not is_external(["a@dtaa.com", "B@DTAA.com"])
    assert is_external(["a@dtaa.com", "friend@gmail.com"])


def test_logs_merge_into_ordered_days(dataset: Path):
    days = list(by_day(merged_events(dataset)))
    assert [d for d, _ in days][:2] == [date(2010, 1, 4), date(2010, 1, 5)]
    last_day, users = days[-1]
    assert last_day == date(2010, 1, 25)
    types = [e.event_type for e in users["AAA0001"]]
    assert types == ["logon", "usb_insert", "http_request", "email_external"]
    stamps = [e.timestamp for d, u in days for evs in u.values() for e in evs]
    assert all(stamps[i].date() <= stamps[i + 1].date() for i in range(len(stamps) - 1))
    assert list(by_day(merged_events(dataset), start=date(2010, 1, 24), end=date(2010, 1, 25)))[0][
        0
    ] == date(2010, 1, 24)


def test_directory_owners_and_answer_key(dataset: Path):
    employees = load_ldap(dataset / "LDAP")
    assert privileged_users(employees) == {"AAA0001"}
    assert employees["AAA0001"].supervisor == "Bob B"

    assert assigned_machines(dataset / "logon.csv", min_logons=5) == {
        "PC-1": "AAA0001",
        "PC-2": "BBB0002",
    }

    insiders = load_insiders(dataset.parent / "answers")
    assert list(insiders) == ["AAA0001"], "other releases are ignored"
    insider = insiders["AAA0001"]
    assert insider.scenario == 3
    assert insider.malicious_days == {
        date(2010, 1, 25)
    }, "rows of other accounts don't label the insider"


def test_replay_writes_features_and_findings(dataset: Path, tmp_path: Path, monkeypatch):
    import evaluation.cert.replay as replay_module

    real = replay_module.assigned_machines
    monkeypatch.setattr(replay_module, "assigned_machines", lambda p: real(p, min_logons=5))
    out = tmp_path / "out"

    meta = replay(dataset, out)

    assert meta["days"] == 22 and meta["user_days"] == 43
    with gzip.open(out / "features.csv.gz", "rt", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    last = [r for r in rows if r["day"] == "2010-01-25"]
    assert len(last) == 1 and last[0]["usb_activity_count"] == "1.0"
    assert last[0]["external_email_count"] == "1.0"

    with gzip.open(out / "findings.jsonl.gz", "rt", encoding="utf-8") as fh:
        findings = [json.loads(line) for line in fh]
    categories = {f["category"] for f in findings if f["day"] == "2010-01-25"}
    assert {
        "UNUSUAL_LOGIN_TIME",
        "ABNORMAL_DATA_DOWNLOAD",
        "SUSPICIOUS_DEVICE_USAGE",
        "PRIVILEGE_ABUSE",
    } <= categories
    assert all(f["day"] == "2010-01-25" for f in findings), "ordinary weeks raise nothing"
    assert json.loads((out / "replay_meta.json").read_text())["privileged_users"] == ["AAA0001"]

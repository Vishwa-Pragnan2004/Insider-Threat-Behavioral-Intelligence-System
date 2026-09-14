"""
ITBIS — CERT r4.2 replay, pass A: features and category findings

Streams the whole dataset day by day through the platform's own feature
aggregator and category detectors, exactly as the live pipeline would have
seen it, and writes:

    features.csv.gz    one row per active user-day: event count + 16 features
    findings.jsonl.gz  every detector finding
    replay_meta.json   what was replayed, with which settings, how long it took

Pass B (evaluate.py) builds baselines, trains and scores the model, applies the
risk engine and measures everything against the answer key; it re-runs in
minutes, so this slow pass only has to run once.

    python -m evaluation.cert.replay --cert-dir ../archive/r4.2 \
        --out ../data/evaluation/cert_r4.2 [--end 2010-03-01]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

import structlog

from app.modules.behavioral.application.aggregator import aggregate_features
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION
from app.modules.detection.application.detectors import DetectionContext, UserTimeline
from app.modules.detection.domain.finding import DETECTOR_VERSION
from evaluation.cert.cert_io import (
    assigned_machines,
    by_day,
    load_ldap,
    merged_events,
    privileged_users,
)

log = structlog.get_logger("cert.replay")
SOURCE = "cert_r4.2"


def replay(
    cert_dir: Path,
    out_dir: Path,
    *,
    start: date | None = None,
    end: date | None = None,
    progress_every: int = 10,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()

    employees = load_ldap(cert_dir / "LDAP")
    owners = assigned_machines(cert_dir / "logon.csv")
    context = DetectionContext(
        pc_owners=owners, privileged_users=privileged_users(employees), source_dataset=SOURCE
    )
    log.info(
        "replay.context",
        employees=len(employees),
        dedicated_machines=len(owners),
        privileged=len(context.privileged_users),
    )

    timelines: dict[str, UserTimeline] = {}
    totals = {"days": 0, "events": 0, "user_days": 0, "findings": 0}
    first_day = last_day = None

    with (
        gzip.open(out_dir / "features.csv.gz", "wt", newline="", encoding="utf-8") as ffh,
        gzip.open(out_dir / "findings.jsonl.gz", "wt", encoding="utf-8") as jfh,
    ):
        features_out = csv.writer(ffh)
        features_out.writerow(["user_id", "day", "event_count", *FEATURE_NAMES])
        for day, users in by_day(merged_events(cert_dir), start=start, end=end):
            first_day = first_day or day
            last_day = day
            for user_id, events in users.items():
                features = aggregate_features([e.as_doc() for e in events])
                features_out.writerow(
                    [user_id, day.isoformat(), len(events), *(features[n] for n in FEATURE_NAMES)]
                )
                timeline = timelines.get(user_id)
                if timeline is None:
                    timeline = timelines[user_id] = UserTimeline(user_id, context)
                _, findings = timeline.process_day(day, [e.as_view() for e in events])
                for f in findings:
                    jfh.write(
                        json.dumps(
                            {
                                "user_id": f.user_id,
                                "day": day.isoformat(),
                                "category": f.category.value,
                                "detector": f.detector,
                                "severity": f.severity,
                                "title": f.title,
                                "description": f.description,
                                "evidence": f.evidence,
                            },
                            default=str,
                        )
                        + "\n"
                    )
                totals["events"] += len(events)
                totals["user_days"] += 1
                totals["findings"] += len(findings)
            totals["days"] += 1
            if totals["days"] % progress_every == 0:
                log.info(
                    "replay.progress",
                    day=day.isoformat(),
                    elapsed_s=round(time.monotonic() - began),
                    **totals,
                )

    meta = {
        "source": SOURCE,
        "cert_dir": str(cert_dir),
        "first_day": first_day.isoformat() if first_day else None,
        "last_day": last_day.isoformat() if last_day else None,
        "feature_version": FEATURE_VERSION,
        "detector_version": DETECTOR_VERSION,
        "detection_settings": asdict(context.settings),
        "employees": len(employees),
        "dedicated_machines": len(owners),
        "privileged_users": sorted(context.privileged_users),
        "runtime_seconds": round(time.monotonic() - began, 1),
        **totals,
    }
    (out_dir / "replay_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out_dir / "machine_owners.json").write_text(json.dumps(owners), encoding="utf-8")
    log.info("replay.done", **{k: v for k, v in meta.items() if k != "privileged_users"})
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--cert-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    args = parser.parse_args()
    replay(args.cert_dir, args.out, start=args.start, end=args.end)


if __name__ == "__main__":
    main()

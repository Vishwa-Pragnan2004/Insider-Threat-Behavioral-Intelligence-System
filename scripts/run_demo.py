"""
ITBIS — Demo Data Generator & Pipeline Runner

This script generates synthetic CERT-format activity data and runs the full detection pipeline:
1. Generate synthetic logon and email CSV data
2. Ingest via POST /api/v1/ingestion/upload
3. Generate behavioral features via POST /api/v1/behavioral/generate
4. Run anomaly detection via POST /api/v1/anomaly/detect
5. Generate alerts via POST /api/v1/alerts/generate

Usage:
    python scripts/run_demo.py [--base-url http://localhost:8000] [--token <jwt_token>]
"""

import argparse
import csv
import io
import random
import sys
import uuid
from datetime import datetime, timedelta, UTC
from pathlib import Path

import httpx


def _utcnow() -> datetime:
    return datetime.now(UTC)


def generate_cert_csv(
    output_path: Path,
    num_users: int = 5,
    normal_days: int = 14,
    anomalous_days: int = 3,
    include_anomalies: bool = True,
) -> list[str]:
    """
    Generate synthetic CERT-format CSV data with normal and anomalous behavior.

    Returns list of generated user IDs.
    """
    random.seed(42)

    users = [f"CERT.user.{i:03d}" for i in range(1, num_users + 1)]
    anomaly_users = random.sample(users, k=max(1, num_users // 3)) if include_anomalies else []

    start_date = _utcnow() - timedelta(days=normal_days + anomalous_days + 1)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(["id", "date", "user", "pc", "activity"])

        row_id = 1

        for user in users:
            pc = f"PC-{user.split('.')[-1]}"

            is_anomaly = user in anomaly_users

            for day_offset in range(normal_days):
                current_date = start_date + timedelta(days=day_offset)

                num_logons = random.randint(3, 8) if not is_anomaly else random.randint(8, 15)
                for _ in range(num_logons):
                    hour = random.randint(8, 18)
                    minute = random.randint(0, 59)
                    second = random.randint(0, 59)
                    dt = current_date.replace(hour=hour, minute=minute, second=second)
                    writer.writerow([row_id, dt.strftime("%m/%d/%Y %H:%M:%S"), user, pc, "logon"])
                    row_id += 1

                    if random.random() < 0.3:
                        writer.writerow([row_id, dt.strftime("%m/%d/%Y %H:%M:%S"), user, pc, "logoff"])
                        row_id += 1

            if is_anomaly:
                for day_offset in range(anomalous_days):
                    current_date = start_date + timedelta(days=normal_days + day_offset)

                    for _ in range(random.randint(20, 35)):
                        hour = random.randint(0, 23)
                        minute = random.randint(0, 59)
                        second = random.randint(0, 59)
                        dt = current_date.replace(hour=hour, minute=minute, second=second)
                        writer.writerow([row_id, dt.strftime("%m/%d/%Y %H:%M:%S"), user, pc, "logon"])
                        row_id += 1

                    for _ in range(random.randint(5, 15)):
                        writer.writerow([row_id, dt.strftime("%m/%d/%Y %H:%M:%S"), user, pc, "failed logon"])
                        row_id += 1

    return users, anomaly_users


def generate_email_csv(output_path: Path, users: list[str], anomaly_users: list[str]) -> None:
    """Generate email activity CSV."""
    random.seed(43)
    cert_domain = "dtaa.com"

    start_date = _utcnow() - timedelta(days=17)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "date", "user", "pc", "to", "from", "activity", "size", "attachments"])

        row_id = 1

        for user in users:
            pc = f"PC-{user.split('.')[-1]}"
            is_anomaly = user in anomaly_users

            for day_offset in range(14):
                current_date = start_date + timedelta(days=day_offset)

                num_emails = random.randint(2, 8) if not is_anomaly else random.randint(15, 30)
                for _ in range(num_emails):
                    hour = random.randint(8, 19)
                    minute = random.randint(0, 59)
                    second = random.randint(0, 59)
                    dt = current_date.replace(hour=hour, minute=minute, second=second)

                    to_addr = f"internal.{random.choice(users).lower()}" if random.random() < 0.8 else f"external@{random.choice(['gmail.com', 'yahoo.com', 'outlook.com'])}"

                    size = random.randint(1000, 500000)
                    attachments = random.randint(0, 5)

                    writer.writerow([
                        row_id,
                        dt.strftime("%m/%d/%Y %H:%M:%S"),
                        user,
                        pc,
                        to_addr,
                        user.lower(),
                        "send",
                        size,
                        attachments
                    ])
                    row_id += 1

                if is_anomaly:
                    for _ in range(random.randint(10, 20)):
                        external_addr = f"external_{random.randint(1000, 9999)}@suspicious-domain.com"
                        size = random.randint(1000000, 10000000)
                        attachments = random.randint(3, 10)

                        writer.writerow([
                            row_id,
                            dt.strftime("%m/%d/%Y %H:%M:%S"),
                            user,
                            pc,
                            external_addr,
                            user.lower(),
                            "send",
                            size,
                            attachments
                        ])
                        row_id += 1


def run_pipeline(base_url: str, token: str) -> dict:
    """Run the full ITBIS demo pipeline."""
    headers = {
        "Authorization": f"Bearer {token}",
    }

    results = {}

    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        print("\n[1/5] Generating synthetic CERT data...")
        data_dir = Path(__file__).parent.parent / "backend" / "data" / "demo"
        data_dir.mkdir(parents=True, exist_ok=True)

        logon_csv = data_dir / "demo_logon.csv"
        email_csv = data_dir / "demo_email.csv"

        users, anomaly_users = generate_cert_csv(logon_csv, num_users=5, normal_days=14, anomalous_days=3)
        print(f"  Generated logon data: {logon_csv}")
        print(f"  Users: {users}")
        print(f"  Anomaly users: {anomaly_users}")

        generate_email_csv(email_csv, users, anomaly_users)
        print(f"  Generated email data: {email_csv}")

        print("\n[2/5] Ingesting logon data...")
        with open(logon_csv, "rb") as f:
            resp = client.post(
                "/api/v1/ingestion/upload",
                headers=headers,
                files={"file": ("demo_logon.csv", f, "text/csv")},
                data={"source_dataset": "cert"},
            )
        resp.raise_for_status()
        job_result = resp.json()
        print(f"  Job status: {job_result['job']['status']}")
        print(f"  Events stored: {job_result['job']['events_stored']}")
        results["logon_ingestion"] = job_result

        print("\n[3/5] Ingesting email data...")
        with open(email_csv, "rb") as f:
            resp = client.post(
                "/api/v1/ingestion/upload",
                headers=headers,
                files={"file": ("demo_email.csv", f, "text/csv")},
                data={"source_dataset": "cert"},
            )
        resp.raise_for_status()
        job_result = resp.json()
        print(f"  Job status: {job_result['job']['status']}")
        print(f"  Events stored: {job_result['job']['events_stored']}")
        results["email_ingestion"] = job_result

        end = _utcnow()
        start = end - timedelta(days=17)

        print(f"\n[4/5] Generating behavioral features ({start.date()} to {end.date()})...")
        resp = client.post(
            "/api/v1/behavioral/generate",
            headers=headers,
            json={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "source_dataset": "cert",
                "window": "daily",
            },
        )
        resp.raise_for_status()
        feat_result = resp.json()
        print(f"  Rows generated: {feat_result['rows_generated']}")
        print(f"  Users processed: {feat_result['users_processed']}")
        results["features"] = feat_result

        print("\n[5/5] Running anomaly detection...")
        resp = client.post(
            "/api/v1/anomaly/detect",
            headers=headers,
            json={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "source_dataset": "cert",
                "window": "daily",
            },
        )
        resp.raise_for_status()
        anomaly_result = resp.json()
        print(f"  Anomalies detected: {anomaly_result['count']}")
        print(f"  Risk levels: {anomaly_result['risk_levels']}")
        results["anomalies"] = anomaly_result

        if anomaly_result["count"] > 0:
            print("\n[Bonus] Generating alerts...")
            resp = client.post(
                "/api/v1/alerts/generate",
                headers=headers,
                json={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": 50,
                },
            )
            resp.raise_for_status()
            alert_result = resp.json()
            print(f"  Alerts created: {alert_result['created']}")
            print(f"  Skipped (duplicates): {alert_result['skipped_duplicates']}")
            print(f"  Skipped (below threshold): {alert_result['skipped_below_threshold']}")
            results["alerts"] = alert_result
        else:
            print("\n[Bonus] No anomalies to generate alerts from.")

    print("\n" + "=" * 60)
    print("DEMO PIPELINE COMPLETE")
    print("=" * 60)
    return results


def get_token(base_url: str, email: str, password: str) -> str:
    """Login and get access token."""
    resp = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main():
    parser = argparse.ArgumentParser(description="Run ITBIS demo pipeline")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--token", help="JWT access token (will login if not provided)")
    parser.add_argument("--email", default="admin@itbis-platform.com", help="Login email")
    parser.add_argument("--password", default="Admin@ITBIS1", help="Login password")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    if not args.token:
        print(f"Logging in as {args.email}...")
        token = get_token(base_url, args.email, args.password)
        print("Login successful.\n")
    else:
        token = args.token

    run_pipeline(base_url, token)


if __name__ == "__main__":
    main()

# ruff: noqa: E402
# Imports below are deliberately placed after the environment is
# configured: itbis_agent reads ITBIS_AGENT_* at import time, so hoisting
# them to the top would capture the wrong settings.
r"""
Windows Security Collector - Manual End-to-End Test
============================================================================

Run this from an ELEVATED PowerShell where Security Event Log access is available.

Usage:
    cd C:\Users\vishw\Desktop\spring\2\project2
    python agent\scripts\manual_e2e_windows.py

Steps:
0. Script enrolls this device and obtains its own revocable credential
1. Script performs initial discovery poll (establishes bookmark, yields nothing)
2. Script PAUSES and asks you to lock/unlock Windows (generate new Security events)
3. Script collects new events
4. Script passes events through Normalizer -> Queue -> Uploader -> Backend
5. Script verifies queue is empty after successful upload
"""

import os
import sys
import time
import uuid
from pathlib import Path

import httpx

# Allow importing the agent package regardless of the working directory.
AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))


# =============================================================================
# STEP 0: Enroll this device and obtain its credential
# =============================================================================

print("=" * 60)
print("WINDOWS SECURITY COLLECTOR - MANUAL END-TO-END TEST")
print("=" * 60)
print()

BASE_URL = os.environ.get("ITBIS_E2E_BASE_URL", "http://localhost:8000")
ADMIN_EMAIL = os.environ.get("ITBIS_E2E_ADMIN_EMAIL", "admin@itbis-platform.com")
ADMIN_PASSWORD = os.environ.get("ITBIS_E2E_ADMIN_PASSWORD", "Admin@ITBIS1")
DEVICE_ID = "WS-SEC-E2E"
DEVICE_NAME = "SEC-E2E-PC"

print("STEP 0a: Logging in as admin (needed to enroll a device)...")
with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if r.status_code != 200:
        print(f"ERROR: admin login failed ({r.status_code}): {r.text[:300]}")
        sys.exit(1)
    admin_token = r.json()["access_token"]
    print("  Admin token obtained.")

    print(f"STEP 0b: Enrolling device {DEVICE_ID!r}...")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/agents/enroll",
        json={"device_id": DEVICE_ID, "device_name": DEVICE_NAME},
        headers=admin_headers,
    )
    if r.status_code == 409:
        # Already enrolled from a previous run — rotate to get a usable key,
        # since the original secret is not recoverable by design.
        print("  Already enrolled; rotating its key instead.")
        r = client.post(f"/api/v1/agents/{DEVICE_ID}/rotate", headers=admin_headers)
    if r.status_code not in (200, 201):
        print(f"ERROR: enrollment failed ({r.status_code}): {r.text[:300]}")
        sys.exit(1)
    device_key = r.json()["api_key"]
    print(f"  Device credential issued: {device_key[:24]}...")

print()


# =============================================================================
# Configure agent through environment variables
# =============================================================================

test_id = f"SEC-E2E-{uuid.uuid4().hex[:8]}"

print(f"Test ID: {test_id}")
print()

os.environ["ITBIS_AGENT_DEVICE_ID"] = DEVICE_ID
os.environ["ITBIS_AGENT_DEVICE_NAME"] = DEVICE_NAME
os.environ["ITBIS_AGENT_BASE_URL"] = BASE_URL
os.environ["ITBIS_AGENT_API_KEY"] = device_key


# =============================================================================
# Import ITBIS components
# =============================================================================

from itbis_agent.collectors.windows_security import WindowsSecurityCollector
from itbis_agent.config import Config, QueueConfig
from itbis_agent.normalizer import Normaliser
from itbis_agent.queue import PersistentQueue
from itbis_agent.uploader import Uploader

# =============================================================================
# STEP 1: Create collector
# =============================================================================

print("STEP 1: Creating WindowsSecurityCollector...")

collector = WindowsSecurityCollector(poll_interval_seconds=1.0)

print(f"  Bookmark before: {collector._bookmark}")
print()


# =============================================================================
# STEP 2: Initial discovery poll
# =============================================================================

print("STEP 2: Performing initial discovery poll...")
print("  This reads the Security log and establishes the bookmark.")
print("  No historical events will be yielded (live monitoring policy).")
print()

try:
    events = list(collector._read_events())

    print(f"  Events from discovery: {len(events)} (expected: 0)")
    print(f"  Bookmark after discovery: {collector._bookmark}")

except Exception as e:
    print(f"  ERROR during discovery: {e}")
    sys.exit(1)

if collector._bookmark is None:
    print("  ERROR: Bookmark was not set after discovery!")
    sys.exit(1)


# =============================================================================
# STEP 3: Generate new Windows events
# =============================================================================

print()
print("=" * 60)
print("ACTION REQUIRED: Please LOCK and UNLOCK your Windows session")
print()
print("This should generate new Windows Security events such as:")
print("  4624 - Successful logon")
print("  4634 - Logoff")
print()
print("After unlocking Windows, return here.")
print("=" * 60)

input("Press ENTER when you have locked and unlocked Windows...")

# Give Windows a moment to finish writing Security events
time.sleep(2)


# =============================================================================
# STEP 4: Collect new events
# =============================================================================

print()
print("STEP 4: Collecting new Security events...")
print(f"  Looking for events newer than record number {collector._bookmark}")
print()

try:
    new_events = list(collector._read_events())

    print(f"  Collected {len(new_events)} new events")
    print(f"  New bookmark: {collector._bookmark}")

except Exception as e:
    print(f"  ERROR while collecting events: {e}")
    new_events = []


if not new_events:
    print()
    print("WARNING: No new events collected!")
    print("The lock/unlock may not have generated matching events.")
    print()
    print("=" * 60)
    print("TEST COMPLETE - NO EVENTS CAPTURED")
    print("=" * 60)
    sys.exit(0)


# =============================================================================
# STEP 5: Display captured events
# =============================================================================

print()
print("STEP 5: Captured Events")
print("-" * 40)

for i, ev in enumerate(new_events):
    print(f"  Event {i + 1}:")
    print(f"    EventID: {ev['event_id']}")
    print(f"    RecordNumber: {ev['record_number']}")
    print(f"    Category: {ev['category']}")
    print(f"    TimeGenerated: {ev['time_generated']}")

    strings = ev.get("strings", [])
    user = strings[5] if len(strings) > 5 else "N/A"

    print(f"    User: {user}")
    print()


# =============================================================================
# STEP 6: Normalize events
# =============================================================================

print("STEP 6: Normalizing events through existing Normaliser...")
print()

cfg = Config.from_env()
normalizer = Normaliser(cfg.agent)

normalized = []

for raw in new_events:
    canon = normalizer.normalise(raw)

    if canon:
        canon.tags = [
            "security_e2e_test",
            raw.get("category", ""),
            test_id,
        ]

        normalized.append(canon)

        print(
            f"  Normalized: "
            f"{canon.event_type} "
            f"user={canon.user_id} "
            f"raw_id={canon.raw_event_id}"
        )

    else:
        print(f"  FAILED to normalize event {raw.get('event_id')}")

print()
print(f"  Successfully normalized: {len(normalized)} events")

if not normalized:
    print()
    print("ERROR: No events were successfully normalized.")
    sys.exit(1)


# =============================================================================
# STEP 7: Enqueue events into SQLite
# =============================================================================

print()
print("STEP 7: Enqueueing events into SQLite queue...")

queue_cfg = QueueConfig(db_path="./test_security_e2e.db")

queue = PersistentQueue(
    queue_cfg,
    agent_id="WS-SEC-E2E",
)

for canon in normalized:
    queue.enqueue(canon)

print(f"  Pending events: {queue.count_pending()}")
print(f"  Queue stats: {queue.stats()}")


# =============================================================================
# STEP 8: Upload events to backend
# =============================================================================

print()
print("STEP 8: Uploading events to backend via existing Uploader...")

uploader = Uploader(
    server=cfg.server,
    upload=cfg.upload,
    queue=queue,
    agent_id="WS-SEC-E2E",
)

try:
    uploader.start()

    stats = uploader.tick()

    print(f"  Upload stats: {stats}")

    print(
        f"  Backend response: "
        f"sent={stats['sent']} "
        f"duplicates={stats['duplicates']} "
        f"rejected={stats['rejected']} "
        f"retries={stats['retries']}"
    )

finally:
    uploader.stop()


# =============================================================================
# STEP 9: Verify queue state
# =============================================================================

print()
print("STEP 9: Verifying queue after upload...")

print(f"  Queue stats: {queue.stats()}")

pending_after = queue.count_pending()

print(f"  Pending events after upload: {pending_after}")

queue.close()


# =============================================================================
# RESULTS
# =============================================================================

print()
print("=" * 60)
print("RESULTS")
print("=" * 60)

print(f"  Test ID: {test_id}")
print(f"  Events captured: {len(new_events)}")
print(f"  Events normalized: {len(normalized)}")
print(f"  Events sent: {stats['sent']}")
print(f"  Duplicates: {stats['duplicates']}")
print(f"  Rejected: {stats['rejected']}")
print(f"  Retries: {stats['retries']}")
print(f"  Queue empty: {pending_after == 0}")

print()

if stats["sent"] > 0 and pending_after == 0:
    print("RESULT: SUCCESS - Full pipeline verified!")
    print()
    print("Real Windows Security events successfully travelled through:")
    print()
    print("  Windows Security Log")
    print("          ↓")
    print("  WindowsSecurityCollector")
    print("          ↓")
    print("  Normaliser")
    print("          ↓")
    print("  SQLite Persistent Queue")
    print("          ↓")
    print("  Uploader")
    print("          ↓")
    print("  ITBIS Backend")

elif stats["duplicates"] > 0 and pending_after == 0:
    print("RESULT: SUCCESS - Events were already known to the backend.")
    print("The pipeline worked and the queue was successfully cleared.")

else:
    print("RESULT: PARTIAL / FAILED")
    print("Check the output above for the failing stage.")

print()
print("=" * 60)
print("TEST COMPLETE")
print("=" * 60)

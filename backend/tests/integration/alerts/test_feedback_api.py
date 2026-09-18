"""
ITBIS — Integration tests: analyst feedback API.

Covers:
  - permissions (401 unauthenticated, 403 for a viewer, 201 for an analyst)
  - recording a verdict closes the alert to match
  - a verdict without an explanation is refused
  - re-judging supersedes but keeps the history
  - measured precision and the labelled training export
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.alerts.conftest import (
    ALERTS_BASE,
    admin_token,
    analyst_token,
    anomaly_doc,
    viewer_token,
)

FEEDBACK = "/api/v1/feedback"
UNKNOWN = "00000000-0000-0000-0000-000000000000"


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _an_alert(client: AsyncClient, headers: dict, mongo, *, user_id: str, day: int = 1) -> str:
    """Seed one anomaly, generate its alert, and return the alert id."""
    await mongo["anomaly_results"].insert_one(
        anomaly_doc(
            user_id=user_id,
            risk_level="CRITICAL",
            window_start=datetime(2026, 8, day, tzinfo=UTC),
            window_end=datetime(2026, 8, day + 1, tzinfo=UTC),
        )
    )
    await client.post(f"{ALERTS_BASE}/generate", json={"limit": 100}, headers=headers)
    r = await client.get(f"{ALERTS_BASE}/", params={"user_id": user_id}, headers=headers)
    return r.json()["alerts"][0]["id"]


# ─── Permissions ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthenticated_requests_are_rejected(async_client: AsyncClient):
    assert (await async_client.get(f"{FEEDBACK}/stats")).status_code == 401
    assert (await async_client.get(f"{FEEDBACK}/labels")).status_code == 401
    r = await async_client.post(
        f"{FEEDBACK}/alerts/{UNKNOWN}/verdict",
        json={"verdict": "BENIGN", "rationale": "x" * 5},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_viewer_may_read_but_not_judge(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    analyst = await analyst_token(async_client, db_session)
    viewer = await viewer_token(async_client, db_session)
    alert_id = await _an_alert(async_client, _h(analyst), mongo_mock_db, user_id="jane")

    # A viewer has alerts:read, so the measurements are open to them...
    assert (await async_client.get(f"{FEEDBACK}/stats", headers=_h(viewer))).status_code == 200
    # ...but judging an alert takes alerts:update.
    r = await async_client.post(
        f"{FEEDBACK}/alerts/{alert_id}/verdict",
        json={"verdict": "BENIGN", "rationale": "Routine."},
        headers=_h(viewer),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_judging_an_unknown_alert_is_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    analyst = await analyst_token(async_client, db_session)
    r = await async_client.post(
        f"{FEEDBACK}/alerts/{UNKNOWN}/verdict",
        json={"verdict": "BENIGN", "rationale": "Nothing here."},
        headers=_h(analyst),
    )
    assert r.status_code == 404


# ─── Recording ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirming_a_threat_closes_the_alert_and_stores_the_evidence(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    analyst = await analyst_token(async_client, db_session)
    alert_id = await _an_alert(async_client, _h(analyst), mongo_mock_db, user_id="jane")

    r = await async_client.post(
        f"{FEEDBACK}/alerts/{alert_id}/verdict",
        json={
            "verdict": "CONFIRMED_THREAT",
            "rationale": "HR confirmed the resignation; the copy was not sanctioned.",
        },
        headers=_h(analyst),
    )
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["alert"]["status"] == "RESOLVED"
    verdict = body["verdict"]
    assert verdict["subject_user_id"] == "jane"
    assert verdict["subject_day"] == "2026-08-01"
    assert verdict["is_current"] is True
    assert verdict["training_label"] is True
    assert verdict["decided_by"]  # the analyst who called it
    # The snapshot records which model was in force, so the label stays
    # interpretable after the model changes.
    assert verdict["evidence"]["model_version"]
    assert verdict["evidence"]["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_calling_it_benign_marks_the_alert_a_false_positive(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    analyst = await analyst_token(async_client, db_session)
    alert_id = await _an_alert(async_client, _h(analyst), mongo_mock_db, user_id="bob")

    r = await async_client.post(
        f"{FEEDBACK}/alerts/{alert_id}/verdict",
        json={"verdict": "BENIGN", "rationale": "Scheduled archive job, ticket CHG-441."},
        headers=_h(analyst),
    )
    assert r.status_code == 201
    assert r.json()["alert"]["status"] == "FALSE_POSITIVE"

    # And the alert itself reflects it when fetched fresh.
    a = await async_client.get(f"{ALERTS_BASE}/{alert_id}", headers=_h(analyst))
    assert a.json()["status"] == "FALSE_POSITIVE"


@pytest.mark.asyncio
async def test_a_verdict_needs_an_explanation(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    analyst = await analyst_token(async_client, db_session)
    alert_id = await _an_alert(async_client, _h(analyst), mongo_mock_db, user_id="carl")

    r = await async_client.post(
        f"{FEEDBACK}/alerts/{alert_id}/verdict",
        json={"verdict": "BENIGN", "rationale": ""},
        headers=_h(analyst),
    )
    assert r.status_code == 422

    # Nothing was recorded.
    got = await async_client.get(f"{FEEDBACK}/alerts/{alert_id}/verdict", headers=_h(analyst))
    assert got.json()["current"] is None


@pytest.mark.asyncio
async def test_re_judging_supersedes_the_first_call_but_keeps_it(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    analyst = await analyst_token(async_client, db_session)
    alert_id = await _an_alert(async_client, _h(analyst), mongo_mock_db, user_id="dina")

    await async_client.post(
        f"{FEEDBACK}/alerts/{alert_id}/verdict",
        json={"verdict": "BENIGN", "rationale": "Looked like normal backup traffic."},
        headers=_h(analyst),
    )
    r = await async_client.post(
        f"{FEEDBACK}/alerts/{alert_id}/verdict",
        json={
            "verdict": "CONFIRMED_THREAT",
            "rationale": "Reopened after HR flagged the resignation.",
        },
        headers=_h(analyst),
    )
    assert r.status_code == 201

    got = (
        await async_client.get(f"{FEEDBACK}/alerts/{alert_id}/verdict", headers=_h(analyst))
    ).json()
    assert got["current"]["verdict"] == "CONFIRMED_THREAT"
    assert len(got["history"]) == 2
    assert [v["verdict"] for v in got["history"]] == ["BENIGN", "CONFIRMED_THREAT"]
    assert got["history"][0]["is_current"] is False

    # Only the current one counts towards the numbers.
    stats = (await async_client.get(f"{FEEDBACK}/stats", headers=_h(analyst))).json()
    assert stats["total"] == 1 and stats["threats"] == 1 and stats["benign"] == 0


# ─── Measurement and export ────────────────────────────────


@pytest.mark.asyncio
async def test_precision_and_training_rows_reflect_the_calls_made(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    analyst = await analyst_token(async_client, db_session)
    headers = _h(analyst)

    calls = [
        ("eve", "CONFIRMED_THREAT", "Exfiltration confirmed."),
        ("finn", "CONFIRMED_THREAT", "Keylogger found on the machine."),
        ("gil", "BENIGN", "Approved migration work."),
        ("hana", "POLICY_VIOLATION", "Personal Dropbox use — real, but not a threat."),
        ("ivan", "INCONCLUSIVE", "Cannot reach the owner."),
    ]
    for i, (user, verdict, why) in enumerate(calls):
        alert_id = await _an_alert(async_client, headers, mongo_mock_db, user_id=user, day=i + 1)
        r = await async_client.post(
            f"{FEEDBACK}/alerts/{alert_id}/verdict",
            json={"verdict": verdict, "rationale": why},
            headers=headers,
        )
        assert r.status_code == 201, r.text

    stats = (await async_client.get(f"{FEEDBACK}/stats", headers=headers)).json()
    assert stats["total"] == 5
    assert stats["counts"]["CONFIRMED_THREAT"] == 2
    assert stats["counts"]["POLICY_VIOLATION"] == 1
    # 2 of the 3 decisive calls were real threats.
    assert stats["precision"] == pytest.approx(0.667, abs=0.001)
    assert stats["trainable"] == 3

    labels = (await async_client.get(f"{FEEDBACK}/labels", headers=headers)).json()
    assert sorted(row["subject_user_id"] for row in labels) == ["eve", "finn", "gil"]
    assert {row["label"] for row in labels} == {True, False}
    # The ambiguous calls are stored but withheld from training.
    assert all(row["subject_user_id"] not in ("hana", "ivan") for row in labels)


@pytest.mark.asyncio
async def test_verdicts_can_be_listed_and_filtered_by_person(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    admin = await admin_token(async_client, db_session)
    headers = _h(admin)
    for i, user in enumerate(("kim", "leo")):
        alert_id = await _an_alert(async_client, headers, mongo_mock_db, user_id=user, day=i + 1)
        await async_client.post(
            f"{FEEDBACK}/alerts/{alert_id}/verdict",
            json={"verdict": "BENIGN", "rationale": "Checked, fine."},
            headers=headers,
        )

    all_rows = (await async_client.get(f"{FEEDBACK}/verdicts", headers=headers)).json()
    assert all_rows["total"] == 2

    just_kim = (
        await async_client.get(f"{FEEDBACK}/verdicts", params={"user_id": "kim"}, headers=headers)
    ).json()
    assert just_kim["total"] == 1
    assert just_kim["items"][0]["subject_user_id"] == "kim"

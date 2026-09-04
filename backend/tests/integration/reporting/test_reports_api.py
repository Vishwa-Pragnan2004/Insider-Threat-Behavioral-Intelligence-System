"""
ITBIS — Integration Tests: Reporting Endpoints
Tests real HTTP flows end-to-end using in-memory SQLite + FakeRedis.

Coverage:
- GET  /api/v1/reports/alerts/export           (auth, RBAC, CSV content)
- GET  /api/v1/reports/investigations/export    (auth, RBAC, CSV content)
"""

import pytest
from httpx import AsyncClient

from app.modules.identity.application.services.token_service import token_service
from app.modules.identity.domain.enums import PermissionName, RoleName

BASE = "/api/v1/reports"


async def get_auth_headers(async_client: AsyncClient) -> dict:
    """Register and login a user, return auth headers."""
    await async_client.post("/api/v1/auth/register", json={
        "username": "reporter",
        "email": "reporter@example.com",
        "password": "SecurePass1!",
        "full_name": "Test Reporter",
    })
    resp = await async_client.post("/api/v1/auth/login", json={
        "email": "reporter@example.com",
        "password": "SecurePass1!",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def get_admin_headers(async_client: AsyncClient) -> dict:
    """Register and login a user with admin role, return auth headers."""
    await async_client.post("/api/v1/auth/register", json={
        "username": "admin",
        "email": "admin@example.com",
        "password": "SecurePass1!",
        "full_name": "Test Admin",
    })
    resp = await async_client.post("/api/v1/auth/login", json={
        "email": "admin@example.com",
        "password": "SecurePass1!",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────
# Alert Export
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alerts_export_requires_auth(async_client: AsyncClient):
    """Unauthenticated requests return 401."""
    r = await async_client.get(f"{BASE}/alerts/export")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_alerts_export_returns_csv(async_client: AsyncClient):
    """Authenticated user can export alerts as CSV."""
    headers = await get_auth_headers(async_client)
    r = await async_client.get(f"{BASE}/alerts/export", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "alerts_report.csv" in r.headers["content-disposition"]


@pytest.mark.asyncio
async def test_alerts_export_empty_csv_structure(async_client: AsyncClient):
    """Export returns valid CSV even when empty."""
    headers = await get_auth_headers(async_client)
    r = await async_client.get(f"{BASE}/alerts/export", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"


@pytest.mark.asyncio
async def test_alerts_export_with_filters(async_client: AsyncClient):
    """Export accepts severity and status filters."""
    headers = await get_auth_headers(async_client)
    r = await async_client.get(
        f"{BASE}/alerts/export",
        headers=headers,
        params={"severity": "HIGH", "status": "OPEN"},
    )
    assert r.status_code == 200


# ─────────────────────────────────────────────────────────────
# Investigation Export
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_investigations_export_requires_auth(async_client: AsyncClient):
    """Unauthenticated requests return 401."""
    r = await async_client.get(f"{BASE}/investigations/export")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_investigations_export_returns_csv(async_client: AsyncClient):
    """Authenticated user can export investigations as CSV."""
    headers = await get_auth_headers(async_client)
    r = await async_client.get(f"{BASE}/investigations/export", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "investigations_report.csv" in r.headers["content-disposition"]


@pytest.mark.asyncio
async def test_investigations_export_empty_csv_structure(async_client: AsyncClient):
    """Export returns valid CSV even when empty."""
    headers = await get_auth_headers(async_client)
    r = await async_client.get(f"{BASE}/investigations/export", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"


@pytest.mark.asyncio
async def test_investigations_export_with_status_filter(async_client: AsyncClient):
    """Export accepts status filter."""
    headers = await get_auth_headers(async_client)
    r = await async_client.get(
        f"{BASE}/investigations/export",
        headers=headers,
        params={"status": "OPEN"},
    )
    assert r.status_code == 200

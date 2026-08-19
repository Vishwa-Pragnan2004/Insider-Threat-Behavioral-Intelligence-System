"""
ITBIS — Health Endpoint Tests
Tests for GET /api/v1/health, /api/v1/health/ready, /api/v1/health/info
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealthLiveness:
    """Tests for the liveness health endpoint."""

    async def test_liveness_returns_200(self, client: AsyncClient):
        """Liveness endpoint must return HTTP 200."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_liveness_returns_ok_status(self, client: AsyncClient):
        """Liveness response body must contain status: ok."""
        response = await client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "ok"

    async def test_liveness_contains_service_name(self, client: AsyncClient):
        """Liveness response must include the service name."""
        response = await client.get("/api/v1/health")
        data = response.json()
        assert "service" in data
        assert data["service"] == "ITBIS"

    async def test_liveness_contains_version(self, client: AsyncClient):
        """Liveness response must include a version field."""
        response = await client.get("/api/v1/health")
        data = response.json()
        assert "version" in data

    async def test_liveness_contains_uptime(self, client: AsyncClient):
        """Liveness response must include uptime_seconds."""
        response = await client.get("/api/v1/health")
        data = response.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
class TestHealthReadiness:
    """Tests for the readiness health endpoint."""

    async def test_readiness_returns_200(self, client: AsyncClient):
        """Readiness endpoint must return HTTP 200 (stubs are OK)."""
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200

    async def test_readiness_contains_checks(self, client: AsyncClient):
        """Readiness response must contain individual dependency checks."""
        response = await client.get("/api/v1/health/ready")
        data = response.json()
        assert "checks" in data
        checks = data["checks"]
        assert "postgres" in checks
        assert "mongodb" in checks
        assert "redis" in checks
        assert "elasticsearch" in checks
        assert "kafka" in checks

    async def test_readiness_overall_status(self, client: AsyncClient):
        """Readiness response must have an overall status field."""
        response = await client.get("/api/v1/health/ready")
        data = response.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")


@pytest.mark.asyncio
class TestHealthInfo:
    """Tests for the application info endpoint."""

    async def test_info_returns_200(self, client: AsyncClient):
        """Info endpoint must return HTTP 200."""
        response = await client.get("/api/v1/health/info")
        assert response.status_code == 200

    async def test_info_contains_api_version(self, client: AsyncClient):
        """Info response must include api_version."""
        response = await client.get("/api/v1/health/info")
        data = response.json()
        assert data["api_version"] == "v1"

    async def test_info_contains_modules(self, client: AsyncClient):
        """Info response must list expected modules."""
        response = await client.get("/api/v1/health/info")
        data = response.json()
        assert "modules" in data
        expected_modules = {
            "identity", "users", "assets", "activity", "behavioral",
            "anomaly", "risk", "ueba", "alerts", "investigations",
            "response", "reporting", "notifications", "admin"
        }
        assert set(data["modules"]) == expected_modules

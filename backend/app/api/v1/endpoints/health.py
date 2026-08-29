"""
ITBIS — Health Check Endpoints
Provides liveness and readiness probes for infrastructure monitoring,
container orchestration (Kubernetes / Docker), and load balancers.

GET /api/v1/health        — Basic liveness: confirms the application is running
GET /api/v1/health/ready  — Readiness: confirms all dependencies are reachable
GET /api/v1/health/info   — Application build/version information
"""

import time
from typing import Any, Dict

import structlog
from fastapi import APIRouter, status

from app.core.config import get_settings

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()

# Application start time (used for uptime calculation)
_START_TIME = time.time()


# ─── Liveness ───────────────────────────────────────────────
@router.get(
    "",
    summary="Liveness probe",
    description="Returns 200 OK if the application process is alive.",
    response_description="Application is alive",
    status_code=status.HTTP_200_OK,
)
async def health_liveness() -> dict:
    """
    Basic liveness check.
    Used by Docker HEALTHCHECK and Kubernetes liveness probes.
    A 200 response means the process is running.
    """
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "uptime_seconds": round(time.time() - _START_TIME, 2),
    }


# ─── Readiness ──────────────────────────────────────────────
@router.get(
    "/ready",
    summary="Readiness probe",
    description=(
        "Returns 200 OK if all critical dependencies are reachable. "
        "Returns 503 if any dependency is unavailable."
    ),
    status_code=status.HTTP_200_OK,
)
async def health_readiness() -> dict:
    """
    Readiness check — verifies connectivity to backing services.

    NOTE: In Phase 0 (foundation), actual connectivity checks are stubbed.
    Each check will be implemented when the corresponding infrastructure
    module is wired up (Phases 1+).
    """
    checks: Dict[str, Any] = {
        "postgres": _stub_check("postgres"),
        "mongodb": _stub_check("mongodb"),
        "redis": _stub_check("redis"),
        "elasticsearch": _stub_check("elasticsearch"),
        "kafka": _stub_check("kafka"),
    }

    all_healthy = all(v["status"] == "ok" for v in checks.values())
    overall = "ok" if all_healthy else "degraded"

    return {
        "status": overall,
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "checks": checks,
    }


# ─── Info ───────────────────────────────────────────────────
@router.get(
    "/info",
    summary="Application information",
    description="Returns build and configuration metadata.",
    status_code=status.HTTP_200_OK,
)
async def health_info() -> dict:
    """
    Application info endpoint.
    Returns version, environment, and feature flags.
    Sensitive config values are never exposed here.
    """
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "description": (
            "ITBIS — Insider Threat Behavioral Intelligence System. "
            "Enterprise UEBA platform."
        ),
        "api_version": "v1",
        "modules": [
            "identity",
            "users",
            "assets",
            "activity",
            "behavioral",
            "anomaly",
            "risk",
            "ueba",
            "alerts",
            "investigations",
            "response",
            "reporting",
            "notifications",
            "admin",
        ],
    }


# ─── Stub Helper ────────────────────────────────────────────
def _stub_check(service: str) -> Dict[str, str]:
    """
    Stub health check for a dependency.

    Returns a placeholder response. Will be replaced with real
    connectivity checks when infrastructure modules are wired up.
    """
    return {
        "status": "ok",
        "note": f"{service} check not yet implemented (Phase 0 stub)",
    }

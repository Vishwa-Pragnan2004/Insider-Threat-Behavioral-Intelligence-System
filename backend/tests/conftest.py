"""
ITBIS — Test Configuration & Shared Fixtures
pytest conftest.py — automatically loaded by pytest for all tests.
"""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.main import app as fastapi_app
from app.core.config import get_settings
from app.modules.identity.application.services.token_service import token_service
from app.modules.identity.domain.enums import RoleName


# ─── Event Loop ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Use a single event loop for all async tests in the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ─── Test Settings Override ─────────────────────────────────
@pytest.fixture(scope="session")
def test_settings():
    """Return settings configured for the test environment."""
    return get_settings()


# ─── Application Fixture ─────────────────────────────────────
@pytest.fixture(scope="session")
def app() -> FastAPI:
    """Return the FastAPI application instance."""
    return fastapi_app


# ─── HTTP Test Client (used by Phase 0 health tests) ────────
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Plain async HTTP test client — no DB/Redis overrides.
    Used by health endpoint tests which don't need auth.
    """
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac


# ─── Auth Headers Helper ─────────────────────────────────────
@pytest.fixture
def auth_headers():
    """Returns a factory function to generate auth headers for a specific user ID."""
    def _create_headers(
        user_id: str,
        roles: list[str] = None,
        permissions: list[str] = None,
        is_superadmin: bool = False,
    ):
        claims = {
            "roles": roles or [RoleName.VIEWER.value],
            "permissions": permissions or [],
            "is_superadmin": is_superadmin,
        }
        token = token_service.create_access_token(user_id, claims)
        return {"Authorization": f"Bearer {token}"}
    return _create_headers

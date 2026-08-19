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
    settings = get_settings()
    return settings


# ─── HTTP Test Client ────────────────────────────────────────
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client for the FastAPI application.
    Use this fixture in all API endpoint tests.
    """
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac


# ─── Application Fixture ─────────────────────────────────────
@pytest.fixture(scope="session")
def app() -> FastAPI:
    """Return the FastAPI application instance."""
    return fastapi_app

"""
ITBIS — MongoDB Client Factory
Provides an async Motor MongoDB client and a FastAPI dependency.
"""

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

_mongo_client: AsyncIOMotorClient | None = None


async def get_mongo_client() -> AsyncIOMotorClient:
    """
    Return a shared async Motor MongoDB client.
    Creates one lazily on first call.
    """
    global _mongo_client
    if _mongo_client is None:
        settings = get_settings()
        _mongo_client = AsyncIOMotorClient(
            settings.mongo_url,
            uuidRepresentation="standard",
        )
    return _mongo_client


async def get_mongo_db() -> AsyncIOMotorDatabase:
    """Return the application's default MongoDB database handle."""
    client = await get_mongo_client()
    settings = get_settings()
    return client[settings.MONGO_DB]


async def close_mongo() -> None:
    """Close the MongoDB connection. Call on application shutdown."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None


async def reset_mongo_for_tests() -> None:
    """
    Reset the module-level Mongo client.
    Test-only helper: allows tests to inject a mock client.
    """
    global _mongo_client
    _mongo_client = None

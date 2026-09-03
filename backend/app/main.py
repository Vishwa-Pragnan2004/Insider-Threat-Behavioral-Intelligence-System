"""
ITBIS — Insider Threat Behavioral Intelligence System
FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware


from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging
from app.core.mongo_client import close_mongo
from app.core.redis_client import close_redis, get_redis
from app.api.v1.router import api_v1_router
from app.modules.identity.infrastructure.seeders import seed_identity_module

# ─── Configure structured logging ───────────────────────────
configure_logging()
logger = structlog.get_logger(__name__)
settings = get_settings()


# ─── Application Lifespan ───────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle.
    Initialise connections on startup; close them on shutdown.
    """
    logger.info(
        "ITBIS starting up",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )
    # Initialize connections
    await get_redis()
    
    # Run seeders
    async with AsyncSessionLocal() as session:
        await seed_identity_module(session)
        await session.commit()

    yield
    logger.info("ITBIS shutting down")
    # Close connections
    await close_redis()
    await close_mongo()


# ─── FastAPI Application ─────────────────────────────────────
def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""

    application = FastAPI(
        title=settings.APP_NAME,
        description=(
            "ITBIS — Insider Threat Behavioral Intelligence System. "
            "Enterprise-grade UEBA platform for detecting insider threats, "
            "anomalous behavior, and security policy violations."
        ),
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.APP_DEBUG else None,
        redoc_url="/redoc" if settings.APP_DEBUG else None,
        openapi_url="/openapi.json" if settings.APP_DEBUG else None,
        lifespan=lifespan,
    )

    # ─── Middleware ──────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if not settings.APP_DEBUG:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"],  # Restrict in production
        )

    # ─── Routers ────────────────────────────────────────────
    application.include_router(api_v1_router, prefix="/api/v1")

    return application


app = create_application()

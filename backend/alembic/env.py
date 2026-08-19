"""
ITBIS — Alembic Migration Environment
Configures async SQLAlchemy migrations for PostgreSQL.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all SQLAlchemy models here so Alembic can detect them for autogenerate
# from app.modules.identity.infrastructure.models import *
# from app.modules.users.infrastructure.models import *
# etc. — uncomment as modules are implemented

from app.core.config import get_settings

# ─── Alembic Config ──────────────────────────────────────────
config = context.config
settings = get_settings()

# Override sqlalchemy.url from application settings
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
# target_metadata = Base.metadata  # uncomment when models are imported
target_metadata = None


# ─── Offline Migrations ──────────────────────────────────────
def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ─── Online Migrations (Async) ───────────────────────────────
def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations with an async database connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ─── Entry Point ─────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

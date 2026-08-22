"""
ITBIS — Application Settings
Centralised configuration using Pydantic Settings.
All values are loaded from environment variables / .env file.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide settings.
    All fields are loaded from environment variables.
    Sensitive fields must never have default values in production.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── Application ───────────────────────────────────────
    APP_NAME: str = "ITBIS"
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    FRONTEND_URL: str = "http://localhost:5173"

    # ─── Security ──────────────────────────────────────────
    SECRET_KEY: str = "INSECURE_CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── PostgreSQL ────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "itbis_db"
    POSTGRES_USER: str = "itbis_user"
    POSTGRES_PASSWORD: str = "itbis_dev_password"

    @property
    def database_url(self) -> str:
        """Async PostgreSQL connection string."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ─── MongoDB ───────────────────────────────────────────
    MONGO_HOST: str = "localhost"
    MONGO_PORT: int = 27017
    MONGO_DB: str = "itbis_events"
    MONGO_USER: str = "itbis_mongo_user"
    MONGO_PASSWORD: str = "itbis_dev_password"

    @property
    def mongo_url(self) -> str:
        """MongoDB connection string."""
        return (
            f"mongodb://{self.MONGO_USER}:{self.MONGO_PASSWORD}"
            f"@{self.MONGO_HOST}:{self.MONGO_PORT}/{self.MONGO_DB}"
        )

    # ─── Elasticsearch ─────────────────────────────────────
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_USER: str = "elastic"
    ELASTICSEARCH_PASSWORD: str = "itbis_dev_password"
    ELASTICSEARCH_INDEX_PREFIX: str = "itbis"

    # ─── Redis ─────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "itbis_dev_password"
    REDIS_DB: int = 0

    @property
    def redis_url(self) -> str:
        """Redis connection string."""
        return (
            f"redis://:{self.REDIS_PASSWORD}"
            f"@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        )

    # ─── Kafka ─────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_ACTIVITY_EVENTS: str = "itbis.activity.events"
    KAFKA_TOPIC_ALERTS: str = "itbis.alerts"
    KAFKA_CONSUMER_GROUP: str = "itbis-consumer-group"

    # ─── MinIO ─────────────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "itbis_minio_admin"
    MINIO_SECRET_KEY: str = "itbis_dev_password"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_EVIDENCE: str = "itbis-evidence"
    MINIO_BUCKET_REPORTS: str = "itbis-reports"
    MINIO_BUCKET_DATASETS: str = "itbis-datasets"

    # ─── TimescaleDB ───────────────────────────────────────
    TIMESCALE_HOST: str = "localhost"
    TIMESCALE_PORT: int = 5433
    TIMESCALE_DB: str = "itbis_timeseries"
    TIMESCALE_USER: str = "itbis_ts_user"
    TIMESCALE_PASSWORD: str = "itbis_dev_password"

    @property
    def timescale_url(self) -> str:
        """TimescaleDB connection string."""
        return (
            f"postgresql+asyncpg://{self.TIMESCALE_USER}:{self.TIMESCALE_PASSWORD}"
            f"@{self.TIMESCALE_HOST}:{self.TIMESCALE_PORT}/{self.TIMESCALE_DB}"
        )

    # ─── Logging ───────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE: str = "logs/itbis.log"

    # ─── CORS ──────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # ─── Rate Limiting ─────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # ─── ML / Anomaly Detection ────────────────────────────
    ISOLATION_FOREST_CONTAMINATION: float = 0.05
    ANOMALY_SCORE_THRESHOLD: float = 0.7
    BEHAVIORAL_BASELINE_DAYS: int = 30

    # ─── First Superadmin (seed) ───────────────────────────
    FIRST_SUPERADMIN_EMAIL: str = "admin@itbis-platform.com"  # Valid TLD for EmailStr
    FIRST_SUPERADMIN_PASSWORD: str = "Admin@ITBIS1"  # Must satisfy strength policy


@lru_cache
def get_settings() -> Settings:
    """
    Return cached Settings instance.
    Use FastAPI's Depends(get_settings) for dependency injection.
    """
    return Settings()

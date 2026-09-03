"""Shared test fixtures for the agent."""
from __future__ import annotations

import pytest

from itbis_agent.config import AgentConfig, Config, QueueConfig, ServerConfig, UploadConfig


@pytest.fixture
def tmp_queue_path(tmp_path) -> str:
    return str(tmp_path / "agent.db")


@pytest.fixture
def base_config(tmp_queue_path: str) -> Config:
    """A Config that points at a throwaway SQLite file."""
    return Config(
        agent=AgentConfig(
            device_id="TEST-DEVICE-001",
            device_name="Test Device",
            device_type="workstation",
            operating_system="Windows",
            source_dataset="win_endpoint",
            poll_interval_seconds=0.05,
            enabled_collectors=["mock"],
        ),
        server=ServerConfig(
            base_url="https://itbis.test",
            api_key="test-key",
            events_path="/api/v1/ingestion/events",
            verify_tls=False,
            timeout_seconds=5.0,
        ),
        queue=QueueConfig(db_path=tmp_queue_path, max_pending_events=1000),
        upload=UploadConfig(
            batch_size=10,
            flush_interval_seconds=0.5,
            max_retries=3,
            initial_backoff_seconds=0.05,
            max_backoff_seconds=1.0,
        ),
    )

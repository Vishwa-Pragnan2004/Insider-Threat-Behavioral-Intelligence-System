"""
Guard the agent's logging configuration.

Regression: configure_logging() paired structlog's PrintLoggerFactory with the
stdlib-only `add_logger_name` processor, so the first log call raised
`AttributeError: 'PrintLogger' object has no attribute 'name'` and the agent
CLI died on startup. No test exercised configure_logging, so it went unnoticed.
"""
from __future__ import annotations

import json

import pytest
import structlog

from itbis_agent.config import LoggingConfig
from itbis_agent.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog():
    yield
    structlog.reset_defaults()


@pytest.mark.parametrize("json_logs", [True, False])
def test_configured_logger_can_emit(json_logs, capsys):
    configure_logging(LoggingConfig(level="INFO", json_logs=json_logs))

    log = structlog.get_logger("itbis_agent.test")
    log.info("agent.start", agent_id="TEST-DEVICE-001")

    err = capsys.readouterr().err
    assert "agent.start" in err
    assert "TEST-DEVICE-001" in err


def test_json_output_is_structured(capsys):
    configure_logging(LoggingConfig(level="INFO", json_logs=True))

    structlog.get_logger("itbis_agent.test").warning("uploader.retry", attempts=2)

    record = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert record["event"] == "uploader.retry"
    assert record["level"] == "warning"
    assert record["attempts"] == 2
    assert "timestamp" in record


def test_level_filter_is_applied(capsys):
    configure_logging(LoggingConfig(level="WARNING", json_logs=True))

    log = structlog.get_logger("itbis_agent.test")
    log.info("should.not.appear")
    log.error("should.appear")

    err = capsys.readouterr().err
    assert "should.not.appear" not in err
    assert "should.appear" in err

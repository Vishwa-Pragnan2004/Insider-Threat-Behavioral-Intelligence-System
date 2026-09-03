"""
ITBIS — Unit tests for the CanonicalEvent schema.

Covers required fields, optional fields, and event_type enum values.
"""
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.shared.schemas.canonical_event import CanonicalEvent, EventType, RiskLevel


def test_canonical_event_minimum_required_fields():
    e = CanonicalEvent(
        event_type=EventType.LOGON,
        timestamp=datetime.now(UTC),
        user_id="alice",
        source_dataset="cert",
    )
    assert e.event_id is not None
    assert isinstance(e.event_id, uuid.UUID)
    assert e.user_id == "alice"
    assert e.risk_indicators == []  # default
    assert e.tags == []             # default


def test_canonical_event_serialises_to_json():
    e = CanonicalEvent(
        event_type=EventType.LOGON,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        user_id="alice",
        source_dataset="cert",
        device_id="PC1",
        target_resource="secret.docx",
        raw_payload={"foo": "bar"},
    )
    doc = e.model_dump(mode="json")
    assert doc["user_id"] == "alice"
    assert doc["device_id"] == "PC1"
    assert doc["raw_payload"]["foo"] == "bar"


def test_canonical_event_rejects_missing_required():
    with pytest.raises(ValidationError):
        CanonicalEvent()  # type: ignore[call-arg]


def test_canonical_event_all_event_types_importable():
    # Smoke check: every enum value is constructible
    for et in EventType:
        e = CanonicalEvent(
            event_type=et,
            timestamp=datetime.now(UTC),
            user_id="u",
            source_dataset="cert",
        )
        assert e.event_type is not None


def test_canonical_event_optional_metadata_fields():
    e = CanonicalEvent(
        event_type=EventType.FILE_UPLOAD,
        timestamp=datetime.now(UTC),
        user_id="u",
        source_dataset="cert",
        bytes_transferred=1024,
        file_count=3,
        risk_indicators=["after_hours", "external_destination"],
        risk_score=0.42,
        risk_level=RiskLevel.MEDIUM,
        tags=["file", "upload"],
    )
    assert e.bytes_transferred == 1024
    assert e.file_count == 3
    assert "after_hours" in e.risk_indicators
    assert e.risk_level == RiskLevel.MEDIUM

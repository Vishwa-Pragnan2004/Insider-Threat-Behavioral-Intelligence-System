"""
ITBIS — Shared Domain Tests
Unit tests for base entity and repository interface.
"""

import uuid

import pytest

from app.shared.domain.base_entity import BaseEntity


class ConcreteEntity(BaseEntity):
    """Minimal concrete entity for testing the base class."""

    def __init__(self, name: str, id: uuid.UUID | None = None):
        super().__init__(id=id)
        self.name = name


@pytest.mark.unit
class TestBaseEntity:
    """Unit tests for BaseEntity."""

    def test_entity_has_uuid(self):
        """Entity must be assigned a UUID on creation."""
        entity = ConcreteEntity(name="test")
        assert isinstance(entity.id, uuid.UUID)

    def test_entity_with_explicit_id(self):
        """Entity must use the provided ID if given."""
        fixed_id = uuid.uuid4()
        entity = ConcreteEntity(name="test", id=fixed_id)
        assert entity.id == fixed_id

    def test_two_entities_with_same_id_are_equal(self):
        """Two entities with the same ID must be equal."""
        fixed_id = uuid.uuid4()
        e1 = ConcreteEntity(name="foo", id=fixed_id)
        e2 = ConcreteEntity(name="bar", id=fixed_id)
        assert e1 == e2

    def test_two_entities_with_different_ids_are_not_equal(self):
        """Two entities with different IDs must not be equal."""
        e1 = ConcreteEntity(name="foo")
        e2 = ConcreteEntity(name="foo")
        assert e1 != e2

    def test_entity_has_created_at(self):
        """Entity must have a created_at timestamp."""
        entity = ConcreteEntity(name="test")
        assert entity.created_at is not None

    def test_entity_has_updated_at(self):
        """Entity must have an updated_at timestamp."""
        entity = ConcreteEntity(name="test")
        assert entity.updated_at is not None

    def test_domain_event_collection(self):
        """Entity must collect and return domain events."""
        entity = ConcreteEntity(name="test")
        event1 = {"type": "EntityCreated"}
        event2 = {"type": "EntityUpdated"}
        entity.add_domain_event(event1)
        entity.add_domain_event(event2)

        events = entity.collect_domain_events()
        assert len(events) == 2
        assert event1 in events
        assert event2 in events

    def test_domain_events_cleared_after_collection(self):
        """Domain events must be cleared after collect_domain_events() is called."""
        entity = ConcreteEntity(name="test")
        entity.add_domain_event({"type": "SomeEvent"})
        entity.collect_domain_events()
        events = entity.collect_domain_events()
        assert len(events) == 0

    def test_entity_repr(self):
        """Entity repr must include class name and id."""
        entity = ConcreteEntity(name="test")
        assert "ConcreteEntity" in repr(entity)
        assert str(entity.id) in repr(entity)

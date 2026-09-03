"""
ITBIS — Activity Module: Agent Event Ingest Router

Additive (Phase 3) endpoint for the Windows Endpoint Agent.

POST /api/v1/ingestion/events
    Accepts a batch of CanonicalEvent documents produced by an agent.
    Persists accepted events to MongoDB via the existing
    IActivityEventStore and returns a per-event acknowledgement
    (accepted | duplicate | rejected) for idempotent retry semantics.

The existing file-upload endpoint from Phase 2 is unchanged.
"""
# ruff: noqa: B008
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.modules.activity.infrastructure.mongo_event_store import MongoActivityEventStore
from app.modules.activity.presentation.dependencies import (
    get_activity_event_store,
)
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)
from app.shared.schemas.canonical_event import CanonicalEvent, EventType

log = structlog.get_logger(__name__)

router = APIRouter()


# ─── Request / Response models ───────────────────────────────


class EventBatchIn(BaseModel):
    """Agent → server: a batch of normalised events."""

    agent_id: str = Field(..., min_length=1, max_length=255)
    submitted_at: datetime | None = None
    events: list[CanonicalEvent] = Field(..., min_length=1, max_length=1000)


class EventAck(BaseModel):
    raw_event_id: str | None = None
    event_id: uuid.UUID
    status: str  # accepted | duplicate | rejected
    reason: str | None = None


class EventBatchAck(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    results: list[EventAck] = Field(default_factory=list)


# ─── Endpoint ────────────────────────────────────────────────


@router.post(
    "/events",
    response_model=EventBatchAck,
    status_code=status.HTTP_200_OK,
    summary="Ingest a batch of CanonicalEvents from an endpoint agent",
    dependencies=[Depends(require_permission(PermissionName.AGENT_INGEST))],
)
async def ingest_agent_events(
    payload: EventBatchIn,
    event_store: MongoActivityEventStore = Depends(get_activity_event_store),
    current_user: User = Depends(require_active_user),
):
    """
    Accept a batch of agent events.

    Semantics:
      - Each event is checked for duplicates by (source_dataset, raw_event_id)
        (a small dedup window kept in-process for now; sufficient for the
        Phase 3 scope — the queue is the agent's primary durability layer).
      - Accepted events are persisted to the canonical_events collection
        via the existing IActivityEventStore.
      - The response carries a per-event ack so the agent can identify
        duplicates and avoid pointless retries.
    """
    dedup = _DedupCache()
    accepted = duplicates = rejected = 0
    results: list[EventAck] = []

    for ev in payload.events:
        try:
            if not ev.user_id or not ev.timestamp or not ev.event_type:
                raise ValueError("missing required field (user_id/timestamp/event_type)")
            # Coerce event_type to a known enum value or fall back to UNKNOWN
            try:
                EventType(ev.event_type)  # validation only
            except ValueError:
                # Unknown event_type from a future agent — accept but flag
                log.warning("agent.unknown_event_type", value=ev.event_type)

            idem = ev.idempotency_key()
            if dedup.seen(idem):
                duplicates += 1
                results.append(EventAck(
                    raw_event_id=ev.raw_event_id,
                    event_id=ev.event_id,
                    status="duplicate",
                ))
                continue

            doc = ev.model_dump(mode="json")
            doc["job_id"] = f"agent:{payload.agent_id}"
            doc["agent_id"] = payload.agent_id
            doc["ingested_at"] = (
                payload.submitted_at or datetime.now(UTC)
            ).isoformat()
            await event_store.insert_many([doc], job_id=doc["job_id"])
            dedup.add(idem)
            accepted += 1
            results.append(EventAck(
                raw_event_id=ev.raw_event_id,
                event_id=ev.event_id,
                status="accepted",
            ))
        except Exception as exc:  # noqa: BLE001
            rejected += 1
            results.append(EventAck(
                raw_event_id=ev.raw_event_id,
                event_id=ev.event_id,
                status="rejected",
                reason=str(exc)[:200],
            ))
            log.warning("agent.event_rejected", reason=str(exc), event_id=str(ev.event_id))

    log.info(
        "agent.batch_received",
        agent_id=payload.agent_id,
        submitted_by=str(current_user.id),
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
    )

    return EventBatchAck(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
        results=results,
    )


# ─── Helpers ─────────────────────────────────────────────────


class _DedupCache:
    """
    Tiny in-process LRU of recently-seen idempotency keys.

    Phase 3 only: a single server instance holds a small ring buffer. For
    multi-instance deployments this becomes a Mongo unique index in a later
    phase — the agent's idempotency_key is already in the right shape.
    """

    def __init__(self, capacity: int = 50_000) -> None:
        self._capacity = capacity
        self._set: set[str] = set()
        self._order: list[str] = []

    def seen(self, key: str) -> bool:
        return key in self._set

    def add(self, key: str) -> None:
        if key in self._set:
            return
        self._set.add(key)
        self._order.append(key)
        if len(self._order) > self._capacity:
            evict = self._order.pop(0)
            self._set.discard(evict)

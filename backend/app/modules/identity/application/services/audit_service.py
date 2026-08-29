"""
ITBIS — Identity Module: Audit Service
Handles persistence of authentication audit events.
"""

import structlog

from app.modules.identity.domain.events import AuthAuditEvent

logger = structlog.get_logger(__name__)


class AuditService:
    """
    Service for writing audit events.
    In a full CQRS system, this would publish to an event bus.
    For this phase, it will write to the local PostgreSQL database via an ORM model
    and emit a structured log.
    """

    # We will inject the DB session in the use cases and pass it here,
    # but for simplicity, we abstract the "logging" part.

    async def log_event(self, event: AuthAuditEvent) -> None:
        """
        Log the event to structured logging (stdout/file).
        The actual DB persistence is handled in the Use Cases via the ORM
        so it shares the same Unit of Work as the user state change.
        """
        # Ensure we never log sensitive data. The dataclass itself
        # doesn't contain passwords, but we are explicit.
        log_kwargs = {
            "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat(),
            "user_id": str(event.user_id) if event.user_id else None,
            "username": event.username,
            "ip_address": event.ip_address,
            "success": event.success,
        }
        
        if not event.success:
            log_kwargs["failure_reason"] = event.failure_reason

        logger.info("auth_audit_event", **log_kwargs)


# ─── Module-level singleton ───────────────────────────────────
audit_service = AuditService()

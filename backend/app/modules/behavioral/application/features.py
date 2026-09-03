"""
ITBIS — Behavioral Module: Feature Definitions

Single source of truth for the feature names, types, and aggregation rules
used by both the server-side feature engineering pipeline and the
eventual Kaggle training notebook.

The expected Kaggle training workflow:

    from app.modules.behavioral.application.features import FEATURE_DEFINITIONS
    import pandas as pd
    df = pd.DataFrame(rows)            # rows from BehavioralFeatures.features
    df = df[FEATURE_DEFINITIONS.names()]  # lock column order
    X = df.values.astype('float32')

No new columns may be added or removed without bumping `FEATURE_VERSION`
in domain/enums.py.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.modules.behavioral.domain.enums import FEATURE_NAMES
from app.shared.schemas.canonical_event import EventType

# ─── Per-event classification helpers ────────────────────────
#
# These classify a single CanonicalEvent into the buckets the daily
# aggregator counts.  Every helper takes the event's dict-form (as stored
# in Mongo) and returns a boolean.  This keeps the per-event logic
# trivially testable.

def _is(ev: dict, event_type: str) -> bool:
    return ev.get("event_type") == event_type


def _ev_type(ev: dict) -> str:
    return (ev.get("event_type") or "").lower()


def is_logon(ev: dict) -> bool:
    return _is(ev, EventType.LOGON.value)


def is_failed_logon(ev: dict) -> bool:
    return _is(ev, EventType.LOGON_FAILED.value)


def is_file_activity(ev: dict) -> bool:
    et = _ev_type(ev)
    return et.startswith("file_")


def is_file_copy(ev: dict) -> bool:
    return _is(ev, EventType.FILE_COPY.value)


def is_usb_activity(ev: dict) -> bool:
    et = _ev_type(ev)
    return et.startswith("usb_")


def is_email(ev: dict) -> bool:
    et = _ev_type(ev)
    return et.startswith("email_")


def is_external_email(ev: dict) -> bool:
    """An email is external if explicitly tagged external, or typed EMAIL_EXTERNAL."""
    if _is(ev, EventType.EMAIL_EXTERNAL.value):
        return True
    indicators = ev.get("risk_indicators") or []
    return "external_email" in indicators


def is_http_activity(ev: dict) -> bool:
    et = _ev_type(ev)
    return et.startswith("http_")


def is_ldap_activity(ev: dict) -> bool:
    et = _ev_type(ev)
    return et in {
        EventType.LDAP_QUERY.value,
        EventType.PRIVILEGE_CHANGE.value,
        EventType.GROUP_CHANGE.value,
        EventType.ACCOUNT_CREATED.value,
        EventType.ACCOUNT_DISABLED.value,
        EventType.PASSWORD_CHANGE.value,
    }


def is_process_activity(ev: dict) -> bool:
    et = _ev_type(ev)
    return et in {
        EventType.APP_LAUNCH.value,
        EventType.APP_CLOSE.value,
        EventType.APP_INSTALL.value,
    }


# ─── Feature definitions ─────────────────────────────────────


@dataclass(frozen=True)
class FeatureDefinition:
    """A single feature definition."""

    name: str
    description: str
    aggregator: str                # "count" | "distinct" | "set_size" | "event_match"
    # For event_match features, the per-event classifier function
    event_match: Callable[[dict], bool] | None = None
    # Distinct field name for "distinct" / "set_size" aggregators
    field: str | None = None


FEATURE_DEFINITIONS: dict[str, FeatureDefinition] = {
    "total_activity_count": FeatureDefinition(
        name="total_activity_count",
        description="Total count of canonical events in the window.",
        aggregator="count",
    ),
    "logon_count": FeatureDefinition(
        name="logon_count",
        description="Count of successful logon events.",
        aggregator="event_match",
        event_match=is_logon,
    ),
    "failed_logon_count": FeatureDefinition(
        name="failed_logon_count",
        description="Count of failed logon events.",
        aggregator="event_match",
        event_match=is_failed_logon,
    ),
    "after_hours_activity_count": FeatureDefinition(
        name="after_hours_activity_count",
        description=(
            "Count of events outside the working-hours window "
            "(08:00–18:00 local).  Phase 4 uses UTC; Phase 5+ may add "
            "per-user timezone awareness."
        ),
        aggregator="event_match",
        event_match=lambda ev: _is_after_hours(ev),
    ),
    "unique_active_hours": FeatureDefinition(
        name="unique_active_hours",
        description="Number of distinct hour-of-day buckets (0-23) the user was active in.",
        aggregator="set_size",
        field="hour_of_day",
    ),
    "unique_device_count": FeatureDefinition(
        name="unique_device_count",
        description="Number of distinct device_ids touched in the window.",
        aggregator="set_size",
        field="device_id",
    ),
    "unique_resource_count": FeatureDefinition(
        name="unique_resource_count",
        description="Number of distinct target_resource values touched.",
        aggregator="set_size",
        field="target_resource",
    ),
    "file_activity_count": FeatureDefinition(
        name="file_activity_count",
        description="Count of file_* events.",
        aggregator="event_match",
        event_match=is_file_activity,
    ),
    "file_copy_count": FeatureDefinition(
        name="file_copy_count",
        description="Count of file_copy events.",
        aggregator="event_match",
        event_match=is_file_copy,
    ),
    "usb_activity_count": FeatureDefinition(
        name="usb_activity_count",
        description="Count of usb_* events.",
        aggregator="event_match",
        event_match=is_usb_activity,
    ),
    "email_count": FeatureDefinition(
        name="email_count",
        description="Count of email_* events.",
        aggregator="event_match",
        event_match=is_email,
    ),
    "external_email_count": FeatureDefinition(
        name="external_email_count",
        description="Count of email events flagged as external.",
        aggregator="event_match",
        event_match=is_external_email,
    ),
    "http_activity_count": FeatureDefinition(
        name="http_activity_count",
        description="Count of http_* events.",
        aggregator="event_match",
        event_match=is_http_activity,
    ),
    "ldap_activity_count": FeatureDefinition(
        name="ldap_activity_count",
        description="Count of LDAP/AD/privilege-change events.",
        aggregator="event_match",
        event_match=is_ldap_activity,
    ),
    "process_activity_count": FeatureDefinition(
        name="process_activity_count",
        description="Count of process/application launch events.",
        aggregator="event_match",
        event_match=is_process_activity,
    ),
    "activity_type_diversity": FeatureDefinition(
        name="activity_type_diversity",
        description="Number of distinct event_type values observed.",
        aggregator="set_size",
        field="event_type",
    ),
}


def feature_names() -> list[str]:
    """Canonical feature name list in stable order (matches FEATURE_NAMES)."""
    # Use FEATURE_NAMES as the source of order; assert all are defined.
    for n in FEATURE_NAMES:
        if n not in FEATURE_DEFINITIONS:
            raise RuntimeError(
                f"Feature {n!r} declared in FEATURE_NAMES but missing from "
                f"FEATURE_DEFINITIONS.  This indicates a version-skew bug."
            )
    return list(FEATURE_NAMES)


# ─── Per-event field extraction ──────────────────────────────


WORK_HOUR_START = 8
WORK_HOUR_END = 18   # exclusive


def _is_after_hours(ev: dict) -> bool:
    """Return True if the event's timestamp falls outside 08:00-18:00."""
    from datetime import datetime

    ts = ev.get("timestamp")
    if not ts:
        return False
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return False
    hour = ts.hour
    return hour < WORK_HOUR_START or hour >= WORK_HOUR_END


def event_field(ev: dict, field_name: str):
    """Extract a comparable per-event field for `set_size` aggregation."""
    if field_name == "hour_of_day":
        from datetime import datetime
        ts = ev.get("timestamp")
        if not ts:
            return None
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return None
        return ts.hour
    if field_name == "device_id":
        v = ev.get("device_id")
        return v if v else None
    if field_name == "target_resource":
        v = ev.get("target_resource")
        return v if v else None
    if field_name == "event_type":
        return ev.get("event_type")
    raise KeyError(f"Unknown field for set_size aggregation: {field_name!r}")

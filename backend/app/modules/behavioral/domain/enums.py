"""
ITBIS — Behavioral Module: Domain Enums
"""
from enum import Enum


class FeatureWindow(str, Enum):
    """Supported aggregation windows for behavioral features."""

    DAILY = "daily"
    ROLLING_7D = "rolling_7d"
    ROLLING_30D = "rolling_30d"


# ─── Canonical feature set (versioned) ─────────────────────
#
# These names are the wire contract between the feature pipeline,
# downstream ML training (Kaggle notebook), and live inference.
# They MUST NOT change without bumping FEATURE_VERSION.
#
# Each feature is documented in docs/behavioral_features.md (Phase 4).

FEATURE_NAMES: list[str] = [
    "total_activity_count",
    "logon_count",
    "failed_logon_count",
    "after_hours_activity_count",
    "unique_active_hours",
    "unique_device_count",
    "unique_resource_count",
    "file_activity_count",
    "file_copy_count",
    "usb_activity_count",
    "email_count",
    "external_email_count",
    "http_activity_count",
    "ldap_activity_count",
    "process_activity_count",
    "activity_type_diversity",
]

# Current version of the feature set.  Bump when adding, removing, or
# changing the semantic of any feature in FEATURE_NAMES.
FEATURE_VERSION = "behavioral_features_v1"

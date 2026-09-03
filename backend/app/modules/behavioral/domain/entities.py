"""
ITBIS — Behavioral Module: Domain Entities
"""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ─── Behavioral Features ────────────────────────────────────


@dataclass
class BehavioralFeatures:
    """
    One row of behavioral features for a single (user, window, day).

    `features` is a flat dict keyed by names from
    `app.modules.behavioral.domain.enums.FEATURE_NAMES`.  All values are
    numeric (int or float) so the dict is directly consumable by a pandas
    DataFrame for ML training.
    """

    user_id: str
    window: str                # "daily" | "rolling_7d" | "rolling_30d"
    window_start: datetime     # inclusive UTC
    window_end: datetime       # exclusive UTC
    source_dataset: str        # "cert" | "win_endpoint" | "all"
    features: dict[str, float] = field(default_factory=dict)
    feature_version: str = "behavioral_features_v1"
    event_count: int = 0       # number of canonical events the features were built from
    generated_at: datetime = field(default_factory=_utcnow)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


# ─── Behavioral Baseline ────────────────────────────────────


@dataclass
class BehavioralBaseline:
    """
    Per-user baseline describing normal behavioural distributions.

    The baseline stores per-feature mean and standard deviation over a
    historical observation window.  It is built from data strictly BEFORE
    the evaluation period to prevent future-data leakage.
    """

    user_id: str
    feature_version: str
    stats: dict[str, dict[str, float]]
    window_start: datetime              # historical window start (inclusive)
    window_end: datetime                # historical window end (exclusive)
    observation_days: int
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    source_dataset: str = "all"

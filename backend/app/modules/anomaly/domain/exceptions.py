"""
ITBIS — Anomaly Module: Domain Exceptions
"""


class AnomalyError(Exception):
    """Base error for the anomaly module."""


class ModelLoadError(AnomalyError):
    """The .joblib artifact could not be loaded or is malformed."""


class FeatureIncompatibilityError(AnomalyError):
    """The Phase 4 feature pipeline is incompatible with the loaded model.

    E.g. the 16 base features are missing or in a different order from
    what the model was trained on.
    """


class ModelNotLoadedError(AnomalyError):
    """Inference was attempted before the model artifact was loaded."""


class NoDataForDetectionError(AnomalyError):
    """No Phase 4 feature rows available for the requested (user, window)."""

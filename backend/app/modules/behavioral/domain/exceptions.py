"""
ITBIS — Behavioral Module: Domain Exceptions
"""


class BehavioralError(Exception):
    """Base error for the behavioral module."""


class NoDataForBaselineError(BehavioralError):
    """No historical events found when building a baseline for a user."""


class FeatureVersionMismatchError(BehavioralError):
    """Feature version mismatch between features and the requested baseline."""

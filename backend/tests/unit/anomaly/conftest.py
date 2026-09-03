"""
ITBIS — Anomaly module test fixtures.

Set the ITBIS_MODEL_PATH env var before any test module imports the
ModelService (which captures the path at import time).
"""
import os
from pathlib import Path

# Project2/ root: tests/unit/anomaly/ -> tests/unit -> tests -> backend -> project2
PROJECT_ROOT = Path(__file__).resolve().parents[4]
os.environ.setdefault(
    "ITBIS_MODEL_PATH",
    str(PROJECT_ROOT / "ml_model" / "itbis_behavior_model_v2.joblib"),
)

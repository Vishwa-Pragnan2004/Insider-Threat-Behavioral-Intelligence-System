"""
Point the anomaly model at the repository's artifact before test modules import
helpers from the anomaly tests (which read ITBIS_MODEL_PATH at import time).
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]

os.environ.setdefault(
    "ITBIS_MODEL_PATH",
    str(PROJECT_ROOT / "ml_model" / "itbis_behavior_model_v3.joblib"),
)

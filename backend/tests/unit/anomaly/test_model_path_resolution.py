"""
Guard the model artifact path.

Both the training service and the serving path used to default to the
CWD-relative "./ml_model/...".  Starting uvicorn from backend/ therefore
loaded a different artifact than starting it from the repo root, and training
run from backend/ wrote a second model the server never read.  That is how a
90-row throwaway ended up shadowing the real CERT-trained model.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def unpatched_paths(monkeypatch):
    """Re-import the modules with ITBIS_MODEL_PATH unset."""
    monkeypatch.delenv("ITBIS_MODEL_PATH", raising=False)
    import importlib

    import app.modules.anomaly.application.model_service as ms
    import app.modules.anomaly.application.model_training_service as mts

    importlib.reload(ms)
    importlib.reload(mts)
    yield ms, mts
    # Restore module state for the rest of the session.
    monkeypatch.setenv("ITBIS_MODEL_PATH", os.environ.get("ITBIS_MODEL_PATH", ""))
    importlib.reload(ms)
    importlib.reload(mts)


def test_training_and_serving_resolve_to_the_same_artifact(unpatched_paths):
    ms, mts = unpatched_paths
    assert mts.DEFAULT_OUTPUT_PATH == ms.DEFAULT_ARTIFACT_PATH


def test_default_path_is_absolute(unpatched_paths):
    """An absolute path is what makes the resolution CWD-independent."""
    ms, _ = unpatched_paths
    assert Path(ms.DEFAULT_ARTIFACT_PATH).is_absolute()


def test_default_path_points_at_the_repo_ml_model_dir(unpatched_paths):
    ms, _ = unpatched_paths
    resolved = Path(ms.DEFAULT_ARTIFACT_PATH)
    assert resolved.parent.name == "ml_model"
    assert resolved.name == "itbis_behavior_model_v2.joblib"
    # The checked-in artifact must actually be there.
    assert resolved.is_file(), f"model artifact missing at {resolved}"


def test_env_var_still_overrides(monkeypatch, tmp_path):
    import importlib

    import app.modules.anomaly.application.model_service as ms

    custom = tmp_path / "custom.joblib"
    monkeypatch.setenv("ITBIS_MODEL_PATH", str(custom))
    importlib.reload(ms)
    try:
        assert ms.DEFAULT_ARTIFACT_PATH == str(custom)
    finally:
        importlib.reload(ms)

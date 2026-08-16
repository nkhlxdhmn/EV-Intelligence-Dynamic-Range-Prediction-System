"""
STEP 11I - MODEL VERSIONING / METADATA.

Metadata only. This module NEVER alters the frozen model, preprocessor, or
feature list. It only reads the frozen artifacts and reports their identity.

Version string: ev-energy-devrt-v1
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib

PROJECT_ROOT = Path(__file__).parent.parent.parent
MODELS = PROJECT_ROOT / "models"

MODEL_VERSION = "ev-energy-devrt-v1"
TRAINING_DATASET = "DEVRT"
TARGET = "target_future_energy_kwh_per_km"
HORIZON_KM = 5
ROUTE_AWARE = True

# Frozen DEVRT hold-out performance (Step 8, evaluated exactly once).
# Stored as metadata only; the test is never re-evaluated.
TEST_MAE = 0.04112
TEST_RMSE = 0.05236
TEST_R2 = 0.5902
BASELINE_MAE = 0.06187
BASELINE_IMPROVEMENT_PCT = 33.5


class ModelMetadata:
    """Read-only identity of the frozen model artifacts."""

    def __init__(self, models_dir: Path | None = None):
        self.models_dir = models_dir or MODELS
        self.model_path = self.models_dir / "ev_energy_extratrees_route_aware.joblib"
        self.preprocessor_path = self.models_dir / "final_preprocessor.joblib"
        self.feature_list_path = self.models_dir / "final_feature_list.json"
        self._model = None
        self._features: list[str] | None = None

    # -- lazy loads ---------------------------------------------------------
    def load_model(self):
        if self._model is None:
            self._model = joblib.load(self.model_path)
        return self._model

    def features(self) -> list[str]:
        if self._features is None:
            self._features = json.loads(
                self.feature_list_path.read_text(encoding="utf-8"))
        return list(self._features)

    # -- identity -----------------------------------------------------------
    def model_type(self) -> str:
        return type(self.load_model()).__name__

    @property
    def model_version(self) -> str:
        return MODEL_VERSION

    def feature_count(self) -> int:
        return len(self.features())

    def n_features_in(self) -> int:
        return getattr(self.load_model(), "n_features_in_", None)

    def preprocessor_type(self) -> str:
        return type(joblib.load(self.preprocessor_path)).__name__

    # -- full metadata dict -------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "model_version": MODEL_VERSION,
            "model": self.model_type(),
            "preprocessor": self.preprocessor_type(),
            "training_dataset": TRAINING_DATASET,
            "target": TARGET,
            "horizon_km": HORIZON_KM,
            "route_aware": ROUTE_AWARE,
            "feature_count": self.feature_count(),
            "n_features_in_": self.n_features_in(),
            "created_at": "2026-08-16 (frozen Step 8 artifacts)",
            "test_mae": TEST_MAE,
            "test_rmse": TEST_RMSE,
            "test_r2": TEST_R2,
            "baseline_mae": BASELINE_MAE,
            "baseline_improvement_pct": BASELINE_IMPROVEMENT_PCT,
        }

    def model_info(self) -> dict:
        """/model/info response payload (no filesystem paths, no internals)."""
        d = self.to_dict()
        return {
            "model": d["model"],
            "feature_count": d["feature_count"],
            "target": d["target"],
            "horizon_km": d["horizon_km"],
            "dataset": d["training_dataset"],
            "route_aware": d["route_aware"],
            "model_version": d["model_version"],
        }


def load_model_metadata(models_dir: Path | None = None) -> ModelMetadata:
    """Convenience factory."""
    return ModelMetadata(models_dir=models_dir)


if __name__ == "__main__":
    md = load_model_metadata()
    print(json.dumps(md.to_dict(), indent=2))
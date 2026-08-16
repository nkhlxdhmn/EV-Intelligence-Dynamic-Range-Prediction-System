"""
STEP 9I - DYNAMIC PREDICTION PIPELINE

    vehicle telemetry (standardized trip df)
        -> feature generation (engineer_trip)
        -> 102 route-aware features
        -> frozen ExtraTrees model
        -> predicted energy consumption (kWh/km)
        -> range estimator
        -> estimated remaining range

The pipeline reuses the exact feature engineering used to build the training
data (scripts.comprehensive_feature_engineering.engineer_trip) and the exact
frozen artifacts from Step 8 (model, preprocessor, feature list). It only
predicts; it never trains, never touches test data, and never writes model
artifacts.

Memory-safe: operates one trip at a time; no raw DEVRT files are loaded.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
MODELS = PROJECT_ROOT / 'models'
TARGET = 'target_future_energy_kwh_per_km'


class EvEnergyPredictor:
    """Frozen route-aware consumption predictor + range estimator."""

    def __init__(self, models_dir: Path | None = None,
                 reserve_soc_pct: float = 10.0):
        models_dir = models_dir or MODELS
        self.model = joblib.load(models_dir / 'ev_energy_extratrees_route_aware.joblib')
        self.imputer = joblib.load(models_dir / 'final_preprocessor.joblib')
        self.features = json.loads(
            (models_dir / 'final_feature_list.json').read_text(encoding='utf-8'))

        from src.inference.range_estimator import RangeEstimator
        self.range_estimator = RangeEstimator(reserve_soc_pct=reserve_soc_pct)

    def engineer_features(self, trip_df: pd.DataFrame) -> pd.DataFrame:
        """Generate the full feature matrix for one standardized trip."""
        from scripts.comprehensive_feature_engineering import engineer_trip
        feats = engineer_trip(trip_df)
        # keep only the frozen 102 features, in the exact training order
        missing = [f for f in self.features if f not in feats.columns]
        if missing:
            raise ValueError(f'missing frozen features after engineering: {missing}')
        return feats[self.features].copy()

    def predict_kwh_per_km(self, trip_df: pd.DataFrame) -> np.ndarray:
        """Predict future energy consumption (kWh/km over the next 5 km)."""
        X = self.engineer_features(trip_df).to_numpy(dtype=float)
        X = self.imputer.transform(X)
        return self.model.predict(X)

    def predict_range(self, trip_df: pd.DataFrame, battery_capacity_kwh: float,
                      soc_pct: float,
                      residual_q_low: float | None = None,
                      residual_q_high: float | None = None,
                      reserve_soc_pct: float | None = None) -> dict:
        """Predict consumption and estimate remaining range per row."""
        pred = self.predict_kwh_per_km(trip_df)
        est = self.range_estimator
        if reserve_soc_pct is not None:
            from src.inference.range_estimator import RangeEstimator
            est = RangeEstimator(reserve_soc_pct=reserve_soc_pct)

        out = []
        for p in pred:
            row = {'predicted_energy_kwh_per_km': p}
            if not (p > 0) or not np.isfinite(p):
                # Negative/zero consumption is regen-gain signal; range is not
                # defined for it (estimator rejects consumption <= 0).
                row.update({'usable_energy_kwh': None,
                            'estimated_range_km': None,
                            'conservative_range_km': None,
                            'expected_range_km': None,
                            'optimistic_range_km': None,
                            'range_skipped_reason':
                                'predicted consumption <= 0 (regen gain)'})
                out.append(row)
                continue
            if residual_q_low is not None and residual_q_high is not None:
                r = est.estimate_range_band(battery_capacity_kwh, soc_pct, p,
                                            residual_q_low, residual_q_high)
            else:
                r = est.estimate_range(battery_capacity_kwh, soc_pct, p)
            r['predicted_energy_kwh_per_km'] = p
            out.append(r)
        return out


def load_residual_quantiles(path: Path | None = None) -> dict:
    """Load model residual quantiles computed on TRAIN+VALIDATION only."""
    path = path or (PROJECT_ROOT / 'reports' / 'step9_trainval_residual_quantiles.json')
    return json.loads(path.read_text(encoding='utf-8'))
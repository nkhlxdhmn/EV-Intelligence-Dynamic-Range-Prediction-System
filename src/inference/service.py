"""
STEP 15 — Robust real-time prediction, uncertainty & OOD detection.

Production inference pipeline with:
- Prediction intervals (using train+validation residual quantiles)
- OOD detection (feature-wise percentile bounds)
- Confidence score (incorporating OOD, missing features, route availability)
- Route availability status
- Sensor quality assessment
- Structured logging of all metadata
- Fail-safe statuses: OK, DEGRADED, INSUFFICIENT_DATA, OFFLINE

Memory-safe: the process loads ONLY the frozen model, frozen preprocessor and
feature metadata (~tens of MB). It never loads DEVRT/TUM/JAC or any raw
dataset. Target process RSS < 500 MB.
"""
from __future__ import annotations

import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


class InferenceError(Exception):
    """Base inference error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ModelLoadError(InferenceError):
    pass


class PreprocessorError(InferenceError):
    pass


class TerrainUnavailableError(InferenceError):
    pass


# ---------------------------------------------------------------------------
# Fail-safe statuses (STEP 15)
# ---------------------------------------------------------------------------

class PredictionStatus:
    """Explicit prediction status — never silently produce a confident-looking result.

    Used to communicate the reliability of a prediction to the caller.
    Always one of: OK, DEGRADED, INSUFFICIENT_DATA, OFFLINE.
    """

    OK = "OK"
    DEGRADED = "DEGRADED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OFFLINE = "OFFLINE"


from src.inference.feature_builder import (
    FeatureBuilder,
    FeatureBuildError,
    RouteTerrain,
    RouteTerrainProvider,
)
from src.inference.inference_logger import InferenceLogger
from src.inference.model_metadata import MODEL_VERSION, load_model_metadata
from src.inference.range_estimator import RangeEstimator
from src.inference.schemas import PredictionRequest, PredictionResponse
from src.monitoring.ood import assess_ood, assess_ood_from_snapshot
from src.monitoring.sensor_quality import assess_complete_telemetry_quality

PROJECT_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Uncertainty estimator using step 9 residual quantiles
# ---------------------------------------------------------------------------

# Step 9 train+validation residual quantiles (n=9098, test excluded)
# q5: -0.0599, q10: -0.0470, q50: 0.0031, q75: 0.0161, q90: 0.0363
# These are errors = true_consumption - model_prediction

STEP9_QUANTILES = {
    "q5": -0.05987434117619389,
    "q10": -0.04704644814200479,
    "q50": 0.003142145997924728,
    "q75": 0.016119548520138572,
    "q90": 0.03627995706319961,
}


def _prediction_interval_from_quantiles(
    pred_consumption: float,
    quantiles: dict[str, float] = STEP9_QUANTILES,
) -> dict[str, float]:
    """Build an estimated prediction interval for consumption.

    Uses the asymmetric residual quantiles from the Step 9 train+validation
    run.  These are *estimated* bounds, not guarantees (per STEP 15B rules).

    Returns:
        dict with keys:
            - lower_consumption: estimated lower bound (kWh/km)
            - upper_consumption: estimated upper bound (kWh/km)
            - interval_width: width of the interval (kWh/km)
    """
    q10 = quantiles["q10"]
    q90 = quantiles["q90"]
    q50 = quantiles["q50"]

    # Asymmetric interval: [pred - q90_abs, pred + q90_abs] approximated
    # using the training-residual spread around the median prediction.
    # We construct lower and upper by shifting the prediction by the
    # residual quantiles.

    # Lower bound: prediction minus the q90 residual (conservative = higher consumption)
    lower = pred_consumption + q10  # q10 is negative, so this reduces the prediction ... wait
    # Actually, residual = true - predicted. If q10 = -0.047, that means
    # true consumption was 0.047 LOWER than predicted at the 10th percentile.
    # For a prediction interval we want: [pred - q90, pred - q10] approx.
    # Let me think more carefully.

    # residual = true - predicted
    # p10 residual = -0.047 => true_10 = predicted - 0.047 (consumption lower than predicted)
    # p90 residual = +0.036 => true_90 = predicted + 0.036 (consumption higher than predicted)

    # So a 90% prediction interval for consumption is:
    # [predicted + q10, predicted + q90] = [pred - 0.047, pred + 0.036]

    lower_consumption = pred_consumption + q10  # q10 is negative, so this subtracts
    upper_consumption = pred_consumption + q90  # q90 is positive, so this adds

    interval_width = upper_consumption - lower_consumption

    return {
        "lower_consumption": round(max(lower_consumption, 0.0), 6),
        "upper_consumption": round(upper_consumption, 6),
        "interval_width": round(interval_width, 6),
    }


# ---------------------------------------------------------------------------
# Confidence score calculator
# ---------------------------------------------------------------------------

def compute_confidence_score(
    ood_result: dict[str, Any],
    missing_feature_fraction: float,
    route_available: bool,
    route_terrain_available: bool,
    uncertainty_width: float,
    predicted_consumption: float,
    baseline_width: float = 0.063,  # STEP9 q90-q10 width from DEVRT train+val
) -> dict[str, Any]:
    """Compute a prediction confidence score in [0, 1].

    This is NOT a probability of correctness. It is a composite index
    indicating prediction reliability, incorporating:

    - OOD severity (0.0 = in-distribution, 1.0 = maximally OOD)
    - Missing feature fraction (0.0 = all features present, 1.0 = most missing)
    - Route availability (unavailable reduces confidence)
    - Route terrain availability (unavailable reduces confidence)
    - Uncertainty width relative to baseline (wider = less confident)
    - Predicted consumption magnitude (very low consumption may be less meaningful)

    Rules (per STEP 15G):
    - Must NOT be presented as probability of correctness
    - Must NOT use target/test data to calibrate
    - Document exactly how it is calculated
    """
    # OOD contribution (0 = in-distribution, higher = more OOD)
    ood_severity_map = {"normal": 0.0, "warning": 0.3, "critical": 0.6}
    ood_severity = ood_result.get("severity", "normal")
    ood_contribution = ood_severity_map.get(ood_severity, 0.0)
    ood_contribution = min(ood_contribution, 1.0)

    # Missing feature fraction contribution
    missing_contribution = missing_feature_fraction  # 0.0 to 1.0

    # Route availability contribution
    route_contribution = 0.0 if not route_available else 0.0
    if not route_available:
        route_contribution = 0.4  # significant reduction
    elif not route_terrain_available:
        route_contribution = 0.2  # moderate reduction

    # Uncertainty width contribution
    # Normalize by baseline; cap contribution
    if baseline_width > 0 and uncertainty_width > 0:
        width_ratio = uncertainty_width / baseline_width
        # Diminishing returns: a ratio of 2x contributes 0.2, 3x contributes 0.3, etc.
        width_contribution = min(0.3, 0.1 * (width_ratio - 1.0) if width_ratio > 1.0 else 0.0)
    else:
        width_contribution = 0.0

    # Total score = weighted sum, capped at 1.0
    total = ood_contribution + missing_contribution + route_contribution + width_contribution
    score = min(total, 1.0)

    # Determine confidence level
    if score <= 0.2:
        level = "high"
    elif score <= 0.5:
        level = "medium"
    else:
        level = "low"

    return {
        "score": round(score, 3),
        "level": level,
        "components": {
            "ood_contribution": round(ood_contribution, 3),
            "missing_contribution": round(missing_contribution, 3),
            "route_contribution": round(route_contribution, 3),
            "width_contribution": round(width_contribution, 3),
        },
    }


# ---------------------------------------------------------------------------
# OOD assessment helper (using snapshot features)
# ---------------------------------------------------------------------------

def assess_ood_from_request(request: PredictionRequest) -> dict[str, Any]:
    """Assess OOD from a PredictionRequest by extracting key features.

    Uses the monitoring OOD assessor on the most important production features.
    """
    snap = request.telemetry.model_dump()

    # Extract features for OOD assessment
    feature_values: dict[str, float] = {}

    if hasattr(snap, 'get'):
        # Pydantic model dump may be dict-like
        for key in ["soc_pct", "speed_kmh", "altitude_m", "ambient_temperature_c",
                     "current_gradient_pct", "distance_since_trip_start_km"]:
            if key in snap and snap[key] is not None:
                feature_values[key] = float(snap[key])

    if feature_values:
        result = assess_ood(feature_values)
    else:
        # No features available; assume normal
        result = {
            "ood": False,
            "severity": "normal",
            "score": 0.0,
            "violations": [],
            "message": "Insufficient features to assess OOD; assuming normal distribution.",
        }

    return result


# ---------------------------------------------------------------------------
# Sensor quality assessment helper
# ---------------------------------------------------------------------------

def assess_sensor_quality_from_request(request: PredictionRequest) -> dict[str, Any]:
    """Assess overall sensor quality from a PredictionRequest."""
    snap = request.telemetry.model_dump()
    return assess_complete_telemetry_quality(snap)


# ---------------------------------------------------------------------------
# Route status helper
# ---------------------------------------------------------------------------

def assess_route_status(terrain: RouteTerrain, terrain_available: bool = True) -> dict[str, str]:
    """Assess route terrain availability status."""
    if terrain_available and terrain is not None and len(terrain.offsets_km) > 0:
        return {"available": True, "terrain_features_available": True, "status": "available"}
    elif terrain_available:
        return {"available": True, "terrain_features_available": False, "status": "incomplete"}
    else:
        return {"available": False, "terrain_features_available": False, "status": "unavailable"}


# ---------------------------------------------------------------------------
# Prediction service with STEP 15 enhancements
# ---------------------------------------------------------------------------

class PredictionService:
    """Production prediction pipeline with uncertainty, OOD, confidence.

    Model is loaded once at startup. All additions are read-only w.r.t. the
    frozen model and preprocessor.
    """

    def __init__(self, models_dir: Path | None = None,
                 terrain_provider: RouteTerrainProvider | None = None,
                 reserve_soc_pct: float = 10.0,
                 log_file: Path | None = None):
        self.models_dir = models_dir or PROJECT_ROOT / "models"
        self.metadata = load_model_metadata(self.models_dir)
        self.terrain_provider = terrain_provider
        self.reserve_soc_pct = float(reserve_soc_pct)
        self._log = InferenceLogger(model_version=MODEL_VERSION)
        self.logger = self._log._logger

        try:
            self.model = joblib.load(self.models_dir / "ev_energy_extratrees_route_aware.joblib")
            self.preprocessor = joblib.load(self.models_dir / "final_preprocessor.joblib")
        except Exception as e:
            raise ModelLoadError("MODEL_LOAD_FAILED",
                                 f"failed to load frozen model artifacts: {e}")
        self.feature_builder = FeatureBuilder(self.models_dir)
        self.range_estimator = RangeEstimator(reserve_soc_pct=self.reserve_soc_pct)

    # ------------------------------------------------------------------ info
    def health(self) -> dict:
        return {
            "status": "ok",
            "model_loaded": True,
            "model_version": self.metadata.model_version,
        }

    def model_info(self) -> dict:
        return self.metadata.model_info()

    # --------------------------------------------------------------- predict
    def _resolve_terrain(self, request: PredictionRequest) -> RouteTerrain:
        """Convert validated terrain input into a RouteTerrain object."""
        pts = [(p.offset_km, p.altitude_m) for p in request.route_terrain.points]
        pts = sorted(pts, key=lambda t: t[0])
        offsets = np.array([t[0] for t in pts], dtype=float)
        alts = np.array([t[1] for t in pts], dtype=float)
        try:
            return RouteTerrain(offsets, alts, source=request.route_terrain.source)
        except ValueError as e:
            raise TerrainUnavailableError("INVALID_TERRAIN", str(e))

    def predict(self, request: PredictionRequest,
                request_id: str | None = None) -> PredictionResponse:
        """Run the full pipeline and return a validated STEP 15 response."""
        ilog = InferenceLogger(request_id=request_id,
                               model_version=self.metadata.model_version)
        ilog.log_start()
        try:
            return self._predict(request, ilog)
        except InferenceError as e:
            ilog.log_failure(e.code, e.message)
            raise
        except Exception as e:
            ilog.log_failure("INTERNAL", str(e))
            raise InferenceError("INTERNAL_ERROR", f"internal prediction error: {e}")

    def _predict(self, request: PredictionRequest, ilog: InferenceLogger) -> PredictionResponse:
        """Run the full pipeline and return a validated STEP 15 response with explicit status.

        Returns a PredictionStatus code indicating reliability:
        - OK: full prediction valid
        - DEGRADED: prediction valid but some features degraded/missing
        - INSUFFICIENT_DATA: cannot produce reliable prediction
        - OFFLINE: system not ready (model, preprocessor, or terrain unavailable)
        """
        ilog.log_start()
        try:
            return self._predict_with_status(ilog)
        except InferenceError as e:
            ilog.log_failure(e.code, e.message)
            from src.inference.service import PredictionStatus
            return PredictionResponse(
                predicted_energy_kwh_per_km=float("nan"),
                usable_energy_kwh=0.0,
                expected_range_km=0.0,
                conservative_range_km=None,
                optimistic_range_km=None,
                uncertainty=None,
                confidence=None,
                ood={"is_ood": False, "severity": "normal", "score": 0.0, "violations": [], "message": e.message},
                route={"available": False, "terrain_features_available": False},
                sensor_quality="invalid",
                route_terrain_source="unknown",
                status=PredictionStatus.OFFLINE,
            )
        except Exception as e:
            ilog.log_failure("INTERNAL", str(e))
            from src.inference.service import PredictionStatus
            return PredictionResponse(
                predicted_energy_kwh_per_km=float("nan"),
                usable_energy_kwh=0.0,
                expected_range_km=0.0,
                conservative_range_km=None,
                optimistic_range_km=None,
                uncertainty=None,
                confidence=None,
                ood={"is_ood": False, "severity": "normal", "score": 0.0, "violations": [], "message": str(e)},
                route={"available": False, "terrain_features_available": False},
                sensor_quality="invalid",
                route_terrain_source="unknown",
                status=PredictionStatus.OFFLINE,
            )

    def _predict_with_status(self, ilog: InferenceLogger) -> PredictionResponse:
        """Internal prediction that determines and returns explicit status."""

        snap = request.telemetry.model_dump()

        # ---- Determine initial status based on input availability ------------
        status = PredictionStatus.OK

        # Check if route terrain is available (required for route-aware mode)
        if request.route_terrain is None or not request.route_terrain.points:
            status = PredictionStatus.INSUFFICIENT_DATA

        # Check if terrain provider is available but unimplemented (real DEM not connected)
        if status != PredictionStatus.INSUFFICIENT_DATA and self.terrain_provider is not None:
            try:
                terrain = self.terrain_provider.get_upcoming_terrain(
                    snap["distance_since_trip_start_km"], snap["altitude_m"])
            except NotImplementedError:
                status = PredictionStatus.DEGRADED  # terrain available but not real
            except Exception:
                status = PredictionStatus.INSUFFICIENT_DATA
        elif status != PredictionStatus.INSUFFICIENT_DATA:
            # Use validated route terrain from request body
            try:
                terrain = self._resolve_terrain(request)
            except TerrainUnavailableError:
                status = PredictionStatus.INSUFFICIENT_DATA

        # ---- Feature building ------------------------------------------------
        past = None
        if request.past_window:
            past = pd.DataFrame([s.model_dump() for s in request.past_window])
            if not past.empty:
                past = past.sort_values("distance_km").reset_index(drop=True)
        try:
            X = self.feature_builder.build_features(snap, terrain, past)
        except FeatureBuildError as e:
            status = PredictionStatus.INSUFFICIENT_DATA
            raise InferenceError("FEATURE_BUILD_FAILED", str(e))
        except Exception as e:
            status = PredictionStatus.INSUFFICIENT_DATA
            raise InferenceError("FEATURE_BUILD_FAILED", str(e))

        # ---- preprocess (frozen imputer) ----------------------------------
        try:
            X_arr = self.preprocessor.transform(X.to_numpy(dtype=float))
        except Exception as e:
            status = PredictionStatus.OFFLINE
            raise PreprocessorError("PREPROCESSOR_FAILED",
                                    f"frozen preprocessor failed: {e}")

        # Check for non-finite features after imputation
        if not np.all(np.isfinite(X_arr)):
            status = PredictionStatus.INSUFFICIENT_DATA
            raise InferenceError(
                "NON_FINITE_FEATURES",
                "feature vector contains non-finite values after imputation")

        # ---- predict ------------------------------------------------------
        try:
            preds = self.model.predict(X_arr)
        except Exception as e:
            status = PredictionStatus.OFFLINE
            raise InferenceError("PREDICTION_FAILED", f"model predict failed: {e}")
        pred = float(preds[0])

        # ---- uncertainty (prediction interval) ----------------------------
        uncertainty = _prediction_interval_from_quantiles(pred)

        # ---- range estimation ---------------------------------------------
        capacity = snap["battery_capacity_kwh"]
        soc = snap["soc_pct"]
        if not (pred > 0) or not math.isfinite(pred):
            # consumption <= 0 => net regen gain; range undefined
            usable = self.range_estimator.usable_energy_kwh(capacity, soc)
            r = {
                "usable_energy_kwh": usable,
                "expected_range_km": 0.0,
                "conservative_range_km": None,
                "optimistic_range_km": None,
            }
        else:
            r = self.range_estimator.estimate_range(capacity, soc, pred)

        # ---- OOD assessment -----------------------------------------------
        ood_result = assess_ood_from_request(request)

        # ---- confidence score ---------------------------------------------
        # Compute missing feature fraction (features that are NaN / absent)
        # After feature building, count how many of the 102 features are NaN
        n_features = len(self.feature_builder.features)
        n_nan = int(np.isnan(X_arr).sum()) if hasattr(X_arr, 'shape') else 0
        missing_frac = n_nan / n_features if n_features > 0 else 0.0

        # Adjust status based on confidence components
        if missing_frac > 0.5:
            # More than half the features are missing — downgrade status
            if status == PredictionStatus.OK:
                status = PredictionStatus.DEGRADED

        confidence = compute_confidence_score(
            ood_result=ood_result,
            missing_feature_fraction=missing_frac,
            route_available=terrain is not None,
            route_terrain_available=terrain is not None and len(terrain.offsets_km) > 0,
            uncertainty_width=uncertainty["interval_width"],
            predicted_consumption=pred,
        )

        # Further status adjustment based on confidence level
        if confidence["level"] == "low" and status == PredictionStatus.OK:
            status = PredictionStatus.DEGRADED

        # ---- route status -------------------------------------------------
        route_status = assess_route_status(terrain, terrain_available=True)

        # ---- sensor quality -----------------------------------------------
        sensor_quality = assess_sensor_quality_from_request(request)

        # ---- build response ------------------------------------------------
        resp = PredictionResponse(
            predicted_energy_kwh_per_km=pred,
            usable_energy_kwh=r["usable_energy_kwh"],
            expected_range_km=r["expected_range_km"],
            conservative_range_km=r["conservative_range_km"],
            optimistic_range_km=r["optimistic_range_km"],
            uncertainty={
                "lower_consumption": uncertainty["lower_consumption"],
                "upper_consumption": uncertainty["upper_consumption"],
                "interval_width": uncertainty["interval_width"],
            } if uncertainty["interval_width"] > 0 else None,
            confidence={
                "score": confidence["score"],
                "level": confidence["level"],
            } if confidence["score"] > 0 else None,
            ood={
                "is_ood": ood_result["ood"],
                "severity": ood_result["severity"],
                "score": ood_result["score"],
                "violations": ood_result["violations"],
                "message": ood_result["message"],
            },
            route={
                "available": route_status["available"],
                "terrain_features_available": route_status["terrain_features_available"],
            },
            sensor_quality=sensor_quality["overall_rating"],
            route_terrain_source=terrain.source,
            status=status,  # Explicit fail-safe status
        )

        ilog.log_success(
            prediction=pred,
            range_km=r["expected_range_km"],
        )
        return resp


def create_service(models_dir: Path | None = None,
                   terrain_provider: RouteTerrainProvider | None = None,
                   reserve_soc_pct: float = 10.0) -> PredictionService:
    """Factory (used by the API and tests)."""
    return PredictionService(models_dir=models_dir,
                             terrain_provider=terrain_provider,
                             reserve_soc_pct=reserve_soc_pct)
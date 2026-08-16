"""
STEP 11L - Inference service memory audit.

Measures peak RAM (resident set, via psutil) of the loaded inference
service including the frozen model and preprocessor. Target: < 500 MB.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.inference.service import PredictionService  # noqa: E402

OUT = ROOT / "reports" / "step11_memory_report.json"


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / (1024 * 1024)


def main() -> None:
    proc = psutil.Process()
    baseline = rss_mb()
    t0 = time.perf_counter()
    svc = PredictionService()
    load_s = time.perf_counter() - t0
    after_load = rss_mb()

    # force a prediction to capture any lazy allocations
    from src.inference.feature_builder import build_demo_snapshot
    from src.inference.schemas import PredictionRequest, RouteTerrainInput, TelemetrySnapshot, TerrainPoint
    snap = build_demo_snapshot()
    pts = [TerrainPoint(offset_km=i * 0.2,
                        altitude_m=150 + 25 * __import__("math").sin(i * 0.4))
           for i in range(26)]
    terrain = RouteTerrainInput(points=pts, source="DEM_STATIC")
    svc.predict(PredictionRequest(telemetry=TelemetrySnapshot(**snap),
                                  route_terrain=terrain))
    after_prediction = rss_mb()

    report = {
        "step": "11L",
        "python": sys.version.split()[0],
        "baseline_rss_mb": round(baseline, 2),
        "after_model_load_rss_mb": round(after_load, 2),
        "after_prediction_rss_mb": round(after_prediction, 2),
        "peak_rss_mb": round(max(baseline, after_load, after_prediction), 2),
        "load_seconds": round(load_s, 3),
        "target_mb": 500,
        "within_budget": max(baseline, after_load, after_prediction) < 500,
        "notes": "single model + preprocessor loaded once; ExtraTrees 300 trees "
                 "over 102 features; memory target < 500 MB",
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
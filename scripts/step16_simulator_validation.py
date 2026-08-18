"""
STEP 16 — 50-scenario validation through the real frozen model (/predict).

For each of 50 seeded physics scenarios, the simulator runs and consumption /
range are predicted at 6 evenly-spaced checkpoints through the REAL
PredictionService.predict (the exact path /predict uses). A subset is also
validated through the HTTP /predict endpoint.

Asserts (never modifies the model):
- No crashes; every prediction returns a structured response.
- predicted energy finite (may be <= 0: the training
  target is energy over the next 5 km and legitimately goes negative during
  regen-dominated segments; the pipeline maps those to range 0.0).
- expected range finite and >= 0 (== 0.0 exactly when predicted energy <= 0,
  with conservative/optimistic None per the pipeline contract).
- when expected range > 0: conservative <= expected <= optimistic.
- status in {OK, DEGRADED}.
- route terrain source is honestly labeled SIMULATOR_ROUTE.
- non-positive consumption (kwh <= 0, mapping to range 0.0) stays a small minority (< 20%).
- same-seed reruns are deterministic within 1e-9 (ULP-level tolerance:
  ExtraTrees n_jobs=-1 aggregates trees in parallel, causing ~1e-17 jitter).
- the frozen model artifact hash is unchanged.

Writes reports/step16_simulator_validation.json and .md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports"
MODEL_PATH = ROOT / "models" / "ev_energy_extratrees_route_aware.joblib"
EXPECTED_MODEL_SHA256 = (
    "27a0b7ab8a7fd5bc42ba2ac04d73be772880cdf2a64897108e343a57c6841319"
)

N_SCENARIOS = 50
CHECKPOINT_STEPS = [0, 600, 1200, 1800, 2400, 3000]  # 0..25 min @ 0.5 s/step
API_SUBSET = 10  # first N scenarios also validated through HTTP /predict


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_request(engine):
    from src.inference.schemas import (
        PastWindowSample, PredictionRequest, RouteTerrainInput, TelemetrySnapshot,
    )
    snap = engine.snapshot()
    terrain = engine.route_terrain_input()
    return (
        PredictionRequest(
            telemetry=TelemetrySnapshot(**snap),
            route_terrain=RouteTerrainInput(**terrain),
            past_window=[PastWindowSample(**s) for s in engine.past_window()],
        ),
        snap,
    )


def run_validation(service):
    """Run all 50 scenarios; return (rows, violations, status_counts)."""
    from src.simulator.scenario import random_scenario
    from src.simulator.simulator import SimulationEngine

    rows = []
    violations: list[str] = []
    status_counts = Counter()
    seen_scenario_ids: set[str] = set()
    nonpos = 0

    for seed in range(N_SCENARIOS):
        scenario = random_scenario(seed=seed)
        engine = SimulationEngine(scenario)
        prev = 0
        for cs in CHECKPOINT_STEPS:
            engine.step(cs - prev)
            prev = cs
            request, snap = build_request(engine)
            resp = service.predict(request)

            kwh = resp.predicted_energy_kwh_per_km
            exp = resp.expected_range_km
            cons = resp.conservative_range_km
            opt = resp.optimistic_range_km
            status = str(resp.status)

            row = {
                "seed": seed,
                "checkpoint_step": cs,
                "scenario_id": snap.get("scenario_id"),
                "soc_pct": round(float(snap["soc_pct"]), 2),
                "speed_kmh": round(float(snap["speed_kmh"]), 2),
                "altitude_m": round(float(snap["altitude_m"]), 1),
                "dist_km": round(float(snap["distance_since_trip_start_km"]), 3),
                "kwh_per_km": round(float(kwh), 6),
                "expected_range_km": round(float(exp), 2),
                "conservative_range_km": (round(float(cons), 2)
                                          if cons is not None else None),
                "optimistic_range_km": (round(float(opt), 2)
                                        if opt is not None else None),
                "status": status,
                "route_source": resp.route_terrain_source,
                "usable_energy_kwh": round(float(resp.usable_energy_kwh), 3),
            }
            rows.append(row)
            status_counts[status] += 1
            if snap.get("scenario_id"):
                seen_scenario_ids.add(snap["scenario_id"])

            # Invariant checks -------------------------------------------------
            # kWh/km finite (may be <= 0; the training
            # target supports negative values and the pipeline maps them to a
            # 0.0 range). NaN/non-finite is always a violation.
            if not (kwh == kwh and kwh != float("inf") and kwh != float("-inf")):
                violations.append(
                    f"seed {seed} cp {cs}: kwh_per_km not finite ({kwh!r})")
            if not (exp == exp and exp >= 0):
                violations.append(
                    f"seed {seed} cp {cs}: expected_range not >=0 ({exp!r})")
            if kwh <= 0:
                nonpos += 1
                # Pipeline contract for non-positive consumption: range 0.0 and the
                # band ends are None (range undefined, not infinite).
                if not (exp == 0.0 and cons is None and opt is None):
                    violations.append(
                        f"seed {seed} cp {cs}: non-positive consumption not mapped to "
                        f"range 0.0/None band (exp={exp!r} cons={cons!r} opt={opt!r})")
            elif cons is not None and opt is not None:
                if not (cons <= exp <= opt):
                    violations.append(
                        f"seed {seed} cp {cs}: ordering violated "
                        f"cons={cons} exp={exp} opt={opt}")
            if status not in ("OK", "DEGRADED"):
                violations.append(f"seed {seed} cp {cs}: unexpected status {status}")
            if resp.route_terrain_source != "SIMULATOR_ROUTE":
                violations.append(
                    f"seed {seed} cp {cs}: source {resp.route_terrain_source!r}")
            if not (resp.usable_energy_kwh > 0):
                violations.append(f"seed {seed} cp {cs}: usable energy not >0")

    return rows, violations, status_counts, seen_scenario_ids, nonpos


def determinism_check(service):
    """Same seed twice => identical prediction within ULP tolerance.

    ExtraTrees with n_jobs=-1 aggregates tree predictions in parallel, which
    can reorder floating-point additions by ~1e-17; the physics simulator
    itself is fully deterministic. We therefore require abs diff < 1e-9.
    """
    from src.simulator.scenario import random_scenario
    from src.simulator.simulator import SimulationEngine

    out = []
    for trial in range(2):
        engine = SimulationEngine(random_scenario(seed=0))
        engine.step(1500)
        request, _ = build_request(engine)
        out.append(float(service.predict(request).predicted_energy_kwh_per_km))
    return abs(out[0] - out[1]) < 1e-9, out


def api_http_check():
    """Validate a subset through the real HTTP /predict endpoint."""
    from fastapi.testclient import TestClient
    from api.main import app

    results = []
    with TestClient(app) as client:
        for seed in range(API_SUBSET):
            r = client.post("/simulator/reset", params={"seed": seed, "n_steps": 120})
            assert r.status_code == 200, r.text
            snap = r.json()
            p = client.post("/predict", json={
                "telemetry": snap["telemetry"],
                "route_terrain": snap["route_terrain"],
                "reserve_soc_pct": 10.0,
            })
            body = p.json()
            kwh = body["predicted_energy_kwh_per_km"]
            exp = body["expected_range_km"]
            # Non-positive consumption (kwh <= 0) legitimately maps to range 0.0.
            ok = (p.status_code == 200
                  and isinstance(kwh, float)
                  and exp >= 0
                  and body["status"] in ("OK", "DEGRADED")
                  and body["route_terrain_source"] == "SIMULATOR_ROUTE")
            if kwh <= 0:
                ok = ok and exp == 0.0
            results.append({"seed": seed, "http_status": p.status_code,
                            "ok": ok, "status": body.get("status"),
                            "kwh_per_km": body.get("predicted_energy_kwh_per_km")})
    return results


def main() -> int:
    from src.inference.service import PredictionService

    model_sha = sha256_file(MODEL_PATH)
    model_unchanged = model_sha == EXPECTED_MODEL_SHA256

    service = PredictionService()
    rows, violations, status_counts, scenario_ids, nonpos = run_validation(service)
    det_ok, det_vals = determinism_check(service)
    http = api_http_check()

    total = len(rows)
    nonpos_share = nonpos / total if total else 0.0
    if nonpos_share >= 0.20:
        violations.append(
            f"non-positive consumption instants too common: {nonpos}/{total} "
            f"({nonpos_share:.1%})")
    passed = total - len(violations)

    report = {
        "step": "16",
        "title": "STEP 16 - 50-scenario simulator validation via real /predict",
        "model_sha256": model_sha,
        "model_unchanged": model_unchanged,
        "expected_model_sha256": EXPECTED_MODEL_SHA256,
        "n_scenarios": N_SCENARIOS,
        "checkpoints_per_scenario": len(CHECKPOINT_STEPS),
        "total_predictions": total,
        "predictions_passed": passed,
        "predictions_failed": len(violations),
        "validation_status": "all_passed" if not violations and model_unchanged else "failed",
        "status_counts": dict(status_counts),
        "unique_scenario_ids": len(scenario_ids),
        "nonpos_instants_kwh_le_0": nonpos,
        "nonpos_share": round(nonpos_share, 6),
        "energy_kwh_per_km": {
            "min": round(min(r["kwh_per_km"] for r in rows), 6),
            "max": round(max(r["kwh_per_km"] for r in rows), 6),
            "mean": round(sum(r["kwh_per_km"] for r in rows) / total, 6),
        },
        "expected_range_km": {
            "min": round(min(r["expected_range_km"] for r in rows), 2),
            "max": round(max(r["expected_range_km"] for r in rows), 2),
            "mean": round(sum(r["expected_range_km"] for r in rows) / total, 2),
        },
        "determinism": {
            "same_seed_within_1e-9": det_ok,
            "seed_0_trials_kwh_per_km": det_vals,
        },
        "http_predict_subset": {
            "n_checked": len(http),
            "all_ok": all(r["ok"] for r in http),
            "results": http,
        },
        "violations": violations[:50],
        "n_violations_reported": len(violations),
    }

    REPORTS.mkdir(exist_ok=True)
    json_path = REPORTS / "step16_simulator_validation.json"
    json_path.write_text(json.dumps(report, indent=2, default=str),
                         encoding="utf-8")
    _write_markdown(report, rows)

    ok = (not violations) and model_unchanged and det_ok and all(r["ok"] for r in http)
    print(f"model_unchanged={model_unchanged} det={det_ok} "
          f"http_all_ok={all(r['ok'] for r in http)}")
    print(f"predictions: {passed}/{total} passed, status_counts={dict(status_counts)}")
    print(f"report -> {json_path}")
    return 0 if ok else 1


def _write_markdown(report: dict, rows: list[dict]) -> None:
    md = REPORTS / "step16_simulator_validation.md"
    lines = [
        f"# STEP 16 — 50-scenario simulator validation (real /predict)",
        "",
        f"- Date: {__import__('datetime').datetime.now().isoformat(timespec='seconds')}",
        f"- Scenarios: {report['n_scenarios']} seeds x {report['checkpoints_per_scenario']} checkpoints "
        f"= {report['total_predictions']} predictions",
        f"- Passed: {report['predictions_passed']} / {report['total_predictions']}",
        f"- Status counts: {report['status_counts']}",
        f"- Non-positive consumption (kWh/km <= 0, range 0.0): {report['nonpos_instants_kwh_le_0']} "
        f"({report['nonpos_share']:.1%} of predictions)",
        f"- Energy kWh/km: min={report['energy_kwh_per_km']['min']}, "
        f"max={report['energy_kwh_per_km']['max']}, "
        f"mean={report['energy_kwh_per_km']['mean']}",
        f"- Expected range km: min={report['expected_range_km']['min']}, "
        f"max={report['expected_range_km']['max']}, "
        f"mean={report['expected_range_km']['mean']}",
        f"- Deterministic rerun (seed 0): {report['determinism']}",
        f"- HTTP /predict subset: {report['http_predict_subset']['all_ok']} "
        f"({report['http_predict_subset']['n_checked']} checks)",
        f"- Model hash unchanged: {report['model_unchanged']}",
        "",
        "## Invariants validated",
        "",
        "- No crashes; every checkpoint produced a structured response.",
        "- predicted_energy_kwh_per_km finite (may be <= 0;",
        "  the training target is 5-km energy and legitimately goes negative during",
        "  regen-dominated segments, and the pipeline maps those to range 0.0).",
        "- expected_range_km finite and >= 0 (0.0 exactly when predicted energy <= 0,",
        "  with conservative/optimistic None per the pipeline contract).",
        "- conservative <= expected <= optimistic when range > 0.",
        "- status in {OK, DEGRADED}.",
        "- route_terrain_source == SIMULATOR_ROUTE (honest labeling).",
        "- usable_energy_kwh > 0.",
        "- non-positive-consumption instants are a small minority (< 20%).",
        "",
    ]
    if report["violations"]:
        lines += ["## Violations", ""]
        lines += [f"- {v}" for v in report["violations"]]
        lines += [""]
    lines += [
        "## Per-scenario summary",
        "",
        "| seed | checkpoints | min kWh/km | max kWh/km | statuses |",
        "|------|-------------|------------|------------|----------|",
    ]
    by_seed = {}
    for r in rows:
        by_seed.setdefault(r["seed"], []).append(r)
    for seed in sorted(by_seed):
        rs = by_seed[seed]
        ks = [r["kwh_per_km"] for r in rs]
        st = Counter(r["status"] for r in rs)
        lines.append(
            f"| {seed} | {len(rs)} | {min(ks):.4f} | {max(ks):.4f} | {dict(st)} |")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

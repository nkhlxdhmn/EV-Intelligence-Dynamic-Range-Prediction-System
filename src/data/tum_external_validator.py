"""
TUM EV UDS External Validator.

Evaluates whether the frozen DEVRT route-aware energy model
(ExtraTrees, 102 features) can be applied to the TUM EV UDS dataset
(VW ID.3, CUPRA Born) for external validation.

IMPORTANT RULES (from STEP 10):
- The frozen model is NEVER retrained, tuned, or modified.
- The DEVRT hold-out test set is NEVER re-evaluated.
- Missing TUM signals are NEVER fabricated:
    - No GPS/altitude -> route-terrain features are UNAVAILABLE_EXTERNAL.
    - value_id 1205 ptc1_current is heater current, NOT traction current.
    - value_id 56 hv_aux_power is auxiliary power, NOT total traction power.
- If the full 102-feature vector cannot be reproduced from TUM signals,
  external validation is reported as BLOCKED (scientifically valid outcome).
- Memory safety: row-group streaming only, one vehicle file at a time,
  gc.collect() after each row group, never load a full raw file into pandas.

Signal inventory (verified from dataset/electric-vehicle-uds-dataset-main/data/uds_data/):
  AVAILABLE per-timestamp in raw parquet:
    4    vehicle_speed        km/h   200 ms
    15   ambient_air_temp     degC   10000 ms
    56   hv_aux_power         W      1000 ms
    900  hv_soc               %      5000 ms
    1200 hv_battery_voltage   V      200 ms
    1205 ptc1_current         A      1000 ms (ID1 only)
    1208/1209 hv_temp_min/max degC
    961/1265 motor temps, 1269 coolant, 1272/1273 battery temps, 43 interior (ID1)
  NOT PRESENT (verified zero rows across all 7 raw files):
    1288 cell_c_rate, 1290 hv_dod, 1291 track_duration,
    1292 idle_period_duration, 1299 traveled_distance
  traveled_distance (1299) exists ONLY as aggregated histograms in data/json/
  (track_*.json), NOT as a per-timestamp time series. Without a per-timestamp
  distance signal the +5 km future energy target cannot be constructed.

Fleet battery capacity (dataset README.MD fleet specifications table):
  ID.3 Pro Performance 2020: 108s2p (216 cells), 58 kWh net
  CUPRA Born 2022:           108s2p (216 cells), 58 kWh net
  -> Status DERIVED (documented fleet specification, not per-vehicle verified).

Timestamp handling:
  Raw time is timestamp[ns]. One anomalous 812-row block in CUP1 row-group 0
  carries year-2087 timestamps (~55 s of data); the remaining time range is
  normal (2022-11 .. 2023). Garbage blocks are dropped. Time is treated as UTC
  (dataset provides naive UTC timestamps).
"""

import gc
import json
import os
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


TUM_RAW_DIR = Path("dataset/electric-vehicle-uds-dataset-main/data/uds_data")
TUM_VALUE_OVERVIEW = Path("dataset/electric-vehicle-uds-dataset-main/data/value_overview.csv")
TUM_JSON_DIR = Path("dataset/electric-vehicle-uds-dataset-main/data/json")
DEVRT_FEATURES = Path("data/processed/devrt_ml_features_v3_route_aware.parquet")
MODEL_PATH = Path("models/ev_energy_extratrees_route_aware.joblib")
PREPROCESSOR_PATH = Path("models/final_preprocessor.joblib")
FEATURE_LIST_PATH = Path("models/final_feature_list.json")
REPORT_DIR = Path("reports")
INTERIM_DIR = Path("data/interim/tum")

VEHICLES = ["CUP1", "CUP2", "CUP3", "CUP4", "CUP5", "ID1", "ID2"]

# value_id -> (signal_name, unit, native sampling ms)
TUM_SIGNALS = {
    4: ("vehicle_speed", "km/h", 200),
    15: ("ambient_air_temp", "degC", 10000),
    56: ("hv_aux_power", "W", 1000),
    900: ("hv_soc", "%", 5000),
    1200: ("hv_battery_voltage", "V", 200),
    1205: ("ptc1_current", "A", 1000),
    1208: ("hv_temp_min", "degC", 10000),
    1209: ("hv_temp_max", "degC", 10000),
    43: ("interior_temp", "degC", 10000),
    961: ("motor_stator_temp", "degC", 5000),
    1265: ("motor_rotor_temp", "degC", 5000),
    1269: ("coolant_inverter_temp", "degC", 5000),
    1272: ("battery_pack_inlet_temp", "degC", 5000),
    1273: ("battery_pack_outlet_temp", "degC", 5000),
}

# Signals declared in value_overview but verified ABSENT as per-timestamp series.
ABSENT_SIGNALS = {
    1288: "cell_c_rate",
    1290: "hv_dod",
    1291: "track_duration",
    1292: "idle_period_duration",
    1299: "traveled_distance",
}


def _now() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def scan_value_id_presence(vehicles=None, max_row_groups=None):
    """
    Stream row groups of each raw TUM file and count per value_id.

    Memory-safe: only the value_id column is read per row group; the full
    table is never materialized and pandas DataFrames are discarded.

    Returns:
        dict: {vehicle: {value_id(str): count}}
    """
    vehicles = vehicles or VEHICLES
    result = {}
    for v in vehicles:
        path = TUM_RAW_DIR / f"{v}.parquet"
        if not path.exists():
            result[v] = {}
            continue
        pf = pq.ParquetFile(path)
        counts = {}
        n_groups = pf.num_row_groups if max_row_groups is None else min(
            max_row_groups, pf.num_row_groups)
        for rg in range(n_groups):
            t = pf.read_row_group(rg, columns=["value_id"])
            vc = t["value_id"].value_counts().to_pylist()
            for row in vc:
                key = str(row["values"])
                counts[key] = counts.get(key, 0) + row["counts"]
            del t
            gc.collect()
        result[v] = counts
    return result


def stream_signal_series(vehicle, value_id, columns=("vehicle_id", "time", "value_id", "value"),
                         time_bounds=(pd.Timestamp("2020-01-01"), pd.Timestamp("2026-12-31"))):
    """
    Yield pandas DataFrames (one per row group) for a single signal.

    Filters to the requested value_id and drops out-of-bounds timestamps
    (removes the anomalous year-2087 block in CUP1 RG0).

    This generator is the memory-safe building block: consumers must keep only
    one small frame alive at a time.
    """
    path = TUM_RAW_DIR / f"{vehicle}.parquet"
    pf = pq.ParquetFile(path)
    lo, hi = time_bounds
    for rg in range(pf.num_row_groups):
        t = pf.read_row_group(rg, columns=list(columns))
        df = t.to_pandas()
        df = df[df["value_id"] == value_id]
        if len(df) > 0 and "time" in df.columns:
            df = df[(df["time"] >= lo) & (df["time"] <= hi)]
        if len(df) > 0:
            yield df[list(columns)]
        del df, t
        gc.collect()


def compute_signal_stats(vehicle, value_id, time_bounds=None, max_row_groups=None):
    """
    Compute robust per-signal statistics for one vehicle without loading the
    full file. Uses streaming accumulation of count/sum/sumsq + percentiles
    sampled at a fixed stride to bound memory.
    """
    path = TUM_RAW_DIR / f"{vehicle}.parquet"
    pf = pq.ParquetFile(path)
    n_groups = pf.num_row_groups if max_row_groups is None else min(
        max_row_groups, pf.num_row_groups)
    lo, hi = time_bounds or (pd.Timestamp("2020-01-01"), pd.Timestamp("2026-12-31"))

    n = 0
    s = 0.0
    sq = 0.0
    vmin = np.inf
    vmax = -np.inf
    sample = []

    for rg in range(n_groups):
        t = pf.read_row_group(rg, columns=["time", "value_id", "value"])
        df = t.to_pandas()
        df = df[df["value_id"] == value_id]
        if len(df) == 0:
            del df, t
            gc.collect()
            continue
        df = df[(df["time"] >= lo) & (df["time"] <= hi)]
        if len(df) == 0:
            del df, t
            gc.collect()
            continue
        vals = df["value"].to_numpy(dtype="float64")
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            del df, t, vals
            gc.collect()
            continue
        n += len(vals)
        s += float(vals.sum())
        sq += float((vals ** 2).sum())
        vmin = min(vmin, float(vals.min()))
        vmax = max(vmax, float(vals.max()))
        # bounded reservoir sample for percentiles
        k = max(1, len(vals) // 2000)
        sample.extend(vals[::k])
        if len(sample) > 500_000:
            sample = sample[::2]
        del df, t, vals
        gc.collect()

    if n == 0:
        return {"vehicle": vehicle, "value_id": value_id, "n": 0}

    arr = np.asarray(sample, dtype="float64")
    mean = s / n
    var = max(0.0, sq / n - mean * mean)
    pcts = np.percentile(arr, [1, 5, 10, 25, 50, 75, 90, 95, 99]) if len(arr) else [np.nan] * 9
    return {
        "vehicle": vehicle,
        "value_id": value_id,
        "signal_name": TUM_SIGNALS.get(value_id, ("unknown", "", 0))[0],
        "unit": TUM_SIGNALS.get(value_id, ("unknown", "", 0))[1],
        "n": n,
        "count": n,
        "mean": round(mean, 6),
        "std": round(float(np.sqrt(var)), 6),
        "min": round(vmin, 6),
        "max": round(vmax, 6),
        "p1": round(float(pcts[0]), 6),
        "p5": round(float(pcts[1]), 6),
        "p10": round(float(pcts[2]), 6),
        "p25": round(float(pcts[3]), 6),
        "p50": round(float(pcts[4]), 6),
        "p75": round(float(pcts[5]), 6),
        "p90": round(float(pcts[6]), 6),
        "p95": round(float(pcts[7]), 6),
        "p99": round(float(pcts[8]), 6),
    }


def _check_garbage_block(vehicle):
    """Detect the anomalous year-2087 timestamp block(s) in a raw file."""
    path = TUM_RAW_DIR / f"{vehicle}.parquet"
    pf = pq.ParquetFile(path)
    t = pf.read_row_group(0, columns=["time"])
    df = t.to_pandas()
    n_total = len(df)
    bad = (df["time"] >= pd.Timestamp("2026-01-01")).sum()
    res = {
        "vehicle": vehicle,
        "row_group_0_rows": int(n_total),
        "anomalous_rows_year_2087": int(bad),
        "has_anomalous_block": bool(bad > 0),
        "rg0_time_min": str(df["time"].min()),
        "rg0_time_max": str(df["time"].max()),
    }
    del df, t
    gc.collect()
    return res


def classify_feature_compatibility(feature_list):
    """
    Classify each feature of the frozen model as computable from TUM signals.

    Categories:
      AVAILABLE               -> computable from TUM per-timestamp signals
      UNAVAILABLE_NEEDS_GPS   -> requires GPS/altitude/route terrain (absent)
      UNAVAILABLE_NEEDS_MOTOR -> requires traction motor power/regen (absent)
      UNAVAILABLE_NEEDS_DISTANCE_TRIP -> requires per-timestamp distance or
                                         trip boundaries (traveled_distance absent)
      UNAVAILABLE_OTHER       -> other missing source signal

    Returns:
        list of dicts with feature, category, source, reason.
    """
    # TUM signals available as per-timestamp series.
    has = {name for name, *_ in TUM_SIGNALS.values()}

    # Features computable from speed/temp/aux/soc/voltage + timestamps only.
    speed_based = {
        "current_speed_kmh", "acceleration_mps2", "mean_acceleration",
        "std_acceleration", "max_acceleration", "min_acceleration",
        "mean_pos_accel", "mean_neg_accel", "speed_change_recent",
        "speed_iqr", "speed_p10", "speed_p50", "speed_p90", "speed_squared",
        "max_speed_recent", "min_speed_recent", "high_speed_fraction",
        "stopped_fraction", "stop_count_recent", "hour_of_day", "day_of_week",
        "hour_sin", "hour_cos",
    }
    temp_based = {"current_temperature_c", "temperature_recent_mean",
                  "temperature_bucket", "speed_x_temperature"}
    soc_based = {"current_soc_pct"}
    aux_based = {"aux_power_kw", "aux_power_variability"}

    # Route terrain / altitude family (requires GPS + DEM elevation).
    gps_terms = ["altitude", "gradient", "elevation", "terrain", "uphill",
                 "downhill", "flat_fraction", "hillyness", "net_elev",
                 "hilly"]

    # Traction motor / regen family.
    motor_terms = ["motor_power", "torque", "motor_rpm", "regen",
                   "power_variability", "positive_motor_power"]

    # Distance / trip-boundary family.
    dist_terms = ["distance_since_trip_start", "trip_distance_so_far",
                  "trip_elapsed_time", "time_since_trip_start",
                  "_1km", "_500m", "regen_events_per_km"]

    rows = []
    for feat in feature_list:
        # direct source availability
        if feat in speed_based:
            cat, src, reason = "AVAILABLE", "vehicle_speed", "speed + timestamp signals present"
        elif feat in temp_based:
            cat, src, reason = "AVAILABLE", "ambient_air_temp", "temperature signal present"
        elif feat in soc_based:
            cat, src, reason = "AVAILABLE", "hv_soc", "SOC signal present"
        elif feat in aux_based:
            cat, src, reason = "AVAILABLE", "hv_aux_power", "aux power signal present"
        elif any(t in feat for t in gps_terms) or feat.startswith("next_"):
            cat = "UNAVAILABLE_NEEDS_GPS"
            src = "GPS_ALTITUDE"
            reason = "requires GPS/altitude/DEM route terrain, not present in TUM"
        elif any(t in feat for t in motor_terms):
            cat = "UNAVAILABLE_NEEDS_MOTOR"
            src = "TRACTION_MOTOR"
            reason = "requires traction motor power/torque/rpm or regen power, not present (ptc1_current is heater, hv_aux_power is aux)"
        elif any(t in feat for t in dist_terms):
            cat = "UNAVAILABLE_NEEDS_DISTANCE_TRIP"
            src = "DISTANCE_TRIP"
            reason = "requires per-timestamp traveled_distance (1299) or trip boundaries, absent in raw TUM"
        else:
            cat = "UNAVAILABLE_OTHER"
            src = "UNKNOWN"
            reason = "no TUM source signal maps to this feature"
        rows.append({
            "feature": feat,
            "status": cat,
            "source_signal": src,
            "reason": reason,
        })
    return rows


def run_freeze_verification():
    """10A: verify the frozen model artifacts are unmodified and loadable."""
    m = None
    p = None
    feats = []
    ok = False
    errors = []
    try:
        import joblib
        m = joblib.load(MODEL_PATH)
        p = joblib.load(PREPROCESSOR_PATH)
        feats = json.load(open(FEATURE_LIST_PATH))
    except Exception as e:  # pragma: no cover
        errors.append(str(e))

    params = {}
    n_features = None
    if m is not None:
        params = m.get_params()
        n_features = getattr(m, "n_features_in_", None)

    # expected frozen configuration
    expected = {
        "type": "ExtraTreesRegressor",
        "n_estimators": 300,
        "max_depth": 10,
        "min_samples_leaf": 3,
        "random_state": 42,
    }
    param_checks = {k: params.get(k) for k in ["n_estimators", "max_depth",
                                               "min_samples_leaf", "random_state"]}
    param_match = (
        m is not None
        and param_checks["n_estimators"] == expected["n_estimators"]
        and param_checks["max_depth"] == expected["max_depth"]
        and param_checks["min_samples_leaf"] == expected["min_samples_leaf"]
        and param_checks["random_state"] == expected["random_state"]
    )
    if n_features is not None and n_features != 102:
        errors.append(f"n_features_in_={n_features}, expected 102")
    if len(feats) != 102:
        errors.append(f"feature list length={len(feats)}, expected 102")
    if "trip_phase" in feats:
        errors.append("trip_phase present in frozen feature list (should be excluded)")
    preproc_ok = p is not None and type(p).__name__ == "SimpleImputer"
    ok = (param_match and preproc_ok and not errors and n_features == 102
          and len(feats) == 102)

    return {
        "generated_at": _now(),
        "model_path": str(MODEL_PATH),
        "preprocessor_path": str(PREPROCESSOR_PATH),
        "feature_list_path": str(FEATURE_LIST_PATH),
        "model_type": type(m).__name__ if m is not None else None,
        "n_features_in_": n_features,
        "feature_count": len(feats),
        "preprocessor_type": type(p).__name__ if p is not None else None,
        "params": {k: params.get(k) for k in ["n_estimators", "max_depth",
                                              "min_samples_leaf", "random_state"]},
        "param_match_expected": param_match,
        "trip_phase_excluded": "trip_phase" not in feats,
        "errors": errors,
        "freeze_verified": bool(ok),
    }


def run_battery_capacity_analysis():
    """
    10F: determine battery capacity status from dataset documentation.

    The dataset README.MD fleet-specifications table documents 58 kWh net for
    both the ID.3 Pro Performance (2020) and CUPRA Born (2022). This is a fleet
    specification, not a per-vehicle verified figure -> status DERIVED.
    """
    readme = Path("dataset/electric-vehicle-uds-dataset-main/README.MD")
    docs = []
    if readme.exists():
        txt = readme.read_text(encoding="utf-8", errors="ignore")
        if "58 kWh" in txt and "108s2p" in txt:
            docs.append("README.MD fleet specifications table: 58 kWh net, 108s2p (216 cells), both models")
    else:
        docs.append("README.MD not found")
    # Note: value_overview has no capacity column; no per-vehicle BMS capacity
    # field is exposed in the raw parquet (no value_id maps to capacity).
    return {
        "generated_at": _now(),
        "capacity_kwh_nominal": 58,
        "source": "dataset README.MD fleet specifications table",
        "per_vehicle_verified": False,
        "status": "DERIVED",
        "notes": [
            "Capacity is a documented fleet specification, not a per-vehicle BMS readout.",
            "No value_id in raw UDS maps to battery capacity.",
            "Used only to interpret SOC deltas; NOT used to fabricate features.",
        ],
        "documentation": docs,
    }


def run_signal_inventory(max_row_groups=None):
    """Build the signal presence inventory + per-signal stats + garbage-block report."""
    presence = scan_value_id_presence(max_row_groups=max_row_groups)
    present = {v: {k for k, c in d.items() if c > 0} for v, d in presence.items()}
    absent_per_vehicle = {
        v: sorted({vid for vid in ABSENT_SIGNALS if vid not in present.get(v, set())})
        for v in presence
    }
    garbage = [_check_garbage_block(v) for v in presence]
    return {
        "presence": presence,
        "absent_signal_value_ids": absent_per_vehicle,
        "garbage_blocks": garbage,
        "generated_at": _now(),
    }


def compute_domain_shift(devrt_path=DEVRT_FEATURES):
    """
    Compute DEVRT(train+val) vs TUM distributions for the handful of signals
    that ARE available in both worlds (speed, temperature, aux power, SOC).

    DEVRT stats come from the full 10,635-row feature parquet (train+val+test
    combined for distribution comparison only; no model fitting). TUM stats are
    computed by streaming each raw vehicle file.

    Returns:
        dict with per-signal comparative table rows.
    """
    devrt = pd.read_parquet(devrt_path, columns=[
        "current_speed_kmh", "current_temperature_c", "aux_power_kw",
        "current_soc_pct",
    ])
    dev_stats = {}
    for col in ["current_speed_kmh", "current_temperature_c", "aux_power_kw",
                "current_soc_pct"]:
        s = devrt[col].dropna()
        dev_stats[col] = {
            "n": int(len(s)),
            "mean": round(float(s.mean()), 6),
            "std": round(float(s.std(ddof=0)), 6),
            "min": round(float(s.min()), 6),
            "max": round(float(s.max()), 6),
            "p10": round(float(s.quantile(0.10)), 6),
            "p50": round(float(s.quantile(0.50)), 6),
            "p90": round(float(s.quantile(0.90)), 6),
        }
    del devrt
    gc.collect()

    # TUM side: vehicle_speed (km/h), ambient_air_temp, aux power (W->kW),
    # hv_soc.
    tum = {}
    for vid, col, scale in [(4, "current_speed_kmh", 1.0),
                            (15, "current_temperature_c", 1.0),
                            (56, "aux_power_kw", 1.0 / 1000.0),
                            (900, "current_soc_pct", 1.0)]:
        pooled = []
        for v in VEHICLES:
            st = compute_signal_stats(v, vid)
            if st.get("n", 0) > 0:
                st["mean_scaled"] = st["mean"] * scale
                st["n"] = st["n"]
                pooled.append(st)
        if pooled:
            n = sum(p["n"] for p in pooled)
            wmean = sum(p["mean_scaled"] * p["n"] for p in pooled) / n

            def wq(field):
                arr = sorted((p[field], p["n"]) for p in pooled if p.get(field) is not None)
                total = sum(nn for _, nn in arr)
                acc = 0.0
                for val, nn in arr:
                    acc += nn
                    if acc >= total / 2:
                        return val
                return None

            median_val = wq("p50")
            if median_val is not None:
                median_val = median_val * scale
            tum[col] = {
                "n": int(n),
                "mean": round(wmean, 6),
                "median_of_medians": round(median_val, 6) if median_val is not None else None,
            }

    rows = []
    for col in ["current_speed_kmh", "current_temperature_c", "aux_power_kw",
                "current_soc_pct"]:
        d = dev_stats.get(col, {})
        t = tum.get(col, {})
        ratio = None
        if d.get("mean") and t.get("mean"):
            ratio = round(t["mean"] / d["mean"], 4)
        rows.append({
            "signal": col,
            "devrt_n": d.get("n"),
            "devrt_mean": d.get("mean"),
            "devrt_std": d.get("std"),
            "devrt_p10": d.get("p10"),
            "devrt_p50": d.get("p50"),
            "devrt_p90": d.get("p90"),
            "tum_n": t.get("n"),
            "tum_mean": t.get("mean"),
            "tum_median_of_medians": t.get("median_of_medians"),
            "tum_devrt_mean_ratio": ratio,
        })
    return rows


def run_full_pipeline(write_reports=True):
    """Run the complete Step 10 external validation pipeline (memory tracked)."""
    REPORT_DIR.mkdir(exist_ok=True)
    tracemalloc.start()
    peak = 0.0
    t0 = time.time()

    print("[STEP 10] Freeze verification (10A)...")
    freeze = run_freeze_verification()
    peak = max(peak, tracemalloc.get_traced_memory()[1] / (1024 ** 2))

    print("[STEP 10] Signal inventory + garbage-block scan (10B/10C)...")
    inventory = run_signal_inventory()
    peak = max(peak, tracemalloc.get_traced_memory()[1] / (1024 ** 2))

    print("[STEP 10] Battery capacity analysis (10F)...")
    capacity = run_battery_capacity_analysis()
    peak = max(peak, tracemalloc.get_traced_memory()[1] / (1024 ** 2))

    print("[STEP 10] Feature compatibility classification (10G/10H)...")
    feats = json.load(open(FEATURE_LIST_PATH))
    compat = classify_feature_compatibility(feats)
    compat_summary = pd.DataFrame(compat)["status"].value_counts().to_dict()
    peak = max(peak, tracemalloc.get_traced_memory()[1] / (1024 ** 2))

    print("[STEP 10] Domain shift analysis (10L/10M)...")
    domain = compute_domain_shift()
    peak = max(peak, tracemalloc.get_traced_memory()[1] / (1024 ** 2))

    # Decision (10I/K): external validation of the frozen 102-feature model.
    n_avail = compat_summary.get("AVAILABLE", 0)
    blocked_reasons = []
    if n_avail < 102:
        blocked_reasons.append(
            f"only {n_avail}/102 frozen-model features are reproducible from TUM signals; "
            "missing features are GPS/altitude terrain (route-aware) and traction-motor "
            "features that cannot be fabricated.")
    if "traveled_distance" not in {c for c in ("traveled_distance",)} and True:
        blocked_reasons.append(
            "per-timestamp traveled_distance (1299) is absent; the +5 km future-energy "
            "target cannot be constructed.")
    blocked_reasons = list(dict.fromkeys(blocked_reasons))
    validation_status = "BLOCKED" if blocked_reasons else "COMPLETED"
    peak_mb = round(peak, 2)

    if write_reports:
        json.dump(freeze, open(REPORT_DIR / "step10_model_freeze_verification.json", "w"), indent=2)
        json.dump(inventory, open(REPORT_DIR / "step10_signal_inventory.json", "w"), indent=2)
        json.dump(capacity, open(REPORT_DIR / "step10_battery_capacity.json", "w"), indent=2)
        pd.DataFrame(compat).to_csv(REPORT_DIR / "step10_feature_compatibility.csv", index=False)
        pd.DataFrame(domain).to_csv(REPORT_DIR / "step10_domain_shift.csv", index=False)

    elapsed = time.time() - t0
    tracemalloc.stop()
    summary = {
        "generated_at": _now(),
        "elapsed_seconds": round(elapsed, 1),
        "peak_ram_mb": peak_mb,
        "freeze_verified": freeze["freeze_verified"],
        "validation_status": validation_status,
        "blocked_reasons": blocked_reasons,
        "features_total": len(feats),
        "features_available": n_avail,
        "feature_status_counts": compat_summary,
    }
    if write_reports:
        json.dump(summary, open(REPORT_DIR / "step10_validation_summary.json", "w"), indent=2)
        json.dump({
            "generated_at": _now(),
            "peak_ram_mb": peak_mb,
            "notes": "tracemalloc peak; row-group streaming used throughout",
        }, open(REPORT_DIR / "step10_memory_report.json", "w"), indent=2)
    return summary


if __name__ == "__main__":
    s = run_full_pipeline()
    print("\n=== STEP 10 SUMMARY ===")
    print(json.dumps(s, indent=2))
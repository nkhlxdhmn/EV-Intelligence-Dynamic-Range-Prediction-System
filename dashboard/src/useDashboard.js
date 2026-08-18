import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHealth, fetchModelInfo, postPrediction } from "./api";

// ---------------------------------------------------------------------------
// Live telemetry configuration
// ---------------------------------------------------------------------------

const LIVE_QUERY = (() => {
  const params = new URLSearchParams(window.location.search);
  return params.get("telemetry") === "1";
})();

const TELEMETRY_POLL_INTERVAL = 3000; // 3 seconds
const STALE_THRESHOLD_MS = 5000; // 5 seconds

// Quality state enum for UI display
const QualityState = {
  VALID: "VALID",
  MISSING: "MISSING",
  STALE: "STALE",
  INVALID: "INVALID",
  OUT_OF_RANGE: "OUT_OF_RANGE",
  UNAVAILABLE: "UNAVAILABLE",
};

// Telemetry status for the dashboard
const TelemetryStatus = {
  OK: "ok",
  DEGRADED: "degraded",
  OFFLINE: "offline",
};

// ---------------------------------------------------------------------------
// useDashboard hook
// ---------------------------------------------------------------------------

export function useDashboard() {
  // Determine initial mode: live (if ?telemetry=1 URL param), otherwise demo
  const [mode, setMode] = useState(() => LIVE_QUERY ? "live" : "demo");
  const [running, setRunning] = useState(false);
  const [pollMs, setPollMs] = useState(LIVE_QUERY ? 3000 : 1500);
  const [apiConnected, setApiConnected] = useState(false);
  const [predictionReady, setPredictionReady] = useState(false);
  const [modelInfo, setModelInfo] = useState(null);
  const [lastPred, setLastPred] = useState(null);
  const [lastError, setLastError] = useState(null);
  const [history, setHistory] = useState([]);
  const [, setTick] = useState(0);

  const timerRef = useRef(null);

  // Live telemetry state
  const [telemetry, setTelemetry] = useState({
    signals: [],
    status: TelemetryStatus.OFFLINE,
    quality: QualityState.UNAVAILABLE,
    age_ms: 0,
    source: "none",
  });
  const [routeStatus, setRouteStatus] = useState({
    available: false,
    terrain_features_available: false,
    status: "unavailable",
  });
  const [confidence, setConfidence] = useState({
    score: 0,
    level: "high",
    components: {
      ood_contribution: 0,
      missing_contribution: 0,
      route_contribution: 0,
      width_contribution: 0,
    },
  });
  const [sensorQuality, setSensorQuality] = useState({
    overall_rating: "unknown",
    details: {},
  });

  const timerRefQuality = useRef(null);

  const render = useCallback(() => setTick((t) => t + 1), []);

  // -------------------------------------------------------------------------
  // Payload builder: supports both demo (simulator) and live modes
  // -------------------------------------------------------------------------

  const buildPayload = useCallback(() => {
    if (mode === "demo") {
      // Demo mode: use simulator
      const sim = window.dashboardSimulator;
      if (!sim) {
        return null;
      }
      return {
        telemetry: {
          vehicle_id: "DEMO-VEHICLE",
          timestamp: new Date().toISOString(),
          soc_pct: +sim.soc.toFixed(2),
          battery_capacity_kwh: 58.0,
          speed_kmh: +sim.speed.toFixed(1),
          altitude_m: +sim.altitude.toFixed(1),
          ambient_temperature_c: +sim.temp.toFixed(1),
          distance_since_trip_start_km: +sim.distance.toFixed(2),
          time_since_trip_start_min: +sim.timeMin.toFixed(1),
          motor_power_kw: +sim.motorPower.toFixed(2),
          motor_rpm: 4200,
          motor_torque_nm: 60,
          aux_power_kw: +sim.auxPower.toFixed(2),
          regen_power_kw: sim.regen <= 0 ? +sim.regen.toFixed(2) : null,
          battery_voltage_v: +sim.battVolt.toFixed(1),
          battery_temperature_c: +sim.battTemp.toFixed(1),
          battery_current_a:
            +((sim.motorPower * 1000) / sim.battVolt).toFixed(1),
        },
        route_terrain: {
          points: sim.route,
          source: "DEM_STATIC",
        },
        reserve_soc_pct: 10.0,
      };
    } else {
      // Live mode: fetch from API telemetry endpoint
      // In prototype, we use the buffered telemetry state
      // In production, this would be from the connected adapter
      return {
        telemetry: {
          vehicle_id: "LIVE-VEHICLE",
          timestamp: new Date().toISOString(),
          // These will be filled from the live telemetry buffer
          soc_pct: null,  // placeholder
          battery_capacity_kwh: 58.0,
          speed_kmh: null,
          altitude_m: null,
          ambient_temperature_c: null,
          distance_since_trip_start_km: null,
          time_since_trip_start_min: null,
          motor_power_kw: null,
          motor_rpm: null,
          motor_torque_nm: null,
          aux_power_kw: null,
          regen_power_kw: null,
          battery_voltage_v: null,
          battery_temperature_c: null,
          battery_current_a: null,
        },
        route_terrain: {
          points: [],
          source: "ROUTE_API",
        },
        reserve_soc_pct: 10.0,
      };
    }
  }, [mode]);

  // -------------------------------------------------------------------------
  // Live telemetry polling
  // -------------------------------------------------------------------------

  const startLiveTelemetryPolling = useCallback(() => {
    // Poll the /live/telemetry endpoint at regular intervals
    const pollLiveTelemetry = async () => {
      try {
        const response = await fetch("/live/telemetry");
        if (!response.ok) {
          // Server might not have live telemetry connected;
          // don't treat as error, just show offline
          setTelemetry(prev => ({
            ...prev,
            status: TelemetryStatus.OFFLINE,
            quality: QualityState.UNAVAILABLE,
          }));
          return;
        }
        const data = await response.json();

        if (data.signals && data.signals.length > 0) {
          // Update telemetry state with latest signals
          // Determine overall quality based on signal availability
          let quality = QualityState.UNAVAILABLE;
          let status = TelemetryStatus.OFFLINE;

          // Simple quality assessment: check if we have valid signals
          const hasValidSignals = data.signals.some(
            s => s.has_value !== false && s.quality !== "MISSING" && s.quality !== "STALE"
          );

          const hasAnySignals = data.signals.length > 0;

          if (hasValidSignals && hasAnySignals) {
            quality = QualityState.VALID;
            status = TelemetryStatus.OK;
          } else if (hasAnySignals) {
            // Some signals but many missing/stale
            quality = QualityState.MISSING;
            status = TelemetryStatus.DEGRADED;
          } else {
            // No signals at all
            quality = QualityState.UNAVAILABLE;
            status = TelemetryStatus.OFFLINE;
          }

          setTelemetry({
            signals: data.signals,
            status: status,
            quality: quality,
            age_ms: data.age_ms !== undefined ? data.age_ms : 0,
            source: data.source || "none",
          });
        } else {
          // No signals returned
          setTelemetry(prev => ({
            ...prev,
            status: TelemetryStatus.OFFLINE,
            quality: QualityState.UNAVAILABLE,
          }));
        }
      } catch (e) {
        // Fetch error — telemetry offline
        setTelemetry(prev => ({
          ...prev,
          status: TelemetryStatus.OFFLINE,
          quality: QualityState.UNAVAILABLE,
        }));
      }
    };

    // Initial poll
    pollLiveTelemetry();

    // Set up interval
    timerRefQuality.current = setInterval(pollLiveTelemetry, TELEMETRY_POLL_INTERVAL);
  }, []);

  // -------------------------------------------------------------------------
  // Prediction sending
  // -------------------------------------------------------------------------

  const sendPrediction = useCallback(async () => {
    if (mode === "demo") {
      // Demo mode: use simulator
      if (!window.dashboardSimulator) {
        // Initialize simulator if not already done
        window.dashboardSimulator = window.dashboardSimulator || {
          soc: 85.0,
          speed: 42.0,
          altitude: 150.0,
          temp: 18.0,
          distance: 0.0,
          timeMin: 0.0,
          motorPower: 6.0,
          auxPower: 0.6,
          regen: 0.0,
          battVolt: 348.0,
          battTemp: 24.0,
          targetSpeed: 48.0,
          phase: 0,
          route: [],
          routeTotalKm: 42.6,
          reset() {
            this.soc = 85.0;
            this.speed = 42.0;
            this.altitude = 150.0;
            this.temp = 18.0;
            this.distance = 0.0;
            this.timeMin = 0.0;
            this.motorPower = 6.0;
            this.auxPower = 0.6;
            this.regen = 0.0;
            this.battVolt = 348.0;
            this.battTemp = 24.0;
            this.targetSpeed = 48.0;
            this.phase = 0;
            this.route = [];
            this.routeTotalKm = 42.6;
          },
          tick(dt) {
            this.phase += dt;
            if (Math.random() < 0.05) {
              this.targetSpeed = Math.min(95, Math.max(20, this.targetSpeed + (Math.random() - 0.5) * 18));
            }
            this.speed = this.targetSpeed + Math.sin(this.phase * 0.8) * 4;
            this.speed = Math.max(0, this.speed);

            const dKm = (this.speed / 3.6) * dt / 1000;
            this.distance += dKm;
            this.timeMin += dt / 60;

            const prog = (this.distance % this.routeTotalKm) / this.routeTotalKm;
            const idx = Math.min(this.route.length - 1, Math.floor(prog * this.route.length));
            this.altitude = this.route[idx].altitude_m + Math.sin(this.phase * 0.3) * 3;

            this.temp += (20.0 - this.temp) * 0.002 + (Math.random() - 0.5) * 0.2;
            this.temp = Math.min(30, Math.max(5, this.temp));

            this.motorPower = Math.max(0, this.speed * 0.28 + (Math.random() - 0.4) * 3);
            this.auxPower = 0.5 + Math.sin(this.phase * 0.05) * 0.2;
            this.regen = this.speed > 5 && Math.random() < 0.12 ? -Math.min(12, this.motorPower * 0.8) : 0;

            this.battVolt = 320 + this.soc * 0.42 + Math.sin(this.phase) * 2;
            this.battTemp = 23 + this.motorPower * 0.15;
          },
        };
      }

      const sim = window.dashboardSimulator;
      sim.tick(pollMs / 1000);
      const before = sim.distance;

      try {
        const data = await postPrediction(buildPayload());
        setLastPred(data);
        setPredictionReady(true);
        setLastError(null);
        if (mode === "demo") sim.applyConsumption(data.predicted_energy_kwh_per_km, sim.distance - before);
        setHistory((h) => {
          const next = [...h, { t: Date.now(), pred: data.predicted_energy_kwh_per_km }];
          return next.length > 60 ? next.slice(next.length - 60) : next;
        });
      } catch (e) {
        setLastError(e.message || "API unreachable");
        setPredictionReady(false);
      }
      render();
    } else {
      // Live mode: send prediction with live telemetry + route terrain
      try {
        const payload = buildPayload();
        if (!payload) {
          setLastError("No payload data");
          return;
        }

        const response = await fetch("/live/prediction", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          const errData = await response.json();
          setLastError(errData.detail || "Prediction failed");
          setPredictionReady(false);
          return;
        }

        const data = await response.json();
        setLastPred(data);
        setPredictionReady(true);
        setLastError(null);

        // Update telemetry state from the response/route status
        // In production, would extract telemetry from the prediction response
        // For now, update based on what we can infer from the response
        if (data.telemetry_quality) {
          setTelemetry({
            signals: data.telemetry_signals || [],
            status: TelemetryStatus.OK,
            quality: data.telemetry_quality,
            age_ms: data.telemetry_age_ms || 0,
            source: data.telemetry_source || "none",
          });
        }

        // Update confidence from prediction response
        if (data.confidence) {
          setConfidence({
            score: data.confidence.score,
            level: data.confidence.level,
            components: data.confidence.components,
          });
        }

        // Update sensor quality from prediction response
        if (data.sensor_quality) {
          setSensorQuality({
            overall_rating: data.sensor_quality,
            details: {},
          });
        }

        // Update route status
        if (data.route) {
          setRouteStatus({
            available: data.route.available,
            terrain_features_available: data.route.terrain_features_available,
            status: data.route.available ? "available" : "unavailable",
          });
        }

        // Update history
        setHistory((h) => {
          const next = [...h, { t: Date.now(), pred: data.predicted_energy_kwh_per_km }];
          return next.length > 60 ? next.slice(next.length - 60) : next;
        });
      } catch (e) {
        setLastError(e.message || "Prediction request failed");
        setPredictionReady(false);
        // Reset confidence and route status on error
        setConfidence({
          score: 0,
          level: "high",
          components: {
            ood_contribution: 0,
            missing_contribution: 0,
            route_contribution: 0,
            width_contribution: 0,
          },
        });
        setRouteStatus({
          available: false,
          terrain_features_available: false,
          status: "unavailable",
        });
        setSensorQuality({
          overall_rating: "unknown",
          details: {},
        });
        // Also set telemetry to offline on error
        setTelemetry({
          signals: [],
          status: TelemetryStatus.OFFLINE,
          quality: QualityState.UNAVAILABLE,
          age_ms: 0,
          source: "none",
        });
      }
    }
  }, [mode, pollMs, buildPayload]);

  // -------------------------------------------------------------------------
  // Start/pause/reset functions
  // -------------------------------------------------------------------------

  const start = useCallback(() => {
    setRunning((runningNow) => {
      if (runningNow) return runningNow;
      if (mode === "live") {
        // In live mode, start telemetry polling
        startLiveTelemetryPolling();
      }
      sendPrediction();
      timerRef.current = setInterval(sendPrediction, pollMs);
      return true;
    });
  }, [mode, pollMs, sendPrediction, startLiveTelemetryPolling]);

  const pause = useCallback(() => {
    clearInterval(timerRef.current);
    timerRef.current = null;
    setRunning(false);
  }, []);

  const reset = useCallback(() => {
    pause();
    // Reset dashboard state
    setTelemetry({
      signals: [],
      status: TelemetryStatus.OFFLINE,
      quality: QualityState.UNAVAILABLE,
      age_ms: 0,
      source: "none",
    });
    setRouteStatus({
      available: false,
      terrain_features_available: false,
      status: "unavailable",
    });
    setConfidence({
      score: 0,
      level: "high",
      components: {
        ood_contribution: 0,
        missing_contribution: 0,
        route_contribution: 0,
        width_contribution: 0,
      },
    });
    setSensorQuality({
      overall_rating: "unknown",
      details: {},
    });
    setHistory([]);
    setLastPred(null);
    setLastError(null);
    render();
  }, [pause, render]);

  // -------------------------------------------------------------------------
  // Effect: initialize on mount
  // -------------------------------------------------------------------------

  useEffect(() => {
    // Initialize simulator for demo mode (only in demo, never as LIVE)
    if (mode === "demo") {
      window.dashboardSimulator = window.dashboardSimulator || {
        soc: 85.0,
        speed: 42.0,
        altitude: 150.0,
        temp: 18.0,
        distance: 0.0,
        timeMin: 0.0,
        motorPower: 6.0,
        auxPower: 0.6,
        regen: 0.0,
        battVolt: 348.0,
        battTemp: 24.0,
        targetSpeed: 48.0,
        phase: 0,
        route: [],
        routeTotalKm: 42.6,
        reset() {
          this.soc = 85.0;
          this.speed = 42.0;
          this.altitude = 150.0;
          this.temp = 18.0;
          this.distance = 0.0;
          this.timeMin = 0.0;
          this.motorPower = 6.0;
          this.auxPower = 0.6;
          this.regen = 0.0;
          this.battVolt = 348.0;
          this.battTemp = 24.0;
          this.targetSpeed = 48.0;
          this.phase = 0;
          this.route = [];
          this.routeTotalKm = 42.6;
        },
        tick(dt) {
          this.phase += dt;
          if (Math.random() < 0.05) {
            this.targetSpeed = Math.min(95, Math.max(20, this.targetSpeed + (Math.random() - 0.5) * 18));
          }
          this.speed = this.targetSpeed + Math.sin(this.phase * 0.8) * 4;
          this.speed = Math.max(0, this.speed);

          const dKm = (this.speed / 3.6) * dt / 1000;
          this.distance += dKm;
          this.timeMin += dt / 60;

          const prog = (this.distance % this.routeTotalKm) / this.routeTotalKm;
          const idx = Math.min(this.route.length - 1, Math.floor(prog * this.route.length));
          this.altitude = this.route[idx].altitude_m + Math.sin(this.phase * 0.3) * 3;

          this.temp += (20.0 - this.temp) * 0.002 + (Math.random() - 0.5) * 0.2;
          this.temp = Math.min(30, Math.max(5, this.temp));

          this.motorPower = Math.max(0, this.speed * 0.28 + (Math.random() - 0.4) * 3);
          this.auxPower = 0.5 + Math.sin(this.phase * 0.05) * 0.2;
          this.regen = this.speed > 5 && Math.random() < 0.12 ? -Math.min(12, this.motorPower * 0.8) : 0;

          this.battVolt = 320 + this.soc * 0.42 + Math.sin(this.phase) * 2;
          this.battTemp = 23 + this.motorPower * 0.15;
        },
      };
    } else {
      // Live mode: initialize telemetry
      startLiveTelemetryPolling();
    }

    // Fetch health and model info
    fetchHealth().then(setApiConnected);
    fetchModelInfo().then(setModelInfo);

    // Set up health check timer
    const healthTimer = setInterval(() => fetchHealth().then(setApiConnected), 5000);

    // Poll live telemetry if in live mode
    if (mode === "live") {
      startLiveTelemetryPolling();
    }

    return () => {
      clearInterval(timerRef.current);
      clearInterval(timerRefQuality.current);
      clearInterval(healthTimer);
    };
  }, [mode, startLiveTelemetryPolling, fetchHealth, fetchModelInfo, buildPayload, sendPrediction]);

  // -------------------------------------------------------------------------
  // UI: change polling interval (live mode only)
  // -------------------------------------------------------------------------

  const changePollMs = useCallback(
    (ms) => {
      setPollMs(ms);
      if (running && mode === "live") {
        clearInterval(timerRefQuality.current);
        timerRefQuality.current = setInterval(() => {}, 1);
      }
    },
    [running, mode],
  );

  // -------------------------------------------------------------------------
  // Return everything the UI needs
  // -------------------------------------------------------------------------

  return {
    sim: window.dashboardSimulator,  // still provided for backward compat
    mode,
    running,
    pollMs,
    apiConnected,
    predictionReady,
    modelInfo,
    lastPred,
    lastError,
    history,
    telemetry,
    routeStatus,
    confidence,
    sensorQuality,
    start,
    pause,
    reset,
    changePollMs,
    // Explicit simulator labeling for demo mode
    simulatorInfo: mode === "demo"
      ? {
          label: "SIMULATOR — DEVELOPMENT ONLY",
          description: "Simulated telemetry for development and testing. Does not represent real vehicle data.",
        }
      : null,
  };
}
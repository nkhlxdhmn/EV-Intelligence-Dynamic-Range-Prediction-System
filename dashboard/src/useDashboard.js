import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchHealth,
  fetchModelInfo,
  fetchLiveStatus,
  fetchLiveTelemetry,
  fetchLivePrediction,
  postPrediction,
  postSimulatorReset,
  postSimulatorStep,
} from "./api";

// ---------------------------------------------------------------------------
// Mode selection + constants
// ---------------------------------------------------------------------------

// ?telemetry=1 => LIVE mode; otherwise SIMULATOR (demo) mode driven by the
// backend physics simulator (src/simulator). No client-side telemetry is ever
// fabricated.
const LIVE_QUERY = (() => {
  const params = new URLSearchParams(window.location.search);
  return params.get("telemetry") === "1";
})();

const TELEMETRY_POLL_INTERVAL = 3000; // live telemetry status polling
const SIM_BASE_STEPS = 2; // sim steps per demo tick at 1x (1 sim-second)
const SIM_SPEEDS = { 1: 2, 2: 4, 4: 8, 8: 16 }; // multiplier -> n_steps
const DEFAULT_SEED = 1;

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

const EMPTY_TELEMETRY = {
  signals: [],
  status: TelemetryStatus.OFFLINE,
  quality: QualityState.UNAVAILABLE,
  age_ms: 0,
  source: "none",
};

const EMPTY_LIVE_STATUS = {
  telemetry_connected: false,
  status: "offline",
  provider: null,
  available_signals: [],
  required_signal_status: {},
  prediction_ready: false,
  prediction_ready_reason: "no telemetry source connected",
  route_ready: false,
};

const ROUTE_UNAVAILABLE = {
  available: false,
  terrain_features_available: false,
  status: "unavailable",
};

const ZERO_CONFIDENCE = {
  score: 0,
  level: "high",
  components: {
    ood_contribution: 0,
    missing_contribution: 0,
    route_contribution: 0,
    width_contribution: 0,
  },
};

// ---------------------------------------------------------------------------
// useDashboard hook
// ---------------------------------------------------------------------------

export function useDashboard() {
  const [mode, setMode] = useState(() => (LIVE_QUERY ? "live" : "demo"));
  const [running, setRunning] = useState(false);
  const [pollMs, setPollMs] = useState(LIVE_QUERY ? 3000 : 1500);
  const [simSpeed, setSimSpeed] = useState(1); // simulation multiplier (1x..8x)
  const [seed, setSeed] = useState(DEFAULT_SEED);
  const [apiConnected, setApiConnected] = useState(false);
  const [predictionReady, setPredictionReady] = useState(false);
  const [modelInfo, setModelInfo] = useState(null);
  const [lastPred, setLastPred] = useState(null);
  const [lastPredAt, setLastPredAt] = useState(null);
  const [lastError, setLastError] = useState(null);
  const [history, setHistory] = useState([]);

  // SIMULATOR (demo) state — backend physics simulator output, always labeled.
  const [simTelemetry, setSimTelemetry] = useState(null);
  const [simRoute, setSimRoute] = useState(null);
  const [simScenario, setSimScenario] = useState(null);
  const [scenarioInfo, setScenarioInfo] = useState(null);

  // LIVE telemetry state
  const [telemetry, setTelemetry] = useState(EMPTY_TELEMETRY);
  const [liveStatus, setLiveStatus] = useState(EMPTY_LIVE_STATUS);
  const [routeStatus, setRouteStatus] = useState(ROUTE_UNAVAILABLE);
  const [confidence, setConfidence] = useState(ZERO_CONFIDENCE);

  // Speed trace for a client-computed acceleration estimate from REAL samples.
  const speedTraceRef = useRef([]);

  const timerRef = useRef(null);
  const statusTimerRef = useRef(null);
  const seedRef = useRef(seed);
  seedRef.current = seed;
  const simSpeedRef = useRef(simSpeed);
  simSpeedRef.current = simSpeed;

  // -------------------------------------------------------------------------
  // Demo (SIMULATOR) loop
  // -------------------------------------------------------------------------

  const simSteps = () => SIM_SPEEDS[simSpeedRef.current] || SIM_BASE_STEPS;

  const applySimSnapshot = useCallback((snap) => {
    setSimTelemetry(snap.telemetry || null);
    setSimRoute(snap.route_terrain || null);
    setSimScenario(snap.scenario_id || null);
    setScenarioInfo(snap.scenario || null);
  }, []);

  const resetSimulator = useCallback(async () => {
    try {
      const snap = await postSimulatorReset(seedRef.current, simSteps());
      applySimSnapshot(snap);
      return snap;
    } catch (e) {
      setLastError(e.message || "Simulator backend unavailable");
      return null;
    }
  }, [applySimSnapshot]);

  const randomize = useCallback(async () => {
    // RANDOMIZE SCENARIO: a fresh coherent scenario is produced server-side
    // from a new seed (route, driving style, traffic, SOC, temperature).
    const s = Math.floor(Math.random() * 2147483647);
    try {
      const snap = await postSimulatorReset(s, simSteps());
      applySimSnapshot(snap);
      setSeed(s);
      return snap;
    } catch (e) {
      setLastError(e.message || "Simulator backend unavailable");
      return null;
    }
  }, [applySimSnapshot]);

  const applyPrediction = useCallback((pred) => {
    setLastPred(pred);
    setLastPredAt(Date.now());
    setPredictionReady(true);
    setLastError(null);
    if (pred && pred.confidence) {
      setConfidence({
        score: pred.confidence.score,
        level: pred.confidence.level,
        components: pred.confidence.components,
      });
    }
    setHistory((h) => {
      if (!pred || !Number.isFinite(pred.predicted_energy_kwh_per_km)) return h;
      const next = [...h, { t: Date.now(), pred: pred.predicted_energy_kwh_per_km }];
      return next.length > 60 ? next.slice(next.length - 60) : next;
    });
  }, []);

  // -------------------------------------------------------------------------
  // Prediction sending
  // -------------------------------------------------------------------------

  const sendDemoPrediction = useCallback(async () => {
    try {
      let snap = await postSimulatorStep(simSteps());
      // Restart the scenario when the simulation reaches its route end.
      if (snap.finished) {
        snap = (await resetSimulator()) || snap;
      }
      applySimSnapshot(snap);
      const payload = {
        telemetry: snap.telemetry,
        route_terrain: snap.route_terrain,
        reserve_soc_pct: 10.0,
      };
      const data = await postPrediction(payload);
      applyPrediction(data);
      pushSpeedTrace(snap.telemetry);
    } catch (e) {
      setLastError(e.message || "API unreachable");
      setPredictionReady(false);
    }
  }, [applyPrediction, applySimSnapshot, resetSimulator]);

  const sendLivePrediction = useCallback(async () => {
    try {
      const data = await fetchLivePrediction();
      if (!data.available || !data.prediction) {
        setLastPred(null);
        setPredictionReady(false);
        setLastError(data.message || "Live prediction unavailable");
        if (data.route) {
          setRouteStatus({
            available: data.route.available,
            terrain_features_available: data.route.terrain_features_available,
            status: data.route.available ? "available" : "unavailable",
          });
        }
        return;
      }
      const pred = data.prediction;
      pred.status = data.status || pred.status;
      applyPrediction(pred);
      if (data.route) {
        setRouteStatus({
          available: data.route.available,
          terrain_features_available: data.route.terrain_features_available,
          status: data.route.available ? "available" : "unavailable",
        });
      }
    } catch (e) {
      setLastError(e.message || "Prediction request failed");
      setPredictionReady(false);
      setConfidence(ZERO_CONFIDENCE);
      setRouteStatus(ROUTE_UNAVAILABLE);
    }
  }, [applyPrediction]);

  const sendPrediction = useCallback(() => {
    return mode === "demo" ? sendDemoPrediction() : sendLivePrediction();
  }, [mode, sendDemoPrediction, sendLivePrediction]);

  // -------------------------------------------------------------------------
  // Live telemetry polling (LIVE mode)
  // -------------------------------------------------------------------------

  const pollLiveTelemetry = useCallback(async () => {
    try {
      const [statusData, telemetryData] = await Promise.all([
        fetchLiveStatus(),
        fetchLiveTelemetry(),
      ]);
      const status = statusData ? statusData.status : "offline";
      const source = (telemetryData && telemetryData.source) || "none";
      const signals = (telemetryData && telemetryData.signals) || [];

      let quality = QualityState.UNAVAILABLE;
      let telemetryStatus = TelemetryStatus.OFFLINE;
      const hasValid = signals.some(
        (s) => s.quality === "VALID" && s.value !== null && s.value !== undefined,
      );
      if (status === "ok" || hasValid) {
        quality = QualityState.VALID;
        telemetryStatus = TelemetryStatus.OK;
      } else if (signals.length > 0) {
        quality = QualityState.MISSING;
        telemetryStatus = TelemetryStatus.DEGRADED;
      }

      setTelemetry({
        signals,
        status: telemetryStatus,
        quality,
        age_ms: statusData ? statusData.age_ms || 0 : 0,
        source,
      });
      if (statusData) {
        setLiveStatus({
          telemetry_connected: statusData.telemetry_connected === true,
          status: statusData.status || "offline",
          provider: statusData.provider || null,
          available_signals: statusData.available_signals || [],
          required_signal_status: statusData.required_signal_status || {},
          prediction_ready: statusData.prediction_ready === true,
          prediction_ready_reason: statusData.prediction_ready_reason || null,
          route_ready: statusData.route_ready === true,
          mode: statusData.mode || null,
        });
        if (statusData.required_signal_status) {
          setRouteStatus((prev) => ({
            ...prev,
            available: statusData.route_ready === true,
            terrain_features_available: statusData.route_ready === true,
            status: statusData.route_ready ? "available" : "unavailable",
          }));
        }
      }
      // Record VALID speed samples for the acceleration estimate.
      const speedSig = signals.find((s) => s.name === "vehicle_speed_kmh" && s.quality === "VALID");
      if (speedSig && Number.isFinite(speedSig.value)) {
        pushSpeedTrace({ speed_kmh: speedSig.value });
      }
    } catch {
      setTelemetry(EMPTY_TELEMETRY);
    }
  }, []);

  const pushSpeedTrace = useCallback((t) => {
    const v = t && t.speed_kmh;
    if (!Number.isFinite(v)) return;
    const trace = speedTraceRef.current;
    trace.push({ t: Date.now(), v });
    if (trace.length > 20) trace.shift();
  }, []);

  const startLiveTelemetryPolling = useCallback(() => {
    clearInterval(statusTimerRef.current);
    statusTimerRef.current = null;
    pollLiveTelemetry();
    statusTimerRef.current = setInterval(pollLiveTelemetry, TELEMETRY_POLL_INTERVAL);
  }, [pollLiveTelemetry]);

  // -------------------------------------------------------------------------
  // Start / pause / reset
  // -------------------------------------------------------------------------

  const start = useCallback(() => {
    if (running) return;
    setRunning(true);
    if (mode === "demo") {
      resetSimulator();
    } else {
      startLiveTelemetryPolling();
    }
    sendPrediction();
    timerRef.current = setInterval(sendPrediction, pollMs);
  }, [running, mode, pollMs, sendPrediction, resetSimulator, startLiveTelemetryPolling]);

  const pause = useCallback(() => {
    clearInterval(timerRef.current);
    timerRef.current = null;
    clearInterval(statusTimerRef.current);
    statusTimerRef.current = null;
    setRunning(false);
  }, []);

  const reset = useCallback(() => {
    pause();
    setHistory([]);
    setLastPred(null);
    setLastPredAt(null);
    setLastError(null);
    setPredictionReady(false);
    setSimTelemetry(null);
    setSimRoute(null);
    setSimScenario(null);
    setScenarioInfo(null);
    setTelemetry(EMPTY_TELEMETRY);
    setLiveStatus(EMPTY_LIVE_STATUS);
    setRouteStatus(ROUTE_UNAVAILABLE);
    setConfidence(ZERO_CONFIDENCE);
    speedTraceRef.current = [];
  }, [pause]);

  const switchMode = useCallback(
    (next) => {
      if (next === mode) return;
      pause();
      setHistory([]);
      setLastPred(null);
      setLastPredAt(null);
      setLastError(null);
      setPredictionReady(false);
      setSimTelemetry(null);
      setSimRoute(null);
      setSimScenario(null);
      setScenarioInfo(null);
      setTelemetry(EMPTY_TELEMETRY);
      setLiveStatus(EMPTY_LIVE_STATUS);
      setRouteStatus(ROUTE_UNAVAILABLE);
      setConfidence(ZERO_CONFIDENCE);
      speedTraceRef.current = [];
      setMode(next);
      // Persist the mode in the URL so reloads keep the same operating mode.
      const url = new URL(window.location.href);
      if (next === "live") {
        url.searchParams.set("telemetry", "1");
      } else {
        url.searchParams.delete("telemetry");
      }
      window.history.replaceState(null, "", url.toString());
    },
    [mode, pause],
  );

  // -------------------------------------------------------------------------
  // Mount: health + model info
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (mode === "live") {
      startLiveTelemetryPolling();
    }
    fetchHealth().then(setApiConnected);
    fetchModelInfo().then(setModelInfo);
    const healthTimer = setInterval(() => fetchHealth().then(setApiConnected), 5000);

    return () => {
      clearInterval(timerRef.current);
      clearInterval(statusTimerRef.current);
      clearInterval(healthTimer);
    };
  }, [mode, startLiveTelemetryPolling]);

  const changePollMs = useCallback((ms) => setPollMs(ms), []);
  const changeSimSpeed = useCallback((m) => setSimSpeed(m), []);

  const changeSeed = useCallback((s) => setSeed(Math.max(0, Math.floor(Number(s) || 0))), []);

  // -------------------------------------------------------------------------
  // Derived values
  // -------------------------------------------------------------------------

  // Acceleration estimate from the real speed trace (client-side, honest).
  const accelerationMps2 = (() => {
    const tr = speedTraceRef.current;
    if (tr.length >= 2) {
      const a = tr[tr.length - 1];
      const b = tr[tr.length - 2];
      const dt = (a.t - b.t) / 1000;
      if (dt > 0) return ((a.v - b.v) / 3.6) / dt;
    }
    return null;
  })();

  const reliability = {
    score: confidence.score,
    level: confidence.level,
    status: lastPred ? lastPred.status : null,
    components: confidence.components,
  };

  return {
    mode,
    running,
    pollMs,
    simSpeed,
    seed,
    apiConnected,
    predictionReady,
    modelInfo,
    lastPred,
    lastPredAt,
    lastError,
    history,
    simTelemetry,
    simRoute,
    simScenario,
    scenarioInfo,
    telemetry,
    liveStatus,
    routeStatus,
    confidence,
    reliability,
    accelerationMps2,
    start,
    pause,
    reset,
    switchMode,
    changePollMs,
    changeSimSpeed,
    changeSeed,
    randomize,
    demoLabel: "SIMULATOR — DEVELOPMENT ONLY",
    demoDescription:
      "Backend physics simulator (src/simulator). Development data — does not represent real vehicle telemetry.",
  };
}

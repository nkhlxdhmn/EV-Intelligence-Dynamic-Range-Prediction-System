// EV RANGE MONITOR - API client. No model logic; only talks to the backend.

// API base for cross-origin deployments (e.g. a Vercel-hosted frontend calling
// a Docker-hosted backend). When unset, all calls are same-origin relative
// paths (local dev proxy / Docker single-container) and behavior is unchanged.
const API_BASE = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

export const API = {
  health: `${API_BASE}/health`,
  info: `${API_BASE}/model/info`,
  predict: `${API_BASE}/predict`,
  // Backend physics simulator (STEP 16) — drives demo mode.
  simulatorReset: `${API_BASE}/simulator/reset`,
  simulatorStep: `${API_BASE}/simulator/step`,
  // Live telemetry endpoints (STEP 15)
  liveStatus: `${API_BASE}/live/status`,
  liveTelemetry: `${API_BASE}/live/telemetry`,
  livePrediction: `${API_BASE}/live/prediction`,
};

export async function fetchHealth() {
  try {
    const r = await fetch(API.health, { headers: { Accept: "application/json" } });
    if (!r.ok) return false;
    const data = await r.json();
    return data.status === "ok";
  } catch {
    return false;
  }
}

export async function fetchModelInfo() {
  try {
    const r = await fetch(API.info, { headers: { Accept: "application/json" } });
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

export async function postPrediction(payload) {
  const r = await fetch(API.predict, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    let detail = `Prediction failed (${r.status})`;
    try {
      const err = await r.json();
      if (err && (err.detail || err.message)) {
        detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
      }
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  return r.json();
}

// Live telemetry fetch functions

export async function fetchLiveStatus() {
  try {
    const r = await fetch(API.liveStatus, { headers: { Accept: "application/json" } });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

export async function fetchLiveTelemetry() {
  try {
    const r = await fetch(API.liveTelemetry, { headers: { Accept: "application/json" } });
    if (!r.ok) return { signals: [], count: 0 };
    return await r.json();
  } catch {
    return { signals: [], count: 0 };
  }
}

// Live route-aware prediction from the connected telemetry source.
// The endpoint reads its own telemetry; no payload body is required.
export async function fetchLivePrediction() {
  const r = await fetch(API.livePrediction, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({}),
  });
  if (!r.ok) {
    let detail = `Live prediction failed (${r.status})`;
    try {
      const err = await r.json();
      if (err && (err.detail || err.message)) {
        detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
      }
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  return r.json();
}

// ---- Backend physics simulator (demo mode) ---------------------------------

export async function postSimulatorReset(seed = 1, nSteps = 2) {
  const qs = new URLSearchParams({ seed: String(seed), n_steps: String(nSteps) });
  const r = await fetch(`${API.simulatorReset}?${qs}`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!r.ok) {
    let detail = `Simulator reset failed (${r.status})`;
    try {
      const err = await r.json();
      if (err && (err.detail || err.message)) detail = err.detail;
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  return r.json();
}

export async function postSimulatorStep(nSteps = 4) {
  const qs = new URLSearchParams({ n_steps: String(nSteps) });
  const r = await fetch(`${API.simulatorStep}?${qs}`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!r.ok) {
    let detail = `Simulator step failed (${r.status})`;
    try {
      const err = await r.json();
      if (err && (err.detail || err.message)) detail = err.detail;
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  return r.json();
}
// EV RANGE MONITOR - API client. No model logic; only talks to the backend.

export const API = {
  health: "/health",
  info: "/model/info",
  predict: "/predict",
  // Live telemetry endpoints (STEP 15)
  liveStatus: "/live/status",
  liveTelemetry: "/live/telemetry",
  liveConnect: "/live/connect",
  liveDisconnect: "/live/disconnect",
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

export async function postLiveConnect(provider = "obd_ii", format_type = "json", config = null) {
  try {
    const r = await fetch(API.liveConnect, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, format_type, config }),
    });
    if (!r.ok) {
      let detail = `Connection failed (${r.status})`;
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
    return await r.json();
  } catch (e) {
    throw new Error(e.message || "Failed to connect to telemetry");
  }
}

export async function postLiveDisconnect() {
  try {
    const r = await fetch(API.liveDisconnect, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!r.ok) {
      let detail = `Disconnection failed (${r.status})`;
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
    return await r.json();
  } catch (e) {
    throw new Error(e.message || "Failed to disconnect telemetry");
  }
}
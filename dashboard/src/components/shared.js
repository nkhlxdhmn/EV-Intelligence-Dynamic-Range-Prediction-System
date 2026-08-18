// Shared display helpers for the EV Intelligence dashboard.

export const fmt = (v, digits, unit) => {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  const s = Number(v).toFixed(digits);
  return unit ? s + " " + unit : s;
};

// Monospace number with thousands grouping (e.g. 2,840) for engineering rows.
export const grp = (v, digits) => {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  const n = Number(v);
  const s = digits !== undefined ? n.toFixed(digits) : String(n);
  const [int, dec] = s.split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return dec ? grouped + "." + dec : grouped;
};

export const nowClock = (tz = "local") => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  if (tz === "utc") {
    return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
  }
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

export const qualityToLabel = (quality) => {
  const labels = {
    VALID: "VALID",
    MISSING: "MISSING",
    STALE: "STALE",
    INVALID: "INVALID",
    OUT_OF_RANGE: "OUT OF RANGE",
    UNAVAILABLE: "UNAVAILABLE",
  };
  return labels[quality] || quality;
};

export const routeStatusLabel = (status) => {
  const labels = {
    available: "ON ROUTE",
    incomplete: "INCOMPLETE",
    unavailable: "NO ROUTE",
  };
  return labels[status] || status;
};

export const statusToText = (status) => {
  const labels = {
    OK: "NOMINAL",
    DEGRADED: "DEGRADED",
    INSUFFICIENT_DATA: "INSUFFICIENT DATA",
    OFFLINE: "OFFLINE",
    INSUFFICIENT_TELEMETRY: "INSUFFICIENT TELEMETRY",
    ROUTE_TERRAIN_UNAVAILABLE: "ROUTE UNAVAILABLE",
  };
  return labels[status] || status || "N/A";
};

// Reliability level is a composite index (NOT a probability). Only the
// level string is shown; never a misleading percentage.
export const reliabilityLevelText = (level) =>
  ({ high: "HIGH", medium: "MEDIUM", low: "LOW" }[level] || "HIGH");

export const reliabilityLevelClass = (level) => {
  const classes = { high: "rel-high", medium: "rel-medium", low: "rel-low" };
  return classes[level] || "rel-high";
};

// Scenario label helpers (backend scenario metadata).
export const drivingStyleLabel = (s) =>
  ({ eco: "ECO", balanced: "BALANCED", sporty: "SPORTY" }[s] || s || "—");
export const routeProfileLabel = (s) =>
  ({ highway: "HIGHWAY", hilly: "HILLY", mountain: "MOUNTAIN", flat: "FLAT" }[s] || s || "—");
export const trafficLabel = (s) =>
  ({ light: "LIGHT", moderate: "MODERATE", heavy: "HEAVY" }[s] || s || "—");

// Route elevation stats computed from the actual terrain points.
// Returns nulls when no real profile is present (never fabricated).
export function routeStatsFromPoints(points) {
  if (!points || points.length < 2) {
    return { gain: null, loss: null, gradient: null, horizon: null };
  }
  let gain = 0;
  let loss = 0;
  let prev = points[0].altitude_m;
  for (const p of points.slice(1)) {
    const d = p.altitude_m - prev;
    if (d > 0) gain += d;
    else loss += -d;
    prev = p.altitude_m;
  }
  const dist = points[points.length - 1].offset_km - points[0].offset_km || 1;
  const net =
    ((points[points.length - 1].altitude_m - points[0].altitude_m) / (dist * 1000)) * 100;
  return {
    gain: Math.round(gain),
    loss: Math.round(loss),
    gradient: net.toFixed(2),
    horizon: Math.abs(dist) < 1e-9 ? null : dist.toFixed(1),
  };
}

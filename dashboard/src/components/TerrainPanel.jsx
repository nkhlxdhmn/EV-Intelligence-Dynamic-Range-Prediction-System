import { useMemo } from "react";
import { routeStatsFromPoints, fmt, routeProfileLabel } from "./shared";

const W = 720;
const H = 190;
const PAD = { top: 12, right: 12, bottom: 20, left: 46 };

// Elevation profile of the upcoming terrain. In SIMULATOR mode the profile is
// the real backend route (labeled SIMULATED TERRAIN); in LIVE mode the chart
// only appears when real route terrain is available — never fabricated.
export default function TerrainPanel({ mode, simRoute, simDistanceKm, routeStatus, scenarioInfo }) {
  const points = simRoute && simRoute.points ? simRoute.points : null;
  const stats = routeStatsFromPoints(points);
  const isSim = mode === "demo";
  const available = isSim ? points !== null : routeStatus.available === true;

  const chart = useMemo(() => {
    if (!points || points.length < 2) return null;
    const offs = points.map((p) => p.offset_km);
    const alts = points.map((p) => p.altitude_m);
    const minAlt = Math.min(...alts);
    const maxAlt = Math.max(...alts);
    const altSpan = maxAlt - minAlt || 1;
    const altPad = altSpan * 0.18;
    const lo = minAlt - altPad;
    const hi = maxAlt + altPad;
    const span = hi - lo || 1;
    const maxOff = offs[offs.length - 1] || 1;

    const iw = W - PAD.left - PAD.right;
    const ih = H - PAD.top - PAD.bottom;
    const x = (o) => PAD.left + (o / maxOff) * iw;
    const y = (a) => PAD.top + (1 - (a - lo) / span) * ih;

    const pts = points.map((p) => ({ x: x(p.offset_km), y: y(p.altitude_m) }));
    let d = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 1; i < pts.length; i++) {
      const p0 = pts[i - 1];
      const p1 = pts[i];
      d += ` C ${(p0.x + p1.x) / 2} ${p0.y}, ${(p0.x + p1.x) / 2} ${p1.y}, ${p1.x} ${p1.y}`;
    }
    const area = `${d} L ${pts[pts.length - 1].x} ${H - PAD.bottom} L ${pts[0].x} ${H - PAD.bottom} Z`;

    // distance markers every 1 km
    const distMarks = [];
    for (let k = 0; k <= Math.floor(maxOff); k++) {
      distMarks.push({ km: k, x: x(k) });
    }

    const yTicks = [0, 1, 2, 3].map((k) => {
      const v = lo + (k / 3) * span;
      return { v, y: PAD.top + (k / 3) * ih };
    });

    return { pts, d, area, maxOff, lo, hi, distMarks, yTicks };
  }, [points]);

  const sourceLabel = isSim
    ? simRoute && simRoute.source === "SIMULATOR_ROUTE"
      ? "SIMULATED TERRAIN"
      : "NONE"
    : available
      ? routeStatus.source || "ROUTE PROVIDER"
      : "NONE";

  const profileName = isSim && scenarioInfo && scenarioInfo.route_profile
    ? routeProfileLabel(scenarioInfo.route_profile)
    : null;

  return (
    <section className="panel panel-terrain" aria-label="Route and terrain">
      <div className="section-head">
        <span className="section-no">05</span>
        <span className="section-title">ROUTE / TERRAIN</span>
        <span className="section-hint">{sourceLabel}</span>
      </div>
      {available && chart ? (
        <>
          <div className="terrain-canvas">
            <svg viewBox={`0 0 ${W} ${H}`} className="terrain-svg" role="img" aria-label="Upcoming elevation profile">
              {chart.yTicks.map((t, i) => (
                <g key={i}>
                  <line x1={PAD.left} x2={W - PAD.right} y1={t.y} y2={t.y} className="grid-line" />
                  <text x={PAD.left - 6} y={t.y + 3} className="axis-label" textAnchor="end">
                    {Math.round(t.v)} m
                  </text>
                </g>
              ))}
              {chart.distMarks.map((m) => (
                <g key={m.km}>
                  <line x1={m.x} x2={m.x} y1={PAD.top} y2={H - PAD.bottom} className="dist-mark" />
                  <text x={m.x} y={H - 5} className="axis-label" textAnchor="middle">
                    {m.km} km
                  </text>
                </g>
              ))}
              <path d={chart.area} className="terrain-area" />
              <path d={chart.d} className="terrain-line" />
              {/* vehicle position marker at the current offset (offset 0) */}
              <line
                x1={chart.pts[0].x}
                x2={chart.pts[0].x}
                y1={PAD.top - 6}
                y2={H - PAD.bottom}
                className="vehicle-line"
              />
              <circle cx={chart.pts[0].x} cy={chart.pts[0].y} r="4" className="vehicle-dot" />
              <text x={chart.pts[0].x + 7} y={chart.pts[0].y - 8} className="axis-label">
                VEHICLE
              </text>
            </svg>
          </div>
          <div className="terrain-stats">
            <div className="t-stat">
              <span className="t-label">NET GRADIENT</span>
              <span className="t-value">{stats.gradient !== null ? `${stats.gradient} %` : "—"}</span>
            </div>
            <div className="t-stat">
              <span className="t-label">GAIN</span>
              <span className="t-value">{stats.gain !== null ? `${stats.gain} m` : "—"}</span>
            </div>
            <div className="t-stat">
              <span className="t-label">LOSS</span>
              <span className="t-value">{stats.loss !== null ? `${stats.loss} m` : "—"}</span>
            </div>
            <div className="t-stat">
              <span className="t-label">LOOKAHEAD</span>
              <span className="t-value">{stats.horizon !== null ? `${stats.horizon} km` : "—"}</span>
            </div>
            {profileName && (
              <div className="t-stat">
                <span className="t-label">PROFILE</span>
                <span className="t-value">{profileName}</span>
              </div>
            )}
            <div className="t-stat">
              <span className="t-label">TRIP DIST</span>
              <span className="t-value">{Number.isFinite(simDistanceKm) ? fmt(simDistanceKm, 1, "km") : "—"}</span>
            </div>
          </div>
        </>
      ) : (
        <div className="terrain-empty">
          <div className="terrain-empty-title">
            {isSim ? "NO ROUTE DATA" : routeStatus.available ? "ROUTE READY" : "ROUTE TERRAIN UNAVAILABLE"}
          </div>
          <div className="terrain-empty-note">
            {isSim
              ? "start the simulator to build a route"
              : "no real route provider is connected — terrain is never fabricated"}
          </div>
        </div>
      )}
    </section>
  );
}
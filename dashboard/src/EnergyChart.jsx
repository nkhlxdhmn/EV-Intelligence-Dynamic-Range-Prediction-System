import { useMemo, useState } from "react";
import { fmt } from "./components/shared";

const W = 720;
const H = 210;
const PAD = { top: 14, right: 12, bottom: 20, left: 46 };

// Monotone cubic interpolation between points (smooth, no overshoot).
function smoothPath(pts) {
  if (pts.length < 2) return "";
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const p0 = pts[i - 1];
    const p1 = pts[i];
    const c1x = (p0.x + p1.x) / 2;
    const c1y = p0.y;
    const c2x = (p0.x + p1.x) / 2;
    const c2y = p1.y;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p1.x} ${p1.y}`;
  }
  return d;
}

export default function EnergyChart({ history, horizonKm }) {
  const [hover, setHover] = useState(null);

  const chart = useMemo(() => {
    const pts = (history || []).slice(-60);
    if (pts.length < 2) {
      return { ready: false, pts, points: [], yTicks: [], trend: null, trendOk: false };
    }
    const raw = pts.map((p) => Number(p.pred));
    let min = Math.min(...raw);
    let max = Math.max(...raw);
    if (max - min < 0.005) {
      const m = (min + max) / 2;
      min = m - 0.02;
      max = m + 0.02;
    }
    const padY = (max - min) * 0.12;
    min -= padY;
    max += padY;
    const span = max - min || 1;

    const iw = W - PAD.left - PAD.right;
    const ih = H - PAD.top - PAD.bottom;
    const x = (i) => PAD.left + (i / (pts.length - 1)) * iw;
    const y = (v) => PAD.top + (1 - (v - min) / span) * ih;

    const points = pts.map((p, i) => ({ x: x(i), y: y(p.pred), pred: p.pred, t: p.t }));

    const yTicks = [0, 1, 2, 3].map((k) => {
      const v = min + (k / 3) * span;
      return { v, y: PAD.top + (k / 3) * ih };
    });

    // Trend: current vs mean of the previous window (real history only).
    let trend = null;
    let trendOk = false;
    if (pts.length >= 6) {
      const last = pts[pts.length - 1].pred;
      const prev = pts.slice(-7, -1).map((p) => p.pred);
      const prevMean = prev.reduce((a, b) => a + b, 0) / prev.length;
      if (prevMean !== 0) {
        trend = ((last - prevMean) / Math.abs(prevMean)) * 100;
        trendOk = Number.isFinite(trend);
      }
    }

    return { ready: true, pts, points, yTicks, trend, trendOk };
  }, [history]);

  const nowValue = chart.pts.length
    ? chart.pts[chart.pts.length - 1].pred
    : null;
  const activePoint = hover !== null ? chart.points[hover] : null;

  const onMove = (e) => {
    if (!chart.points.length) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const scaleX = W / rect.width;
    const mx = (e.clientX - rect.left) * scaleX;
    let best = 0;
    let bestD = Infinity;
    chart.points.forEach((p, i) => {
      const d = Math.abs(p.x - mx);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    setHover(best);
  };

  return (
    <div className="energy-chart">
      <div className="chart-canvas">
        {chart.ready ? (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="energy-svg"
            role="img"
            aria-label="Predicted energy consumption over time"
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
          >
            {chart.yTicks.map((t, i) => (
              <g key={i}>
                <line x1={PAD.left} x2={W - PAD.right} y1={t.y} y2={t.y} className="grid-line" />
                <text x={PAD.left - 6} y={t.y + 3} className="axis-label" textAnchor="end">
                  {fmt(t.v, 3)}
                </text>
              </g>
            ))}
            <path d={smoothPath(chart.points)} className="energy-line" />
            {activePoint && (
              <g>
                <line
                  x1={activePoint.x}
                  x2={activePoint.x}
                  y1={PAD.top}
                  y2={H - PAD.bottom}
                  className="crosshair"
                />
                <circle cx={activePoint.x} cy={activePoint.y} r="4" className="energy-point" />
              </g>
            )}
            <circle
              cx={chart.points[chart.points.length - 1].x}
              cy={chart.points[chart.points.length - 1].y}
              r="4"
              className="energy-point energy-point-last"
            />
            <text
              x={chart.points[chart.points.length - 1].x - 8}
              y={chart.points[chart.points.length - 1].y - 10}
              className="axis-label axis-last"
              textAnchor="end"
            >
              {fmt(nowValue, 3)}
            </text>
            <text x={W - PAD.right} y={H - 5} className="axis-label" textAnchor="end">
              last {chart.pts.length} predictions
            </text>
          </svg>
        ) : (
          <div className="chart-empty">WAITING FOR PREDICTION</div>
        )}
        {activePoint && (
          <div
            className="chart-tooltip"
            style={{
              left: `${(activePoint.x / W) * 100}%`,
              top: `${Math.max(4, (activePoint.y / H) * 100 - 26)}%`,
            }}
          >
            <span className="tooltip-val">{fmt(activePoint.pred, 3)} kWh/km</span>
            {activePoint.t && (
              <span className="tooltip-time">
                {new Date(activePoint.t).toLocaleTimeString()}
              </span>
            )}
          </div>
        )}
      </div>
      {chart.trendOk && (
        <div className={`trend ${chart.trend >= 0 ? "trend-up" : "trend-down"}`}>
          <span className="trend-arrow">{chart.trend >= 0 ? "↑" : "↓"}</span>
          <span className="trend-val">{Math.abs(chart.trend).toFixed(1)}%</span>
          <span className="trend-note">vs previous window</span>
        </div>
      )}
      <div className="chart-foot">
        <span>{horizonKm ? `${horizonKm} km prediction horizon` : "prediction horizon"}</span>
        <span className="chart-foot-now">
          {nowValue !== null ? `${fmt(nowValue, 3)} kWh/km` : "no prediction"}
        </span>
      </div>
    </div>
  );
}
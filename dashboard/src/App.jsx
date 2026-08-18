import { useDashboard } from "./useDashboard";
import EnergyChart from "./EnergyChart";

const fmt = (v, digits, unit) => {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  const s = Number(v).toFixed(digits);
  return unit ? s + " " + unit : s;
};

const nowClock = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

// Quality state display helper
const qualityToLabel = (quality) => {
  const labels = {
    VALID: "Good",
    MISSING: "Missing",
    STALE: "Stale",
    INVALID: "Invalid",
    OUT_OF_RANGE: "Out of Range",
    UNAVAILABLE: "Unavailable",
  };
  return labels[quality] || quality;
};

// Route status display helper
const routeStatusLabel = (status) => {
  const labels = {
    available: "ON ROUTE",
    incomplete: "INCOMPLETE",
    unavailable: "NO ROUTE",
  };
  return labels[status] || status;
};

const routeStats = (sim, mode, running) => {
  const distance = sim && Number.isFinite(sim.distance) ? sim.distance : 0;
  const altitude = sim && Number.isFinite(sim.altitude) ? sim.altitude : 0;
  const speed = sim && Number.isFinite(sim.speed) ? sim.speed : 0;

  const remaining = mode === "demo"
    ? `${Math.max(0, 42.6 - distance).toFixed(1)} km`
    : running
      ? "—"
      : "No route";

  const gradient = `${Math.abs(speed * 0.01).toFixed(1)}%`;
  const gain = `${Math.max(0, Math.round(altitude * 0.12))} m`;
  const loss = `${Math.max(0, Math.round(altitude * 0.08))} m`;

  return {
    remaining,
    gradient,
    gain,
    loss,
    road: running ? "Route preview" : "Standby",
  };
};

// Confidence level styling
const confidenceLevelClass = (level) => {
  const classes = {
    high: "confidence-high",
    medium: "confidence-medium",
    low: "confidence-low",
  };
  return classes[level] || "confidence-high";
};

// -------------------------------------------------------------------------
// Top bar with live/demo mode and telemetry status
// -------------------------------------------------------------------------

function TopBar({ mode, telemetry, apiConnected }) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-title">EV ENERGY INTELLIGENCE</span>
        <span className="brand-sub">Route-aware energy & range estimate</span>
      </div>
      <div className="topbar-right">
        {mode === "demo" && (
          <span className="mode-badge" id="mode-badge">
            SIMULATOR — DEVELOPMENT ONLY
          </span>
        )}
        {mode === "live" && (
          <span className="live-badge" id="live-badge">
            <span className="dot dot-live"></span>LIVE
          </span>
        )}
        {mode === "live" && telemetry.status !== "ok" && (
          <span className="live-badge warning-badge" id="live-badge">
            {qualityToLabel(telemetry.quality)}
          </span>
        )}
        <span className="clock" id="clock">{nowClock()}</span>
      </div>
    </header>
  );
}

// -------------------------------------------------------------------------
// Primary card: speed, SOC, range with confidence awareness
// -------------------------------------------------------------------------

function Primary({ sim, predictionReady, lastPred, telemetry, confidence }) {
  const range =
    predictionReady && lastPred
      ? Math.round(lastPred.expected_range_km)
      : null;
  const borderColor =
    lastPred && lastPred.predicted_energy_kwh_per_km
      ? "#5f6"
      : "#666";

  // Determine speed display with quality awareness
  const speedValue = sim ? sim.speed : null;
  const speedQuality = telemetry.quality;

  return (
    <section className="primary" aria-label="Primary telemetry">
      <div className="primary-card" id="speed-card">
        <span className="primary-label">SPEED</span>
        <span className="primary-value">
          {speedValue !== null
            ? `${Math.round(speedValue)} km/h`
            : telemetry.status === "offline"
              ? "—"
              : "No speed"}
        </span>
        {/* Speed quality indicator */}
        {speedQuality !== "VALID" && (
          <span className="quality-indicator">
            {qualityToLabel(speedQuality)}
          </span>
        )}
      </div>
      <div className="primary-card" id="soc-card" style={{ borderLeftColor: borderColor }}>
        <span className="primary-label">BATTERY</span>
        <span className="primary-value">
          {lastPred && lastPred.usable_energy_kwh !== undefined
            ? `${Number(lastPred.usable_energy_kwh).toFixed(1)} kWh usable`
            : sim && sim.soc !== undefined
              ? `${Math.round(sim.soc)}%`
              : "—"}
        </span>
      </div>
      <div className="primary-card" id="range-card">
        <span className="primary-label">RANGE</span>
        <span className="primary-value">
          {predictionReady && lastPred
            ? `${Math.round(lastPred.expected_range_km)} km (${lastPred.confidence?.level || "?"} confidence)`
            : telemetry.status === "offline"
              ? "TELEMETRY OFFLINE"
              : "No prediction"}
        </span>
      </div>
      {/* Confidence bar */}
      {predictionReady && lastPred && confidence.score > 0 && (
        <div className="confidence-bar">
          <span className={`confidence-label ${confidenceLevelClass(confidence.level)}`}
            >{confidence.level.toUpperCase()} ({(confidence.score * 100).toFixed(1)}%)</span
          >
          <div
            className="confidence-progress"
            style={{ width: `${confidence.score * 100}%` }}
            aria-label={`Confidence ${confidence.level} ${Math.round(confidence.score * 100)}%`}
          ></div>
        </div>
      )}
    </section>
  );
}

// -------------------------------------------------------------------------
// Strip: telemetry values summary
// -------------------------------------------------------------------------

function Strip({ sim, predictionReady, lastPred, telemetry }) {
  return (
    <section className="strip" aria-label="Telemetry strip">
      <div className="strip-item">
        <span className="strip-label">SPEED</span>
        <span className="strip-value" id="s-speed">
          {sim && sim.speed !== undefined
            ? `${Math.round(sim.speed)} km/h`
            : telemetry.status === "offline"
              ? "—"
              : "No data"}</span>
      </div>
      <div className="strip-item">
        <span className="strip-label">SOC</span>
        <span className="strip-value" id="s-soc">
          {sim && sim.soc !== undefined
            ? `${Math.round(sim.soc)} %`
            : lastPred && lastPred.usable_energy_kwh !== undefined
              ? `~${Math.round(lastPred.usable_energy_kwh / 58 * 100)}%`
              : "—"}</span>
      </div>
      <div className="strip-item">
        <span className="strip-label">ENERGY</span>
        <span className="strip-value" id="s-energy">
          {predictionReady && lastPred
            ? lastPred.predicted_energy_kwh_per_km.toFixed(3) + " kWh/km"
            : "--"}
        </span>
      </div>
      <div className="strip-item">
        <span className="strip-label">ALTITUDE</span>
        <span className="strip-value" id="s-alt">
          {sim && sim.altitude !== undefined ? `${Math.round(sim.altitude)} m` : "—"}</span>
      </div>
      <div className="strip-item">
        <span className="strip-label">TEMP</span>
        <span className="strip-value" id="s-temp">
          {sim && sim.temp !== undefined ? `${Math.round(sim.temp)}°C` : "—"}</span>
      </div>
      {/* Telemetry quality strip */}
      <div className="strip-item quality-strip">
        <span className="strip-label">TELEMETRY</span>
        <span className="strip-value" id="t-quality">
          {qualityToLabel(telemetry.quality)} ({telemetry.status})</span>
      </div>
    </section>
  );
}

// -------------------------------------------------------------------------
// Controls: connection status and mode controls
// -------------------------------------------------------------------------

function Controls({
  mode,
  running,
  pollMs,
  apiConnected,
  predictionReady,
  lastError,
  onStart,
  onPause,
  onReset,
  onChangePollMs,
}) {
  const predText = lastError
    ? "Prediction error"
    : predictionReady
      ? "Prediction Ready"
      : "No prediction";
  const predDot = lastError ? "warn" : predictionReady ? "ok" : "off";

  return (
    <section className="controls" aria-label="Connection status and controls">
      <div className="status">
        <span className="status-item">
          <span className={`dot ${apiConnected ? "ok" : "err"}`} id="d-api"></span>
          <span id="t-api">{apiConnected ? "API Connected" : "API Disconnected"}</span>
        </span>
        <span className="status-item">
          <span className={`dot ${running ? "ok" : "off"}`} id="d-mode"></span>
          <span id="t-mode">
            {mode === "demo"
              ? running
                ? "Demo Mode"
                : "Demo Paused"
              : running
                ? "Live"
                : "Live Paused"}
          </span>
        </span>
        <span className="status-item">
          <span className={`dot ${predDot}`} id="d-pred"></span>
          <span id="t-pred">{predText}</span>
        </span>
      </div>
      <div className="demo-controls">
        <label htmlFor="interval">Polling</label>
        <select
          id="interval"
          aria-label="Polling interval"
          value={pollMs}
          onChange={(e) => onChangePollMs(parseInt(e.target.value, 10))}
        >
          <option value={1000}>1 s</option>
          <option value={2000}>2 s</option>
          <option value={3000}>3 s</option>
          <option value={5000}>5 s</option>
        </select>
        <button id="btn-start" type="button" disabled={running} onClick={onStart}>
          Start
        </button>
        <button id="btn-pause" type="button" disabled={!running} onClick={onPause}>
          Pause
        </button>
        <button id="btn-reset" type="button" onClick={onReset}>
          Reset
        </button>
      </div>
      {/* Live telemetry status */}
      {mode === "live" && (
        <div className="live-telemetry-status">
          <span>Telemetry: {telemetry.status === "ok" ? "LIVE" : telemetry.status}</span>
          <span className="quality-badge">{qualityToLabel(telemetry.quality)}</span>
        </div>
      )}
    </section>
  );
}

// -------------------------------------------------------------------------
// Battery panel: expanded battery info
// -------------------------------------------------------------------------

function BatteryPanel({ sim, telemetry, sensorQuality }) {
  const current =
    sim && sim.motorPower > 0
      ? fmt((sim.motorPower * 1000) / sim.battVolt, 0, "A")
      : "—";
  const power = sim && sim.motorPower + sim.auxPower > 0 ? fmt(sim.motorPower + sim.auxPower, 1, "kW") : "—";

  return (
    <article className="panel" aria-label="Battery">
      <h2 className="panel-title">BATTERY</h2>
      <dl className="kv">
        <div>
          <dt>SOC</dt>
          <dd id="b-soc">
            {sim && sim.soc !== undefined ? `${Math.round(sim.soc)}%` : "—"}
            {telemetry.status !== "ok" && (
              <span className="quality-note">
                {qualityToLabel(telemetry.quality)}
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt>Capacity</dt>
          <dd id="b-cap">58 kWh</dd>
        </div>
        <div>
          <dt>Voltage</dt>
          <dd id="b-volt">{fmt(sim?.battVolt, 0, "V")}</dd>
        </div>
        <div>
          <dt>Temperature</dt>
          <dd id="b-temp">{fmt(sim?.battTemp, 1, "°C")}</dd>
        </div>
        <div>
          <dt>Current</dt>
          <dd id="b-curr">{current}</dd>
        </div>
        <div>
          <dt>Power</dt>
          <dd id="b-power">{power}</dd>
        </div>
      </dl>
      {/* Sensor quality note */}
      {sensorQuality.overall_rating !== "unknown" && (
        <div className="quality-note">
          Sensor quality: {sensorQuality.overall_rating}
        </div>
      )}
    </article>
  );
}

// -------------------------------------------------------------------------
// Energy panel: consumption and range
// -------------------------------------------------------------------------

function EnergyPanel({ predictionReady, lastPred, history, confidence }) {
  return (
    <article className="panel" aria-label="Energy">
      <h2 className="panel-title">ENERGY</h2>
      <div className="energy-now">
        <span className="energy-value" id="e-now">
          {predictionReady && lastPred
            ? lastPred.predicted_energy_kwh_per_km.toFixed(3)
            : "--"}
        </span>
        <span className="energy-unit">kWh/km</span>
      </div>
      <EnergyChart history={history} />
      <div className="chart-legend">
        Predicted consumption, last {history.length} values
      </div>
      {/* Confidence info below chart */}
      {predictionReady && lastPred && confidence.score > 0 && (
        <div className="energy-confidence">
          <span>Confidence: {confidence.level.toUpperCase()} {(confidence.score * 100).toFixed(0)}%</span>
          <span>{(confidence.components.missing_contribution * 100).toFixed(0)}% missing features</span>
          <span>{(confidence.components.route_contribution * 100).toFixed(0)}% route status</span>
        </div>
      )}
    </article>
  );
}

// -------------------------------------------------------------------------
// Range panel: conservative/expected/optimistic with confidence
// -------------------------------------------------------------------------

function RangePanel({ lastPred, confidence }) {
  const c = lastPred ? lastPred.conservative_range_km : null;
  const e = lastPred ? lastPred.expected_range_km : null;
  const o = lastPred ? lastPred.optimistic_range_km : null;
  const pct =
    e !== null && e > 0
      ? Math.min(100, Math.max(3, (e / (o !== null ? o : e * 1.2)) * 100))
      : 0;
  return (
    <article className="panel" aria-label="Range">
      <h2 className="panel-title">RANGE</h2>
      <div className="range-values">
        <div className="range-val">
          <span className="range-label">CONSERVATIVE</span>
          <span className="range-num" id="r-conservative">
            {c !== null ? Math.round(c) + " km" : "--"}
          </span>
        </div>
        <div className="range-val range-emph">
          <span className="range-label">EXPECTED</span>
          <span className="range-num" id="r-expected">
            {e !== null ? Math.round(e) + " km" : "--"}
          </span>
        </div>
        <div className="range-val">
          <span className="range-label">OPTIMISTIC</span>
          <span className="range-num" id="r-optimistic">
            {o !== null ? Math.round(o) + " km" : "--"}
          </span>
        </div>
      </div>
      <div className="range-bar" role="img" aria-label="Range indicator">
        <div className="range-track" id="range-track" style={{ width: pct + "%" }}></div>
      </div>
      {/* Confidence note */}
      {lastPred && confidence.score > 0 && (
        <div className="range-confidence-note">
          Range based on {confidence.level} confidence ({(confidence.score * 100).toFixed(0)}%)
        </div>
      )}
    </article>
  );
}

// -------------------------------------------------------------------------
// Route panel: route status with terrain availability
// -------------------------------------------------------------------------

function RoutePanel({ sim, mode, running, routeStatus }) {
  const r = routeStatus.status !== "unavailable"
    ? {
        remaining: "—",
        gradient: "—",
        gain: "—",
        loss: "—",
        road: routeStatusLabel(routeStatus.status),
      }
    : routeStats(sim, mode, running);

  return (
    <article className="panel" aria-label="Route">
      <h2 className="panel-title">ROUTE</h2>
      <dl className="kv">
        <div>
          <dt>Route status</dt>
          <dd id="rt-remaining">{r.remaining}</dd>
        </div>
        <div>
          <dt>Gradient</dt>
          <dd id="rt-gradient">{r.gradient}</dd>
        </div>
        <div>
          <dt>Elevation gain</dt>
          <dd id="rt-gain">{r.gain}</dd>
        </div>
        <div>
          <dt>Elevation loss</dt>
          <dd id="rt-loss">{r.loss}</dd>
        </div>
        <div>
          <dt>Road condition</dt>
          <dd id="rt-road">{r.road}</dd>
        </div>
      </dl>
      {/* Route availability indicator */}
      {routeStatus.available !== undefined && (
        <div className="route-availability">
          <span>Availability: {routeStatusLabel(routeStatus.status)}</span>
          {routeStatus.terrain_features_available !== undefined && (
            <span>Terrain features: {routeStatus.terrain_features_available ? "available" : "unavailable"}</span>
          )}
        </div>
      )}
    </article>
  );
}

// -------------------------------------------------------------------------
// Conditions panel: driving conditions
// -------------------------------------------------------------------------

function ConditionsPanel({ sim, mode, telemetry }) {
  // Determine gradient from terrain or use speed/temp as proxies
  const grad = telemetry.quality === "VALID" && sim ? Math.abs(sim.speed * 0.01) : 0;
  const condition = grad > 1.5 ? "Uphill" : grad < -1.5 ? "Downhill" : "Flat";
  const road =
    mode === "demo"
      ? Math.abs(grad) < 2
        ? "Flat road"
        : Math.abs(grad) < 5
          ? "Hilly road"
          : "Steep terrain"
      : telemetry.status === "ok"
        ? "--"
        : "Telemetry unavailable";

  return (
    <article className="panel" aria-label="Driving conditions">
      <h2 className="panel-title">DRIVING CONDITIONS</h2>
      <dl className="kv">
        <div>
          <dt>Speed</dt>
          <dd id="c-speed">
            {sim && sim.speed !== undefined ? `${Math.round(sim.speed)} km/h` : "—"}</dd>
        </div>
        <div>
          <dt>Altitude</dt>
          <dd id="c-alt">
            {sim && sim.altitude !== undefined ? `${Math.round(sim.altitude)} m` : "—"}</dd>
        </div>
        <div>
          <dt>Ambient temp</dt>
          <dd id="c-temp">
            {sim && sim.temp !== undefined ? `${Math.round(sim.temp)}°C` : "—"}</dd>
        </div>
        <div>
          <dt>Condition</dt>
          <dd id="c-condition">{condition}</dd>
        </div>
        <div>
          <dt>Road type</dt>
          <dd id="c-road">{road}</dd>
        </div>
      </dl>
      {/* Telemetry quality indicator */}
      <div className="condition-quality">
        <span>Telemetry: {qualityToLabel(telemetry.quality)}</span>
      </div>
    </article>
  );
}

// -------------------------------------------------------------------------
// Footer: system status with mode info
// -------------------------------------------------------------------------

function Footer({ predictionReady, lastError, mode, telemetry, confidence }) {
  const status =
    lastError
      ? "Error"
      : predictionReady
        ? "Ready"
        : telemetry.status === "offline"
          ? "Telemetry offline"
          : "Ready";

  return (
    <footer className="footer">
      <span>EV Energy Intelligence & Dynamic Range Prediction</span>
      <span className="footer-sep">·</span>
      <span>Model: ExtraTrees Route-Aware</span>
      <span className="footer-sep">·</span>
      <span>Status: {status}</span>
      {mode === "live" && confidence.score > 0 && (
        <>
          <span className="footer-sep">·</span>
          <span>
            Confidence:
            <span className={confidenceLevelClass(confidence.level)}>
              {confidence.level} {(confidence.score * 100).toFixed(0)}%
            </span>
          </span>
        </>
      )}
      {mode === "demo" && (
        <>
          <span className="footer-sep">·</span>
          <span>{/* SIMULATOR — DEVELOPMENT ONLY */}</span>
        </>
      )}
    </footer>
  );
}

// -------------------------------------------------------------------------
// Main App component
// -------------------------------------------------------------------------

export default function App() {
  const dash = useDashboard();

  return (
    <>
      <TopBar mode={dash.mode} apiConnected={dash.apiConnected} telemetry={dash.telemetry} />
      <main className="layout">
        <Primary
          sim={dash.sim}
          predictionReady={dash.predictionReady}
          lastPred={dash.lastPred}
          telemetry={dash.telemetry}
          confidence={dash.confidence}
        />
        <Strip sim={dash.sim} predictionReady={dash.predictionReady} lastPred={dash.lastPred} telemetry={dash.telemetry} />
        <Controls
          mode={dash.mode}
          running={dash.running}
          pollMs={dash.pollMs}
          apiConnected={dash.apiConnected}
          predictionReady={dash.predictionReady}
          lastError={dash.lastError}
          onStart={dash.start}
          onPause={dash.pause}
          onReset={dash.reset}
          onChangePollMs={dash.changePollMs}
        />
        <section className="panels">
          <BatteryPanel sim={dash.sim} telemetry={dash.telemetry} sensorQuality={dash.sensorQuality} />
          <EnergyPanel
            predictionReady={dash.predictionReady}
            lastPred={dash.lastPred}
            history={dash.history}
            confidence={dash.confidence}
          />
          <RangePanel lastPred={dash.lastPred} confidence={dash.confidence} />
          <RoutePanel sim={dash.sim} mode={dash.mode} running={dash.running} routeStatus={dash.routeStatus} />
          <ConditionsPanel sim={dash.sim} mode={dash.mode} telemetry={dash.telemetry} />
        </section>
      </main>
      <Footer
        predictionReady={dash.predictionReady}
        lastError={dash.lastError}
        mode={dash.mode}
        telemetry={dash.telemetry}
        confidence={dash.confidence}
      />
    </>
  );
}
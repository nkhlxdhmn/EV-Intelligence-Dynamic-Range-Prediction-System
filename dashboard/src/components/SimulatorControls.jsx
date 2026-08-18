import { fmt, drivingStyleLabel, routeProfileLabel, trafficLabel } from "./shared";

const SPEEDS = [1, 2, 4, 8];
const POLLS = [1000, 2000, 3000, 5000];

// Simulator test bench: scenario identity + controls. Everything here drives
// the real backend simulator — nothing randomizes UI numbers.
export default function SimulatorControls({
  running,
  simScenario,
  scenarioInfo,
  seed,
  simSpeed,
  pollMs,
  lastError,
  onStart,
  onPause,
  onReset,
  onRandomize,
  onChangeSimSpeed,
  onChangePollMs,
  onChangeSeed,
}) {
  const info = scenarioInfo || {};
  const meta = [
    { label: "DRIVING STYLE", value: drivingStyleLabel(info.driving_style) },
    { label: "TRAFFIC", value: trafficLabel(info.traffic_level) },
    { label: "ROUTE", value: routeProfileLabel(info.route_profile) },
    {
      label: "AMBIENT",
      value: Number.isFinite(info.ambient_temperature_c) ? `${info.ambient_temperature_c} °C` : "—",
    },
    {
      label: "INITIAL SOC",
      value: Number.isFinite(info.initial_soc_pct) ? `${info.initial_soc_pct} %` : "—",
    },
    {
      label: "VEHICLE MASS",
      value: Number.isFinite(info.vehicle_mass_kg) ? `${Math.round(info.vehicle_mass_kg)} kg` : "—",
    },
    {
      label: "ROUTE LENGTH",
      value: info.route && Number.isFinite(info.route.length_km) ? `${info.route.length_km} km` : "—",
    },
    {
      label: "SEED",
      value: Number.isFinite(info.seed) ? info.seed : seed,
    },
  ];

  return (
    <section className="panel panel-sim" aria-label="Simulator controls">
      <div className="section-head">
        <span className="section-no">09</span>
        <span className="section-title">SIMULATOR</span>
        <span className="section-hint">{simScenario || "no scenario"}</span>
      </div>
      <div className="sim-meta">
        {meta.map((m) => (
          <div className="sim-meta-item" key={m.label}>
            <span className="sim-meta-label">{m.label}</span>
            <span className="sim-meta-value">{m.value}</span>
          </div>
        ))}
      </div>
      {lastError && <div className="sim-error">{lastError}</div>}
      <div className="sim-buttons">
        <button type="button" className="sim-btn sim-btn-solid" disabled={running} onClick={onStart}>
          START
        </button>
        <button type="button" className="sim-btn" disabled={!running} onClick={onPause}>
          PAUSE
        </button>
        <button type="button" className="sim-btn" onClick={onReset}>
          RESET
        </button>
        <button type="button" className="sim-btn sim-btn-random" onClick={onRandomize}>
          RANDOMIZE
        </button>
      </div>
      <div className="sim-control-row">
        <span className="sim-control-label">SPEED</span>
        <div className="seg">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              className={`seg-opt ${simSpeed === s ? "seg-opt-active" : ""}`}
              onClick={() => onChangeSimSpeed(s)}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>
      <div className="sim-control-row">
        <span className="sim-control-label">POLL</span>
        <div className="seg">
          {POLLS.map((p) => (
            <button
              key={p}
              type="button"
              className={`seg-opt ${pollMs === p ? "seg-opt-active" : ""}`}
              onClick={() => onChangePollMs(p)}
            >
              {p / 1000}s
            </button>
          ))}
        </div>
      </div>
      <div className="sim-control-row">
        <span className="sim-control-label">SEED</span>
        <input
          type="number"
          min="0"
          aria-label="Simulator seed"
          value={seed}
          onChange={(e) => onChangeSeed(e.target.value)}
          className="seed-input"
        />
      </div>
    </section>
  );
}
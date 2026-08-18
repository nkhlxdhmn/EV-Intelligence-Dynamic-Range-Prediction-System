import { fmt } from "./shared";

export function SpeedMetric({ speed, phase, telemetryOk }) {
  const value = Number.isFinite(speed) ? Math.round(speed) : null;
  return (
    <div className="hero-metric">
      <div className="metric-label">SPEED</div>
      <div className="metric-value">
        {value !== null ? (
          <>
            {value}
            <span className="metric-unit">km/h</span>
          </>
        ) : (
          <span className="metric-empty">—</span>
        )}
      </div>
      <div className="metric-foot">
        {phase ? <span className="metric-tag">{phase}</span> : <span className="metric-note">{telemetryOk ? "no signal" : "unavailable"}</span>}
      </div>
    </div>
  );
}

export function SOCMetric({ soc, usableEnergy }) {
  const value = Number.isFinite(soc) ? Math.round(soc) : null;
  return (
    <div className="hero-metric">
      <div className="metric-label">STATE OF CHARGE</div>
      <div className="metric-value">
        {value !== null ? (
          <>
            {value}
            <span className="metric-unit">%</span>
          </>
        ) : (
          <span className="metric-empty">—</span>
        )}
      </div>
      <div className="metric-foot">
        <span className="metric-note">
          {Number.isFinite(usableEnergy) ? fmt(usableEnergy, 1, "kWh usable") : "no capacity signal"}
        </span>
      </div>
    </div>
  );
}

export function RangeMetric({ expected, conservative, optimistic, ready }) {
  const value = Number.isFinite(expected) ? Math.round(expected) : null;
  return (
    <div className="hero-metric hero-range">
      <div className="metric-label">ESTIMATED RANGE</div>
      <div className="metric-value metric-value-lg">
        {value !== null ? (
          <>
            {value}
            <span className="metric-unit">km</span>
          </>
        ) : (
          <span className="metric-empty">—</span>
        )}
      </div>
      <div className="metric-foot metric-bounds">
        {ready && value !== null ? (
          <>
            <span className="bound">
              <span className="bound-label">CONSERVATIVE</span>
              <span className="bound-value">{Number.isFinite(conservative) ? Math.round(conservative) : "—"}</span>
            </span>
            <span className="bound">
              <span className="bound-label">EXPECTED</span>
              <span className="bound-value">{Number.isFinite(expected) ? Math.round(expected) : "—"}</span>
            </span>
            <span className="bound">
              <span className="bound-label">OPTIMISTIC</span>
              <span className="bound-value">{Number.isFinite(optimistic) ? Math.round(optimistic) : "—"}</span>
            </span>
          </>
        ) : (
          <span className="metric-note">waiting for prediction</span>
        )}
      </div>
    </div>
  );
}

export default function HeroMetrics({ values, predictionReady, lastPred, telemetry, phase }) {
  const range = predictionReady && lastPred ? lastPred : null;
  const speed = values.speed_kmh;
  const soc = values.soc_pct;
  const usable = range ? range.usable_energy_kwh : null;
  return (
    <section className="hero" aria-label="Primary telemetry">
      <div className="section-head">
        <span className="section-no">01</span>
        <span className="section-title">PRIMARY TELEMETRY</span>
      </div>
      <div className="hero-grid">
        <SpeedMetric speed={speed} phase={phase} telemetryOk={telemetry.status === "ok"} />
        <SOCMetric soc={soc} usableEnergy={usable} />
        <RangeMetric
          expected={range ? range.expected_range_km : null}
          conservative={range ? range.conservative_range_km : null}
          optimistic={range ? range.optimistic_range_km : null}
          ready={predictionReady && !!range}
        />
      </div>
    </section>
  );
}
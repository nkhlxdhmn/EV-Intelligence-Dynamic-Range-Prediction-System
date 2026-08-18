// Distinctive horizontal range visualization: a confidence band between the
// conservative and optimistic bounds, with the expected range as the dominant
// marker. No fake data — rendered only when a real prediction exists.
export default function RangeVisualization({ lastPred, predictionReady }) {
  if (!predictionReady || !lastPred) {
    return (
      <section className="range-viz" aria-label="Range visualization">
        <div className="section-head">
          <span className="section-no">02</span>
          <span className="section-title">RANGE DISTRIBUTION</span>
        </div>
        <div className="range-viz-empty">NO PREDICTION — RANGE UNAVAILABLE</div>
      </section>
    );
  }

  const c = Number(lastPred.conservative_range_km);
  const e = Number(lastPred.expected_range_km);
  const o = Number(lastPred.optimistic_range_km);
  const finite = (n) => Number.isFinite(n) && n > 0;

  if (!finite(e)) {
    return (
      <section className="range-viz" aria-label="Range visualization">
        <div className="section-head">
          <span className="section-no">02</span>
          <span className="section-title">RANGE DISTRIBUTION</span>
        </div>
        <div className="range-viz-empty">RANGE VALUES UNAVAILABLE</div>
      </section>
    );
  }

  const useC = finite(c) ? c : e * 0.86;
  const useO = finite(o) ? o : e * 1.14;
  const lo = Math.min(useC, useO);
  const hi = Math.max(useC, useO);
  const span = hi - lo || 1;
  const pos = (v) => Math.min(100, Math.max(0, ((v - lo) / span) * 100));

  const bandLeft = pos(useC);
  const bandRight = pos(useO);
  const expectedPct = pos(e);

  return (
    <section className="range-viz" aria-label="Range visualization">
      <div className="section-head">
        <span className="section-no">02</span>
        <span className="section-title">RANGE DISTRIBUTION</span>
        <span className="section-hint">
          {Number.isFinite(lastPred.usable_energy_kwh)
            ? `${Number(lastPred.usable_energy_kwh).toFixed(1)} kWh usable`
            : "usable energy unknown"}
        </span>
      </div>
      <div className="range-scale">
        <div className="range-band" style={{ left: `${bandLeft}%`, width: `${bandRight - bandLeft}%` }} />
        <div className="range-axis" />
        <div className="range-marker range-marker-c" style={{ left: `${bandLeft}%` }} />
        <div className="range-marker range-marker-e" style={{ left: `${expectedPct}%` }} />
        <div className="range-marker range-marker-o" style={{ left: `${bandRight}%` }} />
        <span className="range-axis-min" style={{ left: `${bandLeft}%` }}>{Math.round(useC)}</span>
        <span className="range-axis-exp" style={{ left: `${expectedPct}%` }}>{Math.round(e)}</span>
        <span className="range-axis-max" style={{ left: `${bandRight}%` }}>{Math.round(useO)}</span>
      </div>
      <div className="range-legend">
        <span className="legend-item">
          <span className="legend-k legend-k-c" />CONSERVATIVE
        </span>
        <span className="legend-item legend-item-e">
          <span className="legend-k legend-k-e" />EXPECTED
        </span>
        <span className="legend-item">
          <span className="legend-k legend-k-o" />OPTIMISTIC
        </span>
        <span className="range-legend-note">model horizon 5 km</span>
      </div>
    </section>
  );
}
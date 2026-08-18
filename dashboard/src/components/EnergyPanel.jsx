import EnergyChart from "../EnergyChart";
import { fmt } from "./shared";

// Energy panel: predicted consumption + large history chart.
export default function EnergyPanel({ predictionReady, lastPred, history, modelInfo }) {
  const current = predictionReady && lastPred ? lastPred.predicted_energy_kwh_per_km : null;
  const horizon = modelInfo && modelInfo.horizon_km ? modelInfo.horizon_km : 5;

  return (
    <section className="panel panel-energy" aria-label="Energy consumption">
      <div className="section-head">
        <span className="section-no">03</span>
        <span className="section-title">ENERGY CONSUMPTION</span>
        <span className="section-hint">avg over next {horizon} km</span>
      </div>
      <div className="energy-now">
        <span className="energy-value" id="e-now">
          {current !== null ? fmt(current, 3) : "—"}
        </span>
        <span className="energy-unit">kWh/km</span>
      </div>
      <EnergyChart history={history} horizonKm={horizon} />
    </section>
  );
}
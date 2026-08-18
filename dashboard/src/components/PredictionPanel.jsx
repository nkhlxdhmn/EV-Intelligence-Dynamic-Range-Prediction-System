import { fmt, reliabilityLevelText, statusToText } from "./shared";

// Technical model / prediction status panel.
export default function PredictionPanel({ modelInfo, predictionReady, lastPred }) {
  const conf = lastPred && lastPred.confidence ? lastPred.confidence : null;
  const reliability = conf ? reliabilityLevelText(conf.level) : "—";
  const relCls = conf ? `rel-${conf.level}` : "rel-high";
  const ood = lastPred && lastPred.ood ? lastPred.ood : null;
  const oodLabel = !ood
    ? "—"
    : ood.is_ood
      ? ood.severity.toUpperCase()
      : "IN DISTRIBUTION";

  const rows = [
    { label: "MODEL", value: modelInfo ? modelInfo.model : "—" },
    { label: "VERSION", value: modelInfo ? modelInfo.model_version : "—" },
    { label: "DATASET", value: modelInfo ? modelInfo.dataset : "—" },
    {
      label: "PREDICTION",
      value: predictionReady && lastPred && Number.isFinite(lastPred.predicted_energy_kwh_per_km)
        ? `${fmt(lastPred.predicted_energy_kwh_per_km, 3)} kWh/km`
        : "—",
    },
    {
      label: "HORIZON",
      value: modelInfo && modelInfo.horizon_km ? `${modelInfo.horizon_km} km` : "—",
    },
    {
      label: "ROUTE-AWARE",
      value: modelInfo && modelInfo.route_aware ? "YES" : "NO",
    },
    {
      label: "STATUS",
      value: predictionReady && lastPred ? statusToText(lastPred.status) : "STANDBY",
    },
    {
      label: "OOD",
      value: oodLabel,
    },
  ];

  return (
    <section className="panel panel-prediction" aria-label="Prediction status">
      <div className="section-head">
        <span className="section-no">07</span>
        <span className="section-title">MODEL / PREDICTION</span>
      </div>
      <dl className="kv prediction-kv">
        {rows.map((r) => (
          <div key={r.label}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      <div className="reliability-line">
        <span className="reliability-label">RELIABILITY</span>
        <span className={`reliability-value ${relCls}`}>{reliability}</span>
      </div>
    </section>
  );
}
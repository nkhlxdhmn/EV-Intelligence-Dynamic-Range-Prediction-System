import { fmt } from "./shared";

const SEGMENTS = 24;

// Minimal technical battery indicator: segmented SOC bar, electrical values,
// and a regeneration readout (accent color only while regen is active).
export default function BatteryPanel({ values }) {
  const soc = values.soc_pct;
  const filled = Number.isFinite(soc) ? Math.max(0, Math.min(1, soc / 100)) : 0;
  const filledSegs = Math.round(filled * SEGMENTS);

  const regen = values.regen_power_kw;
  const regenActive = Number.isFinite(regen) && regen > 0.05;

  const rows = [
    { label: "VOLTAGE", value: fmt(values.battery_voltage_v, 1, "V") },
    { label: "CURRENT", value: fmt(values.battery_current_a, 1, "A") },
    { label: "BATTERY POWER", value: fmt(values.battery_power_kw, 1, "kW") },
    { label: "TEMPERATURE", value: fmt(values.battery_temperature_c, 1, "°C") },
    { label: "CAPACITY", value: fmt(values.battery_capacity_kwh, 1, "kWh") },
  ];

  return (
    <section className="panel panel-battery" aria-label="Battery">
      <div className="section-head">
        <span className="section-no">04</span>
        <span className="section-title">BATTERY</span>
      </div>
      <div className="battery-soc-row">
        <span className="battery-soc-label">SOC</span>
        <span className="battery-soc-value">{Number.isFinite(soc) ? Math.round(soc) : "—"}%</span>
      </div>
      <div className="battery-segs" aria-label={`State of charge ${Number.isFinite(soc) ? Math.round(soc) : "unknown"} percent`}>
        {Array.from({ length: SEGMENTS }, (_, i) => (
          <span
            key={i}
            className={`battery-seg ${i < filledSegs ? "seg-on" : "seg-off"}`}
          />
        ))}
      </div>
      {regenActive ? (
        <div className="regen-active">
          <span className="regen-arrow">↘</span>
          <span>REGEN {fmt(regen, 1, "kW")}</span>
        </div>
      ) : (
        <div className="regen-idle">
          <span>REGEN</span>
          <span className="regen-idle-value">{Number.isFinite(regen) ? fmt(regen, 1, "kW") : "—"}</span>
        </div>
      )}
      <dl className="kv battery-kv">
        {rows.map((r) => (
          <div key={r.label}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
import { fmt, grp } from "./shared";

// Compact engineering telemetry table. Aligned, monospaced, diagnostic-panel
// style. Missing values stay "—"; nothing is synthesized.
export default function VehicleTelemetry({ values, accelerationMps2, phase }) {
  const rows = [
    { label: "SPEED", value: fmt(values.speed_kmh, 1, "km/h") },
    {
      label: "ACCELERATION",
      value: accelerationMps2 !== null ? `${accelerationMps2 >= 0 ? "+" : ""}${accelerationMps2.toFixed(2)} m/s²` : "—",
    },
    { label: "MOTOR RPM", value: grp(values.motor_rpm, 0) !== "—" ? `${grp(values.motor_rpm, 0)} rpm` : "—" },
    { label: "MOTOR TORQUE", value: fmt(values.motor_torque_nm, 0, "Nm") },
    { label: "MOTOR POWER", value: fmt(values.motor_power_kw, 1, "kW") },
    { label: "AUX POWER", value: fmt(values.aux_power_kw, 2, "kW") },
    { label: "BATTERY POWER", value: fmt(values.battery_power_kw, 1, "kW") },
    { label: "BATTERY TEMP", value: fmt(values.battery_temperature_c, 1, "°C") },
    { label: "AMBIENT TEMP", value: fmt(values.ambient_temperature_c, 1, "°C") },
    { label: "ALTITUDE", value: fmt(values.altitude_m, 0, "m") },
    { label: "GRADIENT", value: fmt(values.current_gradient_pct, 2, "%") },
    { label: "TRIP TIME", value: fmt(values.time_since_trip_start_min, 1, "min") },
  ];
  if (phase) rows.push({ label: "PHASE", value: phase });

  return (
    <section className="panel panel-telemetry" aria-label="Vehicle telemetry">
      <div className="section-head">
        <span className="section-no">06</span>
        <span className="section-title">VEHICLE TELEMETRY</span>
      </div>
      <dl className="kv telemetry-kv">
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
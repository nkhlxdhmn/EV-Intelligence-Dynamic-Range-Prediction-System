import { useEffect, useState } from "react";

// LIVE telemetry monitor. Only real connection state is shown — offline and
// stale states are surfaced honestly; nothing is fabricated.
export default function LiveControls({ telemetry, liveStatus, lastPredAt, running }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const now = Date.now();
  const telemAge = Number.isFinite(telemetry.age_ms) ? telemetry.age_ms : null;
  const telemAgeS = telemAge !== null ? (telemAge / 1000).toFixed(1) : null;
  const predAgeS = lastPredAt ? ((now - lastPredAt) / 1000).toFixed(1) : null;

  const connected = telemetry.status === "ok";
  const degraded = telemetry.status === "degraded";
  const stale = telemAgeS !== null && Number(telemAgeS) > 5;

  let state;
  if (connected && !stale) {
    state = { dot: "on", label: "CONNECTED", note: "Telemetry stream active" };
  } else if (degraded || stale) {
    state = { dot: "warn", label: "TELEMETRY STALE", note: `Last update ${telemAgeS ?? "—"} s ago` };
  } else {
    state = { dot: "off", label: "DISCONNECTED", note: "Waiting for vehicle telemetry" };
  }

  const provider = liveStatus.provider || telemetry.source || "none";

  const rows = [
    { label: "PROVIDER", value: provider.toUpperCase() },
    { label: "LAST TELEMETRY", value: telemAgeS !== null ? `${telemAgeS} s ago` : "—" },
    { label: "LAST PREDICTION", value: predAgeS !== null ? `${predAgeS} s ago` : "—" },
    { label: "PREDICTION READY", value: liveStatus.prediction_ready ? "YES" : "NO" },
  ];
  if (liveStatus.prediction_ready_reason) {
    rows.push({ label: "REASON", value: liveStatus.prediction_ready_reason.toUpperCase() });
  }
  if (liveStatus.mode) rows.push({ label: "MODE", value: liveStatus.mode });

  return (
    <section className="panel panel-live" aria-label="Live vehicle">
      <div className="section-head">
        <span className="section-no">09</span>
        <span className="section-title">LIVE VEHICLE</span>
      </div>
      <div className={`live-state live-state-${state.dot}`}>
        <span className={`status-dot dot-${state.dot}`} />
        <span className="live-state-label">{state.label}</span>
        <span className="live-state-note">{state.note}</span>
      </div>
      <dl className="kv live-kv">
        {rows.map((r) => (
          <div key={r.label}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      <div className="live-note">
        <span>{running ? "monitoring live telemetry" : "paused"}</span>
      </div>
    </section>
  );
}
import { qualityToLabel } from "./shared";

// DATA QUALITY: honest readiness indicators. Missing inputs are never hidden.
export default function DataQuality({ mode, simTelemetry, simRoute, telemetry, routeStatus, predictionReady, apiConnected, modelInfo, liveStatus }) {
  const isSim = mode === "demo";

  const telemetryState = isSim
    ? simTelemetry
      ? { state: "on", text: "GOOD" }
      : { state: "warn", text: "IDLE" }
    : telemetry.status === "ok"
      ? { state: "on", text: "GOOD" }
      : telemetry.status === "degraded"
        ? { state: "warn", text: "DEGRADED" }
        : { state: "off", text: "OFFLINE" };

  const terrainReady = isSim ? !!simRoute : routeStatus.available === true;
  const terrainState = terrainReady ? { state: "on", text: "READY" } : { state: "off", text: "UNAVAILABLE" };

  const featuresState = predictionReady ? { state: "on", text: "COMPLETE" } : { state: "warn", text: "STANDBY" };

  const modelState = apiConnected && modelInfo ? { state: "on", text: "READY" } : { state: "off", text: "OFFLINE" };

  const items = [
    { label: "TELEMETRY", ...telemetryState },
    { label: "TERRAIN", ...terrainState },
    { label: "FEATURES", ...featuresState },
    { label: "MODEL", ...modelState },
  ];

  const signalCount = isSim
    ? simTelemetry
      ? Object.keys(simTelemetry).length
      : 0
    : telemetry.signals.length;
  const liveSignals = liveStatus.available_signals || [];
  const required = liveStatus.required_signal_status || {};
  const reqKeys = Object.keys(required);

  return (
    <section className="panel panel-quality" aria-label="Data quality">
      <div className="section-head">
        <span className="section-no">08</span>
        <span className="section-title">DATA QUALITY</span>
      </div>
      <div className="quality-list">
        {items.map((it) => (
          <div className="quality-row" key={it.label}>
            <span className={`status-dot dot-${it.state}`} />
            <span className="quality-label">{it.label}</span>
            <span className="quality-text">{it.text}</span>
          </div>
        ))}
      </div>
      {!isSim && (
        <div className="quality-extra">
          <div className="quality-row">
            <span className="quality-label">SIGNALS</span>
            <span className="quality-text">
              {liveSignals.length ? `${liveSignals.length} available / ${signalCount} valid` : `${signalCount} read`}
            </span>
          </div>
          {reqKeys.length > 0 && (
            <div className="quality-required">
              {reqKeys.map((k) => (
                <div className="quality-row" key={k}>
                  <span className={`status-dot dot-${required[k] === "VALID" ? "on" : "warn"}`} />
                  <span className="quality-label">{k}</span>
                  <span className="quality-text">{required[k] === "VALID" ? "VALID" : required[k]}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {isSim && (
        <div className="quality-note">
          <span>simulated telemetry — not real vehicle data</span>
        </div>
      )}
      <div className="quality-foot">
        <span>quality label: {isSim ? "SIMULATOR" : qualityToLabel(telemetry.quality)}</span>
      </div>
    </section>
  );
}
// System status strip: API / MODEL / PREDICTION / ROUTE readiness dots.
// Small, technical, honest — never hides a missing input.
export default function SystemStatus({
  apiConnected,
  modelInfo,
  predictionReady,
  lastError,
  mode,
  routeAvailable,
  running,
}) {
  const predState = lastError ? "err" : predictionReady ? "on" : running ? "warn" : "off";
  const routeState = routeAvailable ? "on" : mode === "demo" ? "warn" : "off";

  const items = [
    { label: "API", state: apiConnected ? "on" : "err", text: apiConnected ? "CONNECTED" : "OFFLINE" },
    { label: "MODEL", state: modelInfo ? "on" : "warn", text: modelInfo ? "LOADED" : "UNKNOWN" },
    { label: "PREDICTION", state: predState, text: lastError ? "ERROR" : predictionReady ? "READY" : running ? "RUNNING" : "STANDBY" },
    { label: "ROUTE", state: routeState, text: routeAvailable ? "READY" : "UNAVAILABLE" },
  ];

  return (
    <div className="system-status" aria-label="System status">
      {items.map((it) => (
        <div className="sys-item" key={it.label}>
          <span className={`status-dot dot-${it.state}`} />
          <span className="sys-label">{it.label}</span>
          <span className="sys-text">{it.text}</span>
        </div>
      ))}
    </div>
  );
}
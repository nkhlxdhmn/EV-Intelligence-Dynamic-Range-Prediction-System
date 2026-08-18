import { nowClock } from "./shared";

// Header: brand + operating mode identity + clock.
// The mode is the single most obvious thing on screen.
export default function Header({ mode, simScenario, telemetry, running }) {
  const age =
    telemetry && Number.isFinite(telemetry.age_ms)
      ? (telemetry.age_ms / 1000).toFixed(1)
      : null;
  const liveActive = mode === "live";

  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="header-title">EV INTELLIGENCE</div>
        <div className="header-sub">ENERGY &amp; RANGE PREDICTION</div>
      </div>
      <div className="header-meta">
        {liveActive ? (
          <div className="header-mode mode-live">
            <span className={`status-dot ${telemetry.status === "ok" ? "dot-on" : telemetry.status === "degraded" ? "dot-warn" : "dot-off"}`} />
            <span className="header-mode-label">LIVE</span>
            <span className="header-mode-sub">
              {telemetry.status === "ok"
                ? `Telemetry ${age !== null ? age + "s ago" : "active"}`
                : telemetry.status === "degraded"
                  ? "Telemetry degraded"
                  : "No telemetry source"}
            </span>
          </div>
        ) : (
          <div className="header-mode mode-sim">
            <span className="status-dot dot-sim" />
            <span className="header-mode-label">SIMULATOR</span>
            <span className="header-mode-sub">
              {running ? `Scenario ${simScenario || "—"}` : "Standby"}
            </span>
          </div>
        )}
        <span className="header-clock">{nowClock("utc")}</span>
      </div>
    </header>
  );
}

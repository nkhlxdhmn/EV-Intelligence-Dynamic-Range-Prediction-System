import { statusToText, reliabilityLevelText } from "./shared";

// Thin engineering footer.
export default function Footer({ mode, apiConnected, predictionReady, lastError, reliability, telemetry, modelInfo }) {
  const status = lastError
    ? "ERROR"
    : predictionReady
      ? "READY"
      : telemetry.status === "offline" && mode === "live"
        ? "TELEMETRY OFFLINE"
        : "STANDBY";

  return (
    <footer className="footer">
      <span>EV INTELLIGENCE · ENERGY &amp; RANGE PREDICTION</span>
      <span className="footer-sep">·</span>
      <span>MODEL {modelInfo && modelInfo.model ? modelInfo.model : "EXTRA TREES"}</span>
      <span className="footer-sep">·</span>
      <span>FEATURES {modelInfo && modelInfo.feature_count ? modelInfo.feature_count : 102}</span>
      <span className="footer-sep">·</span>
      <span>API {apiConnected ? "CONNECTED" : "DISCONNECTED"}</span>
      <span className="footer-sep">·</span>
      <span>STATUS {status}</span>
      {predictionReady && reliability && reliability.status && (
        <>
          <span className="footer-sep">·</span>
          <span>
            PREDICTION {statusToText(reliability.status)} · RELIABILITY {reliabilityLevelText(reliability.level)}
          </span>
        </>
      )}
      {mode === "demo" && (
        <>
          <span className="footer-sep">·</span>
          <span className="sim-footer-note">SIMULATOR DATA — NOT REAL TELEMETRY</span>
        </>
      )}
    </footer>
  );
}
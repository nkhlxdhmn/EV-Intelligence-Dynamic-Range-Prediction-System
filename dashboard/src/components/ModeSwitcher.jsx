// Segmented operating-mode control: LIVE | SIMULATOR.
// Switching modes on an engineering instrument — quiet, precise, no glow.
export default function ModeSwitcher({ mode, onSwitch }) {
  return (
    <div className="mode-switcher" role="tablist" aria-label="Operating mode">
      <button
        type="button"
        role="tab"
        aria-selected={mode === "live"}
        className={`mode-option ${mode === "live" ? "mode-option-active" : ""}`}
        onClick={() => onSwitch("live")}
      >
        LIVE
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "demo"}
        className={`mode-option ${mode === "demo" ? "mode-option-active" : ""}`}
        onClick={() => onSwitch("demo")}
      >
        SIMULATOR
      </button>
    </div>
  );
}
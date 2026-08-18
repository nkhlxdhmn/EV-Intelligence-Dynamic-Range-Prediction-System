const path = require("path");

const query = process.env.MODE_QUERY || "";
global.window = {
  location: { search: query },
  history: { replaceState() {} },
};

const outfile = path.join(__dirname, ".smoke-out", "bundle.cjs");
const React = require("react");
const { renderToString } = require("react-dom/server");
const C = require(outfile);

let failures = 0;
// React SSR inserts hydration markers between dynamic text nodes; strip them
// so checks compare the real text the browser would show.
const strip = (html) => html.replace(/<!-- -->/g, "");
const check = (label, html, needles) => {
  const norm = strip(html);
  for (const n of needles) {
    if (!norm.includes(n)) {
      failures++;
      console.log(`  FAIL ${label}: missing "${n}"`);
    }
  }
};
const render = (el) => renderToString(el);

const pred = {
  expected_range_km: 186,
  conservative_range_km: 148,
  optimistic_range_km: 232,
  usable_energy_kwh: 44.4,
  predicted_energy_kwh_per_km: 0.1415,
};

// 1) full App initial state (demo)
if (query === "") {
  const appHtml = render(React.createElement(C.App));
  check("App", appHtml, [
    "EV INTELLIGENCE", "SIMULATOR", "PRIMARY TELEMETRY", "RANGE DISTRIBUTION",
    "ENERGY CONSUMPTION", "BATTERY", "ROUTE / TERRAIN", "VEHICLE TELEMETRY",
    "MODEL / PREDICTION", "DATA QUALITY", "SIMULATOR",
  ]);
}

// 2) hero with values + prediction
const hero = render(React.createElement(C.HeroMetrics, {
  values: { speed_kmh: 64, soc_pct: 74, distance_since_trip_start_km: 3.2 },
  predictionReady: true, lastPred: pred, telemetry: { status: "ok" }, phase: "CRUISING",
}));
check("Hero", hero, [">64<", "74", "186", "CONSERVATIVE", "EXPECTED", "OPTIMISTIC", "CRUISING"]);

// 3) range viz with band + empty fallback
const rv = render(React.createElement(C.RangeVisualization, { lastPred: pred, predictionReady: true }));
check("RangeViz", rv, ["range-scale", "range-marker-e", "range-axis-exp", "CONSERVATIVE", "OPTIMISTIC"]);
const rvEmpty = render(React.createElement(C.RangeVisualization, { lastPred: null, predictionReady: false }));
check("RangeVizEmpty", rvEmpty, ["RANGE UNAVAILABLE"]);
const rvBad = render(React.createElement(C.RangeVisualization, { lastPred: { expected_range_km: undefined }, predictionReady: true }));
check("RangeVizBad", rvBad, ["RANGE VALUES UNAVAILABLE"]);

// 4) energy chart with history + empty
const hist = Array.from({ length: 12 }, (_, i) => ({ t: Date.now() + i * 1000, pred: 0.14 + (i % 3) * 0.01 }));
const ec = render(React.createElement(C.EnergyChart, { history: hist, horizonKm: 5 }));
check("EnergyChart", ec, ["energy-svg", "last 12 predictions", "trend"]);
const ecEmpty = render(React.createElement(C.EnergyChart, { history: [], horizonKm: 5 }));
check("EnergyChartEmpty", ecEmpty, ["WAITING FOR PREDICTION"]);

// 5) battery idle + regen
const bat = render(React.createElement(C.BatteryPanel, {
  values: { soc_pct: 74, battery_voltage_v: 352.2, battery_current_a: 41.7, battery_power_kw: 14.7, battery_temperature_c: 28.4, battery_capacity_kwh: 60, regen_power_kw: 0.02 },
}));
check("Battery", bat, ["74", "352.2", "41.7", "REGEN", "TEMPERATURE"]);
const batRegen = render(React.createElement(C.BatteryPanel, {
  values: { soc_pct: 80, regen_power_kw: 12.5, battery_voltage_v: 352, battery_current_a: -35.5, battery_power_kw: -12.5, battery_temperature_c: 27, battery_capacity_kwh: 60 },
}));
check("BatteryRegen", batRegen, ["REGEN 12.5 kW"]);

// 6) terrain sim route + empty
const route = { source: "SIMULATOR_ROUTE", points: [{ offset_km: 0, altitude_m: 100 }, { offset_km: 1, altitude_m: 120 }, { offset_km: 2, altitude_m: 95 }] };
const terr = render(React.createElement(C.TerrainPanel, {
  mode: "demo", simRoute: route, simDistanceKm: 0.5, routeStatus: { available: true }, scenarioInfo: { route_profile: "hilly" },
}));
check("Terrain", terr, ["terrain-svg", "SIMULATED TERRAIN", "HILLY", "VEHICLE", "NET GRADIENT"]);
const terrEmpty = render(React.createElement(C.TerrainPanel, {
  mode: "demo", simRoute: null, simDistanceKm: 0, routeStatus: { available: false }, scenarioInfo: {},
}));
check("TerrainEmpty", terrEmpty, ["NO ROUTE DATA"]);

// 7) telemetry
const tel = render(React.createElement(C.VehicleTelemetry, {
  values: { speed_kmh: 64, motor_rpm: 4200, motor_torque_nm: 85, motor_power_kw: 14.2, aux_power_kw: 0.6, battery_power_kw: 14.8, battery_temperature_c: 28.4, ambient_temperature_c: 18, altitude_m: 105, current_gradient_pct: 1.2, time_since_trip_start_min: 4.3 },
  accelerationMps2: 0.35, phase: "CRUISING",
}));
check("Telemetry", tel, ["MOTOR RPM", "4,200", "ACCELERATION", "+0.35 m/s²", "PHASE", "TRIP TIME"]);

// 8) prediction panel
const pp = render(React.createElement(C.PredictionPanel, {
  modelInfo: { model: "ExtraTreesRegressor", model_version: "ev-energy-devrt-v1", dataset: "DEVRT", horizon_km: 5, route_aware: true },
  predictionReady: true,
  lastPred: { ...pred, status: "OK", confidence: { level: "high" }, ood: { is_ood: false } },
}));
check("PredictionPanel", pp, ["ExtraTreesRegressor", "ev-energy-devrt-v1", "DEVRT", "5 km", "RELIABILITY", "HIGH"]);

// 9) data quality
const dq = render(React.createElement(C.DataQuality, {
  mode: "demo", simTelemetry: { speed_kmh: 64 }, simRoute: route,
  telemetry: { status: "ok", signals: [], quality: "VALID" }, routeStatus: { available: true },
  predictionReady: true, apiConnected: true, modelInfo: { model: "x" }, liveStatus: {},
}));
check("DataQuality", dq, ["GOOD", "READY", "COMPLETE", "SIMULATOR"]);
const dqLive = render(React.createElement(C.DataQuality, {
  mode: "live", simTelemetry: null, simRoute: null,
  telemetry: { status: "offline", signals: [], quality: "UNAVAILABLE" }, routeStatus: { available: false },
  predictionReady: false, apiConnected: true, modelInfo: { model: "x" },
  liveStatus: { available_signals: [], required_signal_status: { soc_pct: "MISSING", vehicle_speed_kmh: "MISSING" } },
}));
check("DataQualityLive", dqLive, ["OFFLINE", "UNAVAILABLE", "MISSING"]);

// 10) simulator controls
const sim = render(React.createElement(C.SimulatorControls, {
  running: true, simScenario: "SIM-12345678",
  scenarioInfo: { driving_style: "eco", traffic_level: "light", route_profile: "flat", ambient_temperature_c: 18, initial_soc_pct: 80, vehicle_mass_kg: 1800, seed: 42, route: { length_km: 39.2 } },
  seed: 42, simSpeed: 2, pollMs: 1500, lastError: null,
  onStart() {}, onPause() {}, onReset() {}, onRandomize() {}, onChangeSimSpeed() {}, onChangePollMs() {}, onChangeSeed() {},
}));
check("SimulatorControls", sim, ["SIM-12345678", "ECO", "FLAT", "LIGHT", "80 %", "1800 kg", "2×", "START", "RANDOMIZE", "SEED"]);

// 11) live controls (connected + disconnected)
const live = render(React.createElement(C.LiveControls, {
  telemetry: { status: "ok", age_ms: 320 },
  liveStatus: { provider: "telematics", prediction_ready: true, prediction_ready_reason: "ready" },
  lastPredAt: Date.now(), running: true,
}));
check("LiveControls", live, ["CONNECTED", "TELEMATICS", "LAST PREDICTION"]);
const liveOff = render(React.createElement(C.LiveControls, {
  telemetry: { status: "offline", age_ms: 0 },
  liveStatus: { provider: null, prediction_ready: false, prediction_ready_reason: "no telemetry source connected" },
  lastPredAt: null, running: false,
}));
check("LiveControlsOff", liveOff, ["DISCONNECTED", "NONE", "no telemetry source connected".toUpperCase()]);

// 12) header both modes
const hdrLive = render(React.createElement(C.Header, { mode: "live", simScenario: null, telemetry: { status: "ok", age_ms: 150 }, running: true }));
check("HeaderLive", hdrLive, ["LIVE", "Telemetry"]);
const hdrSim = render(React.createElement(C.Header, { mode: "demo", simScenario: "SIM-12345678", telemetry: { status: "offline", age_ms: 0 }, running: true }));
check("HeaderSim", hdrSim, ["SIMULATOR", "SIM-12345678"]);

// 13) footer
const foot = render(React.createElement(C.Footer, {
  mode: "demo", apiConnected: true, predictionReady: true, lastError: null,
  reliability: { status: "OK", level: "medium" }, telemetry: { status: "ok" },
  modelInfo: { model: "ExtraTreesRegressor", feature_count: 102 },
}));
check("Footer", foot, ["API CONNECTED", "MEDIUM", "SIMULATOR DATA", "102"]);

// 14) system status + mode switcher
const ss = render(React.createElement(C.SystemStatus, {
  apiConnected: true, modelInfo: { model: "x" }, predictionReady: true, lastError: null,
  mode: "demo", routeAvailable: true, running: true,
}));
check("SystemStatus", ss, ["API", "CONNECTED", "MODEL", "LOADED", "PREDICTION", "READY", "ROUTE", "READY"]);
const ms = render(React.createElement(C.ModeSwitcher, { mode: "demo", onSwitch() {} }));
check("ModeSwitcher", ms, ["LIVE", "SIMULATOR", "mode-option-active"]);

// 15) energy panel
const ep = render(React.createElement(C.EnergyPanel, {
  predictionReady: true, lastPred: pred, history: hist, modelInfo: { horizon_km: 5 },
}));
check("EnergyPanel", ep, ["0.141", "kWh/km", "avg over next 5 km"]);

console.log(failures ? `\n${failures} CHECK(S) FAILED (mode query "${query}")` : `\nALL RENDER CHECKS PASSED (mode query "${query}")`);
process.exit(failures ? 1 : 0);

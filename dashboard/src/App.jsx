import { useMemo } from "react";
import { useDashboard } from "./useDashboard";
import Header from "./components/Header";
import ModeSwitcher from "./components/ModeSwitcher";
import SystemStatus from "./components/SystemStatus";
import HeroMetrics from "./components/HeroMetrics";
import RangeVisualization from "./components/RangeVisualization";
import EnergyPanel from "./components/EnergyPanel";
import BatteryPanel from "./components/BatteryPanel";
import TerrainPanel from "./components/TerrainPanel";
import VehicleTelemetry from "./components/VehicleTelemetry";
import PredictionPanel from "./components/PredictionPanel";
import DataQuality from "./components/DataQuality";
import SimulatorControls from "./components/SimulatorControls";
import LiveControls from "./components/LiveControls";
import Footer from "./components/Footer";

// Unify demo (backend simulator) and live (telemetry signals) into one
// normalized value set for display. Missing values stay undefined (rendered
// as "—"); nothing is synthesized.
function useValues(dash) {
  return useMemo(() => {
    if (dash.mode === "demo") {
      const t = dash.simTelemetry || {};
      return {
        speed_kmh: t.speed_kmh,
        soc_pct: t.soc_pct,
        altitude_m: t.altitude_m,
        ambient_temperature_c: t.ambient_temperature_c,
        battery_capacity_kwh: t.battery_capacity_kwh,
        motor_power_kw: t.motor_power_kw,
        battery_voltage_v: t.battery_voltage_v,
        battery_temperature_c: t.battery_temperature_c,
        current_gradient_pct: t.current_gradient_pct,
        distance_since_trip_start_km: t.distance_since_trip_start_km,
        time_since_trip_start_min: t.time_since_trip_start_min,
        motor_rpm: t.motor_rpm,
        motor_torque_nm: t.motor_torque_nm,
        battery_current_a: t.battery_current_a,
        battery_power_kw: t.battery_power_kw,
        aux_power_kw: t.aux_power_kw,
        regen_power_kw: t.regen_power_kw,
      };
    }
    const byName = (name) => {
      const s = dash.telemetry.signals.find((x) => x.name === name);
      return s && s.quality === "VALID" ? s.value : undefined;
    };
    return {
      speed_kmh: byName("vehicle_speed_kmh"),
      soc_pct: byName("soc_pct"),
      altitude_m: byName("altitude_m"),
      ambient_temperature_c: byName("ambient_temperature_c"),
      battery_capacity_kwh: byName("battery_capacity_kwh"),
      motor_power_kw: byName("motor_power_kw"),
      battery_voltage_v: byName("battery_voltage_v"),
      battery_temperature_c: byName("battery_temperature_c"),
      current_gradient_pct: undefined,
      distance_since_trip_start_km: byName("distance_since_trip_start_km"),
      time_since_trip_start_min: byName("time_since_trip_start_min"),
      motor_rpm: byName("motor_rpm"),
      motor_torque_nm: byName("motor_torque_nm"),
      battery_current_a: byName("battery_current_a"),
      battery_power_kw: byName("battery_power_kw"),
      aux_power_kw: byName("aux_power_kw"),
      regen_power_kw: byName("regen_power_kw"),
    };
  }, [dash.mode, dash.simTelemetry, dash.telemetry]);
}

export default function App() {
  const dash = useDashboard();
  const values = useValues(dash);
  const isSim = dash.mode === "demo";

  const routeAvailable = isSim
    ? !!dash.simRoute
    : dash.routeStatus.available === true;

  return (
    <>
      <Header
        mode={dash.mode}
        simScenario={dash.simScenario}
        telemetry={dash.telemetry}
        running={dash.running}
      />

      <div className="modebar">
        <ModeSwitcher mode={dash.mode} onSwitch={dash.switchMode} />
        <SystemStatus
          apiConnected={dash.apiConnected}
          modelInfo={dash.modelInfo}
          predictionReady={dash.predictionReady}
          lastError={dash.lastError}
          mode={dash.mode}
          routeAvailable={routeAvailable}
          running={dash.running}
        />
        {isSim && <span className="modebar-note">{dash.demoLabel}</span>}
      </div>

      <main className="layout">
        <HeroMetrics
          values={values}
          predictionReady={dash.predictionReady}
          lastPred={dash.lastPred}
          telemetry={dash.telemetry}
          phase={isSim && values.speed_kmh !== undefined ? dash.simTelemetry?.phase : null}
        />
        <RangeVisualization
          lastPred={dash.lastPred}
          predictionReady={dash.predictionReady}
        />

        <div className="row row-main">
          <EnergyPanel
            predictionReady={dash.predictionReady}
            lastPred={dash.lastPred}
            history={dash.history}
            modelInfo={dash.modelInfo}
          />
          <BatteryPanel values={values} />
        </div>

        <div className="row row-main">
          <TerrainPanel
            mode={dash.mode}
            simRoute={dash.simRoute}
            simDistanceKm={values.distance_since_trip_start_km}
            routeStatus={dash.routeStatus}
            scenarioInfo={dash.scenarioInfo}
          />
          <VehicleTelemetry
            values={values}
            accelerationMps2={dash.accelerationMps2}
            phase={isSim ? dash.simTelemetry?.phase : null}
          />
        </div>

        <div className="row row-bottom">
          <PredictionPanel
            modelInfo={dash.modelInfo}
            predictionReady={dash.predictionReady}
            lastPred={dash.lastPred}
          />
          <DataQuality
            mode={dash.mode}
            simTelemetry={dash.simTelemetry}
            simRoute={dash.simRoute}
            telemetry={dash.telemetry}
            routeStatus={dash.routeStatus}
            predictionReady={dash.predictionReady}
            apiConnected={dash.apiConnected}
            modelInfo={dash.modelInfo}
            liveStatus={dash.liveStatus}
          />
          {isSim ? (
            <SimulatorControls
              running={dash.running}
              simScenario={dash.simScenario}
              scenarioInfo={dash.scenarioInfo}
              seed={dash.seed}
              simSpeed={dash.simSpeed}
              pollMs={dash.pollMs}
              lastError={dash.lastError}
              onStart={dash.start}
              onPause={dash.pause}
              onReset={dash.reset}
              onRandomize={dash.randomize}
              onChangeSimSpeed={dash.changeSimSpeed}
              onChangePollMs={dash.changePollMs}
              onChangeSeed={dash.changeSeed}
            />
          ) : (
            <LiveControls
              telemetry={dash.telemetry}
              liveStatus={dash.liveStatus}
              lastPredAt={dash.lastPredAt}
              running={dash.running}
            />
          )}
        </div>
      </main>

      <Footer
        mode={dash.mode}
        apiConnected={dash.apiConnected}
        predictionReady={dash.predictionReady}
        lastError={dash.lastError}
        reliability={dash.reliability}
        telemetry={dash.telemetry}
        modelInfo={dash.modelInfo}
      />
    </>
  );
}
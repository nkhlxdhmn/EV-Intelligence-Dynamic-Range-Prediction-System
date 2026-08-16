// EV RANGE MONITOR - demo telemetry simulator.
// Generates clearly-labeled SIMULATED telemetry; never presented as real data.

// THIS SIMULATOR IS FOR DEVELOPMENT AND TESTING ONLY.
// It must never be presented as real vehicle data or real-world performance.
// Usage: ?telemetry=0 (default) or ?telemetry=1 for live mode (if connected).

export function createSimulator() {
  return {
    soc: 85.0,
    speed: 42.0,
    altitude: 150.0,
    temp: 18.0,
    distance: 0.0,
    timeMin: 0.0,
    motorPower: 6.0,
    auxPower: 0.6,
    regen: 0.0,
    battVolt: 348.0,
    battTemp: 24.0,
    targetSpeed: 48.0,
    phase: 0,
    route: [],
    routeTotalKm: 42.6,
    simulator: true,  // explicit marker

    reset() {
      this.soc = 85.0;
      this.speed = 42.0;
      this.altitude = 150.0;
      this.temp = 18.0;
      this.distance = 0.0;
      this.timeMin = 0.0;
      this.motorPower = 6.0;
      this.auxPower = 0.6;
      this.regen = 0.0;
      this.battVolt = 348.0;
      this.battTemp = 24.0;
      this.targetSpeed = 48.0;
      this.phase = 0;
      this.route = [];
      this.routeTotalKm = 42.6;
      // Rebuild route with elevation data
      let elev = 150;
      for (let i = 0; i <= 25; i++) {
        elev += Math.sin(i * 0.55) * 4 + (i > 12 ? 1.2 : 0.6);
        this.route.push({
          offset_km: +(i * 0.2).toFixed(2),
          altitude_m: Math.round(elev),
        });
      }
    },

    tick(dt) {
      this.phase += dt;
      if (Math.random() < 0.05) {
        this.targetSpeed = Math.min(95, Math.max(20, this.targetSpeed + (Math.random() - 0.5) * 18));
      }
      this.speed = this.targetSpeed + Math.sin(this.phase * 0.8) * 4;
      this.speed = Math.max(0, this.speed);

      const dKm = (this.speed / 3.6) * dt / 1000;
      this.distance += dKm;
      this.timeMin += dt / 60;

      const prog = (this.distance % this.routeTotalKm) / this.routeTotalKm;
      const idx = Math.min(this.route.length - 1, Math.floor(prog * this.route.length));
      this.altitude = this.route[idx].altitude_m + Math.sin(this.phase * 0.3) * 3;

      this.temp += (20.0 - this.temp) * 0.002 + (Math.random() - 0.5) * 0.2;
      this.temp = Math.min(30, Math.max(5, this.temp));

      this.motorPower = Math.max(0, this.speed * 0.28 + (Math.random() - 0.4) * 3);
      this.auxPower = 0.5 + Math.sin(this.phase * 0.05) * 0.2;
      this.regen = this.speed > 5 && Math.random() < 0.12 ? -Math.min(12, this.motorPower * 0.8) : 0;

      this.battVolt = 320 + this.soc * 0.42 + Math.sin(this.phase) * 2;
      this.battTemp = 23 + this.motorPower * 0.15;
    },

    applyConsumption(pred, dKm) {
      if (!pred || pred <= 0) return;
      const usedKwh = pred * dKm;
      const capacityKwh = 58.0;
      this.soc = Math.max(5, Math.min(100, this.soc - (usedKwh / capacityKwh) * 100));
    },
  };
}
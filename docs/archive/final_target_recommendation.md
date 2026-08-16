# Final Target Recommendation

## 1. What should the ML model predict?
The model should predict:
**`future_energy_consumption_kwh_per_km`**

## 2. Why?
Unlike a trip-level baseline reference (which merely categorizes the vehicle or route broadly), a future-window dynamic target tells us exactly how much energy will be consumed given the *current* state of the EV (current speed, current terrain). This allows a dynamic recalculation of remaining range based on shifting conditions, rather than sticking to a static WLTP or trip-level estimate.

## 3. Which dataset supports it?
**DEVRT** is the only dataset that has trip distance, reliable SOC tracking (albeit discrete), and altitude/terrain data all correlated to valid timestamps in a high-resolution format.

## 4. What prediction horizon should be used?
**5 Kilometers (distance-based window).**
*Reasoning*: EDA showed that DEVRT average energy consumption is ~0.15 kWh/km. A 1% change in State of Charge (SOC) for a 33–62 kWh battery requires roughly 0.33 to 0.62 kWh of energy. Thus, SOC only drops 1% every 2 to 4 km. A 1 km horizon would result in massive amounts of "0 kWh" targets due to integer SOC values not ticking over. A 5 km window provides stable SOC delta readings without smoothing over terrain features too heavily.

## 5. What features are available at prediction time?
- **Battery**: Current SOC, Battery Capacity.
- **Terrain**: Current altitude, current gradient, terrain class (FLAT, UPHILL, DOWNHILL) derived from past 1 km.
- **Speed & Environment**: Current speed, mean speed over past 1 km, vehicle model.
- *(For Nissan Leaf only)*: Current ambient temperature, motor power, auxiliary power.

## 6. What information must be excluded? (No Target Leakage)
- Any observation taken *after* time `t`.
- Future SOC, future speed, future altitude, future motor power.
- End-of-trip SOC, end-of-trip distance, total energy consumed for the entire trip.

## 7. How will the target be calculated?
At any given timestamp `t`, we look ahead to timestamp `t+n` where the distance covered reaches 5 km (without crossing a trip boundary).

Formula:
```python
energy_consumed_future_kwh = (SOC_at_start - SOC_at_end) * battery_capacity_kwh / 100
future_energy_consumption_kwh_per_km = energy_consumed_future_kwh / 5.0
```

## 8. How will range eventually be calculated?
Once the ML model predicts the `predicted_energy_consumption_kwh_per_km` for the current condition, the dynamic range calculation is:
```python
remaining_energy_kwh = current_SOC * battery_capacity_kwh / 100
estimated_range_km = remaining_energy_kwh / predicted_energy_consumption_kwh_per_km
```

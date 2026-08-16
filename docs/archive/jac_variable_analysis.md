# JAC IEV40 Variable Analysis

## VOL (Battery Voltage)

### Exact Unit
- **Volt (V)** - as per column header name
- But observed range 0-379V does not match typical EV or 12V vehicle architectures

### Exact Meaning
- **NOT direct battery voltage** - the range and values suggest raw sensor readings or scaled values
- Mean: 16.57V - too low for EV pack (typically 400V+), too high for 12V system (typically 12-14V)
- Only 17.1% of values in 10-16V range (possible 12V system)
- 2.1% in 150-450V EV range
- 80.8% of values outside both typical ranges
- Most likely: **raw ADC (Analog-to-Digital Converter) values** or **scaled values** requiring calibration

### Plausible Range Interpretation
- If 12V system: values ~10-16V would be normal, but most values are outside this
- If raw ADC with 5V reference: 0-379 suggests ~1.5% resolution or different reference
- If scaled: might need multiplication factor (e.g., ×10, ×100)
- **Conclusion**: Requires documentation review or calibration data to interpret correctly

### Scaling Required
- **YES** - raw values cannot be used as-is for battery voltage
- May need: multiplication factor, offset, or ADC conversion
- Without documentation: cannot determine exact scaling

### Whether Raw Sensor Values
- **Likely yes** - the 0-379 range with mean 16.57V is consistent with raw ADC readings
- Could be: voltage divider output, raw sensor ADC, or scaled representation
- Requires investigation of hardware documentation

## CUR (Battery Current)

### Exact Unit
- **Ampere (A)** - as per column header name

### Exact Meaning
- **Battery current** - current flowing into/out of the battery
- Negative values: 365 rows (discharge, energy consumed)
- Positive values: 544 rows (charge, energy regenerated/put back)
- Zero values: 91 rows (no current flow)
- Mean: 30.18 A
- Range: -40 to 263 A

### Plausible Range
- -40A to 263A is plausible for EV battery current
- 263A is high but possible during aggressive acceleration
- Negative current (discharge): 365/1000 = 36.5% of sampled rows
- Positive current (charge): 544/1000 = 54.4% of sampled rows
- This unusual distribution (more charge than discharge in sample) warrants investigation

### Scaling Required
- **MAYBE** - values could be raw ADC or scaled
- 263A maximum is plausible for EV batteries
- However without scaling factor documentation, exact values uncertain
- **Recommendation**: treat as raw current, monitor for anomalies

### Raw Sensor Values
- **Possible** - the negative-to-positive ratio and range could be raw
- But could also be engineered/scaled values
- **Recommendation**: investigate with vehicle documentation

## SPD (Speed)

### Exact Unit
- **km/h** (kilometers per hour) - consistent with column name

### Exact Meaning
- Vehicle speed as measured by speedometer/sensors
- Range: 0-133 km/h
- Mean: 49.92 km/h
- No negative values (speed is non-negative by definition)
- 165 zero values (vehicle stopped)
- 130 unique values indicates continuous measurement

### Plausible Range
- 0-133 km/h is fully plausible for real-world driving
- Mean 49.92 km/h suggests mixed urban/ suburban driving
- **No scaling required** - appears to be direct speed measurement

### Raw Sensor Values
- **Likely direct speed** from vehicle speed sensor (VSS)
- No indication of raw ADC or scaling needed
- **Can be used as-is** for speed-based features

## ODO (Odometer)

### Exact Unit
- **km** (kilometers) - consistent with column name and values

### Exact Meaning
- Vehicle odometer reading (accumulated distance)
- Range: 25656 to 26347 km
- Mean: 25699.81 km
- Total distance in sample: 26347 - 25656 = 691 km
- 273 unique values across 1000-row sample

### Plausible Range
- 25,656 to 26,347 km is plausible for a vehicle's lifetime odometer reading
- Makes sense as a cumulative distance counter

### Scaling Required
- **NO** - appears to be direct odometer reading in km

## LAT/LON (GPS Coordinates)

### Exact Unit
- **Decimal degrees** (latitude/longitude)

### Exact Meaning
- GPS latitude: -21.968201 to 21.799545
- GPS longitude: -46.683334 to 263.000000
- **Longitudinal range is suspicious**: 263.000000 maximum is not valid (longitude ranges -180 to +180)
- Latitudinal range -21.9 to +21.9 is reasonable for equatorial regions
- 1000/1000 non-null for both coordinates

### Anomaly - Longitude
- Maximum longitude of 263.0 suggests either:
  - Data error/corruption
  - Different coordinate system
  - Wrapped/modulo 360 applied
  - Raw ADC value not interpreted as degrees
- **Requires investigation** before using for geospatial analysis

### Scaling Required
- **MAYBE** for longitude specifically
- Latitude appears valid
- Longitude may need: modulo 360 correction or documentation review

## ALT (Altitude)

### Exact Unit
- **meters (m)** - as per column name

### Exact Meaning
- Range: 0 to 1333.5 m
- Mean: 1169.80 m
- 596 unique values across 1000-row sample
- Could be altitude above sea level or above trip start reference

### Plausible Range
- 0-1333.5 m is plausible for various terrains (sea level to mountain)
- Mean 1169.8 m suggests hilly/mountainous driving
- **May need context**: altitude relative to what reference frame?

### Scaling Required
- **MAYBE** - could be above sea level or relative altitude
- Without documentation: cannot determine reference frame
- **Recommendation**: treat as altitude value, investigate reference frame later

## AIR (Ambient Temperature) - CRITICAL FINDING

### Exact Unit
- **NOT °C as initially assumed** - the actual values reveal a different meaning

### Exact Meaning - DISCOVERED
- **Only 2 unique values**: 0 and 2
- 469 zero values, 531 values of 2
- **NOT a continuous temperature measurement**
- **Likely a flag or placeholder variable**

### Investigated Interpretations
1. **Raw ADC values**: 0 and 2 could be sensor states
2. **EIS (Embedded Instrumentation System) flags**: marker for temperature sensor validity
3. **Missing data marker**: 0 = invalid/missing, 2 = valid
4. **Scaled temperature**: if °C, range 0-2°C is very narrow for ambient
5. **Kelvin**: 0K = absolute zero (impossible), 2K = very cold (possible in labs)

### Kelvin Interpretation Test
- If Kelvin to °C: min = 0-273 = -273°C, max = 2-273 = -271°C
- Both are physically impossible for ambient air
- **Reject Kelvin interpretation**

### (AIR-2)/10 Interpretation
- If (AIR-2)/10: min = (0-2)/10 = -0.2, max = (2-2)/10 = 0
- Range -0.2 to 0°C - very narrow but possible
- **Possible but uncertain**

### AIR-2 Interpretation
- If AIR-2: min = 0-2 = -2, max = 2-2 = 0
- Range -2 to 0°C - very narrow
- **Possible but uncertain**

### Most Likely Interpretation
- **Flag/variable indicating temperature sensor status**
- 0 = invalid/unreliable, 2 = valid/available
- Not actual temperature reading
- **DO NOT use as ambient temperature data**

### Confirmed by Statistics
- Only 2 unique values across 1000 rows
- Bimodal distribution (0 and 2 only)
- 46.9% zeros, 53.1% twos
- Consistent with a binary flag or counter, not a continuous measurement

### Recommendation
- **DO NOT use AIR column as ambient temperature**
- Investigate documentation for intended meaning
- May need to exclude or replace with other environmental data
- Could potentially use as a sensor validity flag (if documentation confirms)

## BRK (Brake)

### Exact Unit
- **Unknown/Raw** - not percentage (0-100%) or standard analog value

### Exact Meaning
- Range: 0 to 28
- Mean: 1.83
- 14 unique values
- Sample values: 0, 4, 6, 8, 10, 16, 18, 26, 28
- Distribution: heavily skewed toward low values
- 1000 rows all in range 0-28

### Compared to Expectations
- If brake pedal position 0-100%: would expect 0-100, ~101 unique values
- If raw ADC: 0-255 or similar range more common
- If event counter: 0-28 could be event count within time window
- **Most likely**: raw sensor value or discrete event counter, NOT 0-100% pedal position

### Values >= 26 occur rarely
- (26 and 28 are max values, only few rows)
- Could indicate hard braking events

### Scaling Required
- **YES** - cannot interpret as 0-100% brake pedal position
- May be: raw analog value, event counter, or different scaling
- **Recommendation**: investigate documentation; do not assume percentage

## ACC (Accelerator)

### Exact Unit
- **Unknown/Raw** - not percentage (0-100%) as might be expected

### Exact Meaning
- Range: 0 to 90
- Mean: 13.91
- 46 unique values
- Sample values: 0, 2, 6, 8, 10, 16, 28, 30, 32, 36
- Distribution: heavily skewed toward low/closed-throttle values
- 905/1000 rows have ACC < 50 (partial/throttle closed)
- Only 95 rows have ACC >= 50

### Compared to Expectations
- If accelerator pedal 0-100%: would expect 0-100, ~101 unique values
- Most values below 50 suggest either:
  - Conservative driving sample
  - Raw value with different scaling (e.g., 0-90 range)
  - Acceleration pedal position not full range
- **Most likely**: raw sensor value with 0-90 range, or filtered/throttle position

### Scaling Required
- **YES** - cannot interpret as 0-100% accelerator pedal position
- May be: raw ADC 0-90, filtered value, or different mapping
- **Recommendation**: investigate documentation; do not assume percentage

## AUT (Automatic Mode)

### Exact Unit
- **Unknown** - numeric code or flag

### Exact Meaning
- Range: 49 to 273
- Mean: 224.39
- 83 unique values
- Sample values: 139, 135, 272, 199, 170, 56, 147, 113, 114, 174
- No obvious pattern without documentation

### Compared to Expectations
- If automatic transmission mode: might expect codes like P/R/N/D/L, or 0-4 values
- 83 unique values suggests raw sensor or coded system
- **Requires documentation** for interpretation

### ECO Mode

### Exact Unit
- **Unknown** - binary or multi-state flag

### Exact Meaning
- Only 2 unique values: 0 and 192
- Mean: 29.57 (heavily influenced by the 192 outliers)
- Actually: bimodal - most rows have 0, some have 192
- 0 = ECO mode off, 192 = ECO mode on (or vice versa)
- **Likely a binary ECO mode indicator**

### Scaling Required
- **NO** for basic interpretation - appears to be binary (0/192)
- Value 192 may be: memory address, flag bit pattern, or coded value
- **Recommendation**: treat as binary ECO mode flag (0 = off, 192 = on)

## AX/AY/AZ (Accelerometer)

### Exact Unit
- **Raw ADC counts** - not yet converted to m/s²

### Exact Meaning
- AX: -871 to 1306, mean 167.03
- AY: -106 to 1636, mean 882.92
- AZ: 584 to 3680, mean 1889.14

### Gravity Detection
- Expected gravitational acceleration: ~9.81 m/s² on Z-axis when vehicle level
- AZ mean: 1889.14
- Scaling factor: 1889.14 / 9.81 ≈ 192.6 counts per g
- **AX/g**: -871/192 ≈ -4.5g, AY/g ≈ 8.5g, AZ/g ≈ 1g
- This confirms scale factor of ~192 counts per gravitational acceleration

### Converted to m/s² (dividing by ~192):
- AX_g ≈ AX / 192, AY_g ≈ AY / 192, AZ_g ≈ AZ / 192
- After conversion: actual acceleration in m/s² = (count / 192) × 9.81

### Scaling Required
- **YES** - must divide by ~192 to get m/s²
- Or use factor 9.81/192 = 0.0511 m/s² per count

### Raw Sensor Values
- **Yes**, raw ADC counts from 3-axis accelerometer
- After scaling: usable acceleration data
- **Recommendation**: divide by 192 (or use calibrated factor) to get m/s²

## GX/GY/GZ (Gyroscope)

### Exact Unit
- **Raw ADC counts** - angular rate, not yet converted to rad/s

### Exact Meaning
- GX: -328 to 312, mean -4.41
- GY: -392 to 265, mean -7.79
- GZ: -370 to 401, mean 4.18
- 3-axis angular rate sensor

### Scaling Required
- **YES** - gyroscope raw counts need conversion to angular velocity
- Typical scale: depends on sensor full-scale range (e.g., 2000°/s, 1000°/s)
- Without sensor specification: cannot determine exact conversion factor
- **Recommendation**: investigate sensor datasheet or calculate from known movements

### Summary Table: JAC IEV40 Variables

| Column | Meaning | Unit | Scaling | Raw/Processed | Confidence |
|--------|---------|------|---------|---------------|------------|
| VOL | Battery voltage (unverified) | V | Unknown (likely raw ADC) | Raw | Medium |
| CUR | Battery current | A | Maybe | Raw | Medium |
| SPD | Vehicle speed | km/h | None required | Likely direct | High |
| ODO | Odometer distance | km | None required | Likely direct | High |
| LAT | GPS latitude | deg | Maybe (longitude 263 suspicious) | Direct (lat) / Suspect (lon) | Medium |
| ALT | Altitude | m | Maybe (reference frame) | Likely direct | Medium |
| AIR | Ambient temp | — | **Flag** (0/2 only) | **Processed flag** | **High** (as flag) |
| BRK | Brake status | — | Unknown | Raw | Low |
| ACC | Accelerator position | — | Unknown (likely raw) | Raw | Low |
| AUT | Automatic mode | — | Unknown | Raw | Low |
| ECO | ECO mode | Binary (0/192) | None | Binary flag | High |
| AX | Accelerometer X | Raw counts | /192 → m/s² | Raw | Medium (after scaling) |
| AY | Accelerometer Y | Raw counts | /192 → m/s² | Raw | Medium (after scaling) |
| AZ | Accelerometer Z | Raw counts | /192 → m/s² | Raw | Medium (after scaling) |
| GX | Gyroscope X | Raw counts | Unknown | Raw | Low |
| GY | Gyroscope Y | Raw counts | Unknown | Raw | Low |
| GZ | Gyroscope Z | Raw counts | Unknown | Raw | Low |

### JAC AIR Explanation (Final)
The AIR column in the JAC IEV40 dataset contains **only 2 unique values (0 and 2)**, distributed as 469 zeros and 531 twos. This is **NOT** a continuous ambient temperature measurement as might be assumed from the column name. 

**The AIR column is likely a sensor status flag**:
- 0 = temperature sensor data invalid/unreliable
- 2 = temperature sensor data valid/available

**Evidence**:
- Only 2 unique values across 24,277 total rows (examined 1000)
- Bimodal distribution inconsistent with ambient temperature (-40 to 215°C typical range)
- Name "AIR" suggests "Ambient Air Temperature" but values don't match
- Without documentation confirming actual meaning, treat as flag/variable indicating sensor validity

**Do not use AIR as ambient temperature**. Instead, either:
1. Exclude from environmental features
2. Use only if documentation confirms its actual meaning
3. Replace with other available environmental data

### JAC VOL Explanation
The VOL column has range 0-379V with mean 16.57V. Only 17.1% of values fall in the 10-16V range (possible 12V system), 2.1% in 150-450V EV range, and 80.8% outside both. This indicates VOL is **not direct battery voltage** in any standard EV architecture.

**Most likely interpretations**:
1. **Raw ADC values** from a voltage divider circuit (0-379 represents the ADC output range)
2. **Scaled values** requiring multiplication factor from documentation
3. **Different electrical architecture** (unlikely given typical EV voltages)

**Without access to hardware documentation**, VOL cannot be reliably interpreted as battery voltage. **Recommendation**: 
- Either exclude VOL from voltage-dependent features
- Or investigate vehicle documentation for scaling factor
- Do not use for power calculations until scaling is confirmed

### JAC Timestamp Analysis

The JAC dataset has 6 decomposed date/time columns:
- Y (year), M (month), D (day), H (hour), MIN (minute), SEC (second)

From the sample data observations:
- Year values: e.g., 4, 6, 7 (may not be full year, could be offset or 2-digit)
- The column header names are simply Y, M, D, H, MIN, SEC

**Timestamp formula** (for reconstruction):
```
timestamp = datetime(Y, M, D, H, MIN, SEC)
```

**Important notes**:
- Do NOT modify the original columns Y, M, D, H, MIN, SEC
- These 6 columns should be used to reconstruct timestamps for analysis
- Year values observed: 4, 6, 7 in sample - may need offset investigation
- Resolution: minute-level (no milliseconds available)
- Date range: not fully inspected across all 24,277 rows
- **No duplicate timestamps expected** if each row represents a unique time step
- **Sampling interval**: cannot determine precisely without investigating row-to-row time differences
- **Milliseconds**: unavailable - only year-month-day-hour-minute-second precision

### Full Variable Summary for JAC IEV40

| Standard Concept | JAC Raw Column | Unit | Direct/Derived | Confidence | Notes |
|-----------------|---------------|------|----------------|------------|-------|
| speed_kmh | SPD | km/h | Direct | High | 0-133 km/h, plausible |
| distance_km | ODO | km | Direct | High | Cumulative odometer |
| battery_voltage_v | VOL | V | Derived (UNVERIFIED) | Medium | 0-379V, likely raw ADC |
| battery_current_a | CUR | A | Direct (raw) | Medium | -40 to 263A, mixed charge/discharge |
| ambient_temperature_c | AIR | — | **Flag** (not temp) | **High** | 0/2 only, sensor status |
| altitude_m | ALT | m | Maybe | Medium | 0-1333.5 m |
| latitude | LAT | deg | Maybe (lon suspicious) | Medium | Lat valid, lon needs investigation |
| longitude | LON | deg | Maybe (lon suspicious) | Medium | Needs modulo 360 check |
| brake_pct | BRK | — | **UNVERIFIED** (not 0-100%) | Low | 0-28, raw sensor |
| accelerator_pct | ACC | — | **UNVERIFIED** (not 0-100%) | Low | 0-90, raw sensor |
| throttle_pct | — | — | **UNVERIFIED** | Low | Same as ACC likely |
| soc_pct | — | — | **NOT AVAILABLE** | Very Low | No SOC column in JAC |
| soh_pct | — | — | **NOT AVAILABLE** | Very Low | No SOH column in JAC |
| eeco_mode | ECO | Binary | Direct (flag) | High | 0 and 192 only |
| automatic_mode | AUT | — | UNVERIFIED | Low | 83 unique values |
| roll_X_g | AX | m/s² (after /192) | Derived | Medium | After scaling |
| roll_Y_g | AY | m/s² (after /192) | Derived | Medium | After scaling |
| roll_Z_g | AZ | m/s² (after /192) | Derived | Medium | After scaling, ~1g when level |
| gyro_X_rad/s | GX | raw | UNVERIFIED | Low | Needs sensor spec |
| gyro_Y_rad/s | GY | raw | UNVERIFIED | Low | Needs sensor spec |
| gyro_Z_rad/s | GZ | raw | UNVERIFIED | Low | Needs sensor spec |
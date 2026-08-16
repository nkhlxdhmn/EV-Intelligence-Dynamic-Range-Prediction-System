# Cross-Dataset Feature Coverage

This document outlines the availability of core ML features across the three datasets (DEVRT, TUM, JAC) to ensure future validation/compatibility.

| Feature Concept | DEVRT (Dacia) | DEVRT (Nissan) | TUM | JAC | ML Compatibility |
|-----------------|---------------|----------------|-----|-----|------------------|
| **SOC** | Yes (Discrete) | Yes (Discrete) | Yes (900) | No reliable proxy | High (DEVRT/TUM) |
| **Speed** | No | Yes | Yes (4) | Yes | Medium (Requires Nissan) |
| **Distance** | Yes | Yes | Yes (1299) | Yes | High |
| **Altitude/Terrain** | Yes | Yes | No | No | Low (DEVRT only) |
| **Ambient Temp** | No | Yes | Yes (15) | No | Medium |
| **Voltage** | No | No | Yes (1200) | Yes | Low |
| **Motor Power** | No | Yes | No (Only Aux 56) | No | Low |
| **Regen Power** | No | Yes | No | No | Low |
| **Battery Capacity** | Yes (33 kWh) | Yes (62 kWh) | Yes (58 kWh) | Yes (40 kWh) | High |

## Conclusion
- **DEVRT** is uniquely positioned to train a model that understands **Terrain (Altitude/Gradient)**, which is crucial for dynamic range prediction.
- **TUM** is excellent for external validation of speed/temperature/SOC relationships, but it entirely lacks terrain context (no altitude or GPS data natively in UDS).
- **JAC** lacks reliable SOC, making it unsuitable for energy consumption ML training at this stage.

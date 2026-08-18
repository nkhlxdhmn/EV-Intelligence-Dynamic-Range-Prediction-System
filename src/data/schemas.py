"""
Schema validation module for the EV Intelligence & Dynamic Range Prediction System.

This module defines the conceptual schema for future processed datasets.
It distinguishes:
- required fields
- optional fields
- derived fields
- target fields

DO NOT force raw datasets into this schema yet.
Use clear Python type definitions or Pydantic models where appropriate.
"""

from typing import Literal, Optional, Dict, List, Any
from pydantic import BaseModel, Field, validator


# ============================================================
# Standard Type Literals
# ============================================================

# Supported data types for schema fields
DataLiteral = Literal["int", "float", "str", "datetime", "bool"]

# Dataset source literals
DatasetLiteral = Literal["DEVRT", "JAC", "TUM", "all"]

# Feature availability status
AvailabilityLiteral = Literal["available", "unverified", "unavailable", "flag"]


# ============================================================
# Core Schema Models
# ============================================================


class SchemaField(BaseModel):
    """Individual schema field definition."""
    
    name: str = Field(..., description="Standard concept name")
    dtype: DataLiteral = Field(..., description="Python data type")
    unit: str = Field(..., description="Unit of measurement")
    required: bool = Field(
        default=False, 
        description="Whether this field is required for modeling"
    )
    derivable_from: List[DatasetLiteral] = Field(
        default=["all"],
        description="Which original datasets can provide this field"
    )
    availability: AvailabilityLiteral = Field(
        default="unverified",
        description="Current availability status across datasets"
    )
    notes: str = Field(
        default="",
        description="Additional notes about derivation or limitations"
    )
    
    @validator("dtype")
    def validate_dtype(cls, v):
        """Validate that dtype is one of the allowed literals."""
        if v not in ["int", "float", "str", "datetime", "bool"]:
            raise ValueError(f"Invalid dtype: {v}. Must be one of: int, float, str, datetime, bool")
        return v
    
    @validator("availability")
    def validate_availability(cls, v):
        """Validate availability literal."""
        if v not in ["available", "unverified", "unavailable", "flag"]:
            raise ValueError(f"Invalid availability: {v}. Must be one of: available, unverified, unavailable, flag")
        return v


class DatasetSchema(BaseModel):
    """Schema for a single dataset."""
    
    dataset_name: DatasetLiteral = Field(..., description="Name of the dataset")
    fields: Dict[str, SchemaField] = Field(
        default_factory=dict,
        description="Mapping of standard concepts to schema fields"
    )
    target_field: Optional[str] = Field(
        default=None,
        description="Name of the primary target field (if any)"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional dataset-specific metadata"
    )
    
    def get_field(self, concept_name: str) -> Optional[SchemaField]:
        """Get a schema field by standard concept name."""
        return self.fields.get(concept_name)
    
    def get_required_fields(self) -> List[str]:
        """Get list of required field names."""
        return [name for name, field in self.fields.items() if field.required]
    
    def get_derivable_datasets(self, concept_name: str) -> List[DatasetLiteral]:
        """Get which datasets can provide a given concept."""
        field = self.get_field(concept_name)
        if field is None:
            return []
        return field.derivable_from


# ============================================================
# Pre-defined Schema Fields
# ============================================================

# Battery fields
BATTERY_FIELDS = {
    "soc_pct": SchemaField(
        name="soc_pct",
        dtype="float",
        unit="%",
        required=True,
        derivable_from=["DEVRT", "TUM"],
        availability="available",
        notes="State of Charge percentage; JAC not available"
    ),
    "soh_pct": SchemaField(
        name="soh_pct",
        dtype="float",
        unit="%",
        required=False,
        derivable_from=["DEVRT"],  # Only DEVRT has SOH
        availability="unavailable",  # JAC/TUM: not in inspected value_ids
        notes="DEVRT: soh column %; TUM/JAC: not in value_overview inspection"
    ),
    "battery_voltage_v": SchemaField(
        name="battery_voltage_v",
        dtype="float",
        unit="V",
        required=False,
        derivable_from=["TUM", "DEVRT"],  # TUM direct, DEVRT indirect
        availability="unverified",  # JAC VOL likely raw ADC
        notes="TUM: value_id=1200 direct; DEVRT: indirect via Motor Pwr; JAC: likely raw ADC 0-379V"
    ),
    "battery_current_a": SchemaField(
        name="battery_current_a",
        dtype="float",
        unit="A",
        required=False,
        derivable_from=["TUM", "DEVRT"],
        availability="unverified",
        notes="TUM: value_id=1205 (PTC1 current, 0-100A); DEVRT: implied; JAC: CUR unverified (-40 to 263A)"
    ),
    "battery_capacity_kwh": SchemaField(
        name="battery_capacity_kwh",
        dtype="float",
        unit="kWh",
        required=True,
        derivable_from=["all"],
        availability="available",
        notes="Known fleet values: Dacia 33kWh, TUM 58kWh, Nissan Leaf 62kWh"
    ),
    "battery_temperature_c": SchemaField(
        name="battery_temperature_c",
        dtype="float",
        unit="°C",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="available",
        notes="DEVRT: amb_temp & Motor Temp; TUM: multiple temp value_ids"
    )
}

# Driving fields
DRIVING_FIELDS = {
    "speed_kmh": SchemaField(
        name="speed_kmh",
        dtype="float",
        unit="km/h",
        required=True,
        derivable_from=["DEVRT", "JAC", "TUM"],
        availability="available",
        notes="All three datasets have speed column"
    ),
    "acceleration_ms2": SchemaField(
        name="acceleration_ms2",
        dtype="float",
        unit="m/s²",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="unverified",
        notes="DEVRT: from speed differences; JAC: accel after /192 scaling; TUM: from speed diff"
    ),
    "distance_km": SchemaField(
        name="distance_km",
        dtype="float",
        unit="km",
        required=True,
        derivable_from=["DEVRT", "JAC", "TUM"],
        availability="available",
        notes="DEVRT: cumul_dist; JAC: ODO; TUM: value_id=1299 traveled_distance"
    ),
    "motor_power_kw": SchemaField(
        name="motor_power_kw",
        dtype="float",
        unit="kW",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="medium",
        notes="DEVRT: Motor Pwr(w)/1000 (Nissan Leaf only); TUM: power signals integration"
    ),
    "brake_intensity": SchemaField(
        name="brake_intensity",
        dtype="float",
        unit="(raw)",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="unverified",
        notes="DEVRT: regenwh sign; JAC: BRK 0-28 raw (not %%); TUM: hv_aux_power sign"
    ),
    "accelerator_position": SchemaField(
        name="accelerator_position",
        dtype="float",
        unit="(raw)",
        required=False,
        derivable_from=["DEVRT"],
        availability="unverified",
        notes="DEVRT: indirect via Aux Pwr; JAC: ACC 0-90 raw (not 0-100%)"
    ),
    "eeco_mode": SchemaField(
        name="eeco_mode",
        dtype="bool",
        unit="binary",
        required=False,
        derivable_from=["JAC"],
        availability="available",
        notes="JAC: ECO = 0 (off) or 192 (on) only"
    )
}

# Terrain fields
TERRAIN_FIELDS = {
    "altitude_m": SchemaField(
        name="altitude_m",
        dtype="float",
        unit="m",
        required=False,
        derivable_from=["DEVRT", "JAC", "TUM"],
        availability="medium",
        notes="DEVRT: altitude+elv_spy; JAC: ALT (ref frame unknown); TUM: in JSON histograms"
    ),
    "gradient_pct": SchemaField(
        name="gradient_pct",
        dtype="float",
        unit="%",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="derivable",
        notes="Δaltitude/Δdistance × 100; requires altitude+distance from same dataset"
    ),
    "uphill_flag": SchemaField(
        name="uphill_flag",
        dtype="int",
        unit="binary",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="derivable",
        notes="1 if gradient_pct > 0 else 0"
    ),
    "downhill_flag": SchemaField(
        name="downhill_flag",
        dtype="int",
        unit="binary",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="derivable",
        notes="1 if gradient_pct < 0 else 0"
    )
}

# Energy fields
ENERGY_FIELDS = {
    "net_consumption_kwh_per_km": SchemaField(
        name="net_consumption_kwh_per_km",
        dtype="float",
        unit="kWh/km",
        required=True,
        derivable_from=["DEVRT", "TUM"],
        availability="available",
        notes="Primary ML target; derivable from SOC×cap/dist; JAC: not available (no SOC)"
    ),
    "energy_consumed_kwh": SchemaField(
        name="energy_consumed_kwh",
        dtype="float",
        unit="kWh",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="available",
        notes="abs((soc_start - soc_end) × capacity_kwh / 100)"
    ),
    "regen_energy_kwh": SchemaField(
        name="regen_energy_kwh",
        dtype="float",
        unit="kWh",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="available",
        notes="DEVRT: Σ(regenwh×time)/3600; TUM: Σ(negative_hv_aux_power×interval)/3600"
    ),
    "gross_energy_consumption_kwh": SchemaField(
        name="gross_energy_consumption_kwh",
        dtype="float",
        unit="kWh",
        required=False,
        derivable_from=["TUM"],
        availability="planned",
        notes="Σ(abs(power_w)×interval_s)/3600; total energy throughput"
    )
}

# Environment fields
ENVIRONMENT_FIELDS = {
    "ambient_temperature_c": SchemaField(
        name="ambient_temperature_c",
        dtype="float",
        unit="°C",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="available",
        notes="DEVRT: amb_temp °C; TUM: value_id=15; JAC: AIR is sensor FLAG not temperature"
    ),
    "humidity_pct": SchemaField(
        name="humidity_pct",
        dtype="float",
        unit="%",
        required=False,
        derivable_from=[],
        availability="unavailable",
        notes="NOT available in any of the 3 datasets"
    ),
    "wind_speed_kmh": SchemaField(
        name="wind_speed_kmh",
        dtype="float",
        unit="km/h",
        required=False,
        derivable_from=["DEVRT"],
        availability="available",
        notes="DEVRT: wind_kph/mph convertible; JAC: not available; TUM: not in 29 value_ids"
    )
}

# Vehicle fields
VEHICLE_FIELDS = {
    "vehicle_model": SchemaField(
        name="vehicle_model",
        dtype="str",
        unit="—",
        required=True,
        derivable_from=["all"],
        availability="available",
        notes="DEVRT: Dacia Spring/Nissan Leaf; JAC: IEV40 implied; TUM: VW ID.3/CUPRA Born"
    ),
    "battery_configuration": SchemaField(
        name="battery_configuration",
        dtype="str",
        unit="—",
        required=False,
        derivable_from=["DEVRT", "TUM"],
        availability="available",
        notes="DEVRT: 33kWh/62kWh; TUM: 108s2p (58kWh); JAC: not explicit"
    )
}


# ============================================================
# Pre-defined Dataset Schemas
# ============================================================

# DEVRT Dataset Schema
devrt_schema = DatasetSchema(
    dataset_name="DEVRT",
    fields={
        **BATTERY_FIELDS,
        **DRIVING_FIELDS,
        **TERRAIN_FIELDS,
        **ENERGY_FIELDS,
        **ENVIRONMENT_FIELDS,
        **VEHICLE_FIELDS,
    },
    target_field="net_consumption_kwh_per_km",
    metadata={
        "trips": 28,
        "vehicles": 2 (Dacia Spring, Nissan Leaf),
        "capacities_wh": {"Dacia Spring": 33000, "Nissan Leaf": 62000},
        "note": "SOC and SOH available; regenwh in Nissan Leaf files only"
    }
)

# JAC IEV40 Dataset Schema
jac_schema = DatasetSchema(
    dataset_name="JAC",
    fields={
        **{k: v for k, v in BATTERY_FIELDS.items() if k in [
            "soc_pct", "battery_voltage_v", "battery_current_a", "battery_capacity_kwh"
        ]},
        **{k: v for k, v in DRIVING_FIELDS.items() if k in [
            "speed_kmh", "distance_km", "eeco_mode"
        ]},
        **{k: v for k, v in TERRAIN_FIELDS.items() if k in ["altitude_m", "gradient_pct"]},
        **{k: v for k, v in ENVIRONMENT_FIELDS.items() if k in ["ambient_temperature_c"]},
        **{k: v for k, v in VEHICLE_FIELDS.items()},
    },
    target_field=None,  # JAC cannot produce the primary target (no SOC)
    metadata={
        "vehicles": 1,  # Single IEV40 vehicle
        "notes": "SOH and SOC not available; AIR is sensor flag not temperature; VOL likely raw ADC;
                  ACC/BRK raw values not percentages"
    }
)

# TUM EV UDS Dataset Schema
tum_schema = DatasetSchema(
    dataset_name="TUM",
    fields={
        **BATTERY_FIELDS,
        **DRIVING_FIELDS,
        **TERRAIN_FIELDS,
        **ENERGY_FIELDS,
        **ENVIRONMENT_FIELDS,
        **VEHICLE_FIELDS,
    },
    target_field="net_consumption_kwh_per_km",
    metadata={
        "fleet": 7 vehicles (2 VW ID.3 Pro Performance, 5 CUPRA Born),
        "battery_capacity_kwh": 58,  # Nominal net capacity
        "sampling_intervals_ms": [200, 500, 1000, 10000],  # Variable by signal
        "note": "SOC available (value_id=900); DOD available (value_id=1290, =100-SOC); "
                "UDS data collected via OBD-II; JSON histograms are processed (not raw trip data); "
                "parquet files contain raw UDS measurements"
    }
)


# ============================================================
# Schema Utility Functions
# ============================================================


def get_schema(dataset_name: DatasetLiteral) -> DatasetSchema:
    """
    Get the schema for a given dataset.
    
    Args:
        dataset_name: Name of the dataset (DEVRT, JAC, TUM)
        
    Returns:
        DatasetSchema object with the configuration
    """
    schemas: Dict[DatasetLiteral, DatasetSchema] = {
        "DEVRT": devrt_schema,
        "JAC": jac_schema,
        "TUM": tum_schema,
    }
    return schemas.get(dataset_name, DatasetSchema(dataset_name=dataset_name))


def check_field_availability(
    schema: DatasetSchema,
    concept_name: str,
    dataset: DatasetLiteral
) -> bool:
    """
    Check if a concept is available in a given dataset.
    
    Args:
        schema: The dataset schema
        concept_name: The standard concept to check
        dataset: The dataset to check availability in
        
    Returns:
        True if the concept is available (or derivable) in the dataset
    """
    field = schema.get_field(concept_name)
    if field is None:
        return False
    
    # Check if dataset is in derivable_from
    derivable = field.derivable_from
    if "all" in derivable:
        return True
    return dataset in derivable


def check_target_availability(schema: DatasetSchema) -> bool:
    """
    Check if the primary target is available in the dataset.
    
    Returns:
        True if the target can be derived from this dataset
    """
    if schema.target_field is None:
        return False
    
    target_name = schema.target_field
    field = schema.get_field(target_name)
    if field is None:
        return False
    
    # Check if target is derivable from this dataset
    return field.availability in ["available", "derivable"]


# ============================================================
# Validation Functions
# ============================================================


def validate_schema_consistency(schemas: Dict[DatasetLiteral, DatasetSchema]) -> List[str]:
    """
    Validate consistency across dataset schemas.
    
    Returns:
        List of consistency issues found
    """
    issues = []
    
    # Check that target is defined for datasets that should have one
    for name, schema in schemas.items():
        if schema.target_field is None:
            issues.append(f"{name}: No target field defined")
        else:
            # Check target is marked as required
            target_field = schema.get_field(schema.target_field)
            if target_field and not target_field.required:
                issues.append(f"{name}: Target '{schema.target_field}' not marked as required")
    
    # Check that SOC is available where target is defined (for SOC×cap/dist derivation)
    for name, schema in schemas.items():
        if schema.target_field == "net_consumption_kwh_per_km":
            soc_field = schema.get_field("soc_pct")
            if soc_field and soc_field.availability in ["unavailable", "very low"]:
                issues.append(
                    f"{name}: Target defined but SOC not available ({soc_field.availability})"
                )
    
    # Check for conflicting availability declarations
    for concept in ["soc_pct", "battery_voltage_v", "ambient_temperature_c"]:
        datasets_with_concept = []
        for name, schema in schemas.items():
            field = schema.get_field(concept)
            if field:
                datasets_with_concept.append(f"{name}:{field.availability}")
        if datasets_with_concept:
            issues.append(f"{concept} availability: {', '.join(datasets_with_concept)}")
    
    return issues


# ============================================================
# Example Usage
# ============================================================

if __name__ == "__main__":
    # Example: Get TUM schema and check target availability
    tum_schema = get_schema("TUM")
    
    print("=== TUM Schema ===")
    print(f"Target field: {tum_schema.target_field}")
    print(f"Target availability: {tum_schema.get_field(tum_schema.target_field).availability}")
    print(f"SOC availability: {tum_schema.get_field('soc_pct').availability}")
    print(f"Can derive target: {check_target_availability(tum_schema)}")
    print()
    
    # Example: Check JAC target availability
    jac_schema = get_schema("JAC")
    print("=== JAC Schema ===")
    print(f"Target field: {jac_schema.target_field}")
    print(f"Can derive target: {check_target_availability(jac_schema)}")
    print(f"SOC availability: {jac_schema.get_field('soc_pct').availability}")
    print()
    
    # Example: Validate schema consistency
    print("=== Schema Consistency Validation ===")
    issues = validate_schema_consistency({"DEVRT": devrt_schema, "JAC": jac_schema, "TUM": tum_schema})
    for issue in issues:
        print(f"  - {issue}")
    if not issues:
        print("  No issues found")
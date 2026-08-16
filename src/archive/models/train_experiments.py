"""
STEP 8D: Feature Experiments Design & Multi-Model Training

5 controlled experiments across 3 model types (Ridge, Random Forest, XGBoost)
with baseline comparison and comprehensive evaluation on validation set.

CRITICAL: Test set is NOT used for model selection.
Validation set used for model comparison and architecture selection.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
import joblib
import json
from typing import Dict, Tuple, List
import warnings

warnings.filterwarnings('ignore')

# Random seed for reproducibility
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)


def get_feature_experiments() -> Dict[str, Dict]:
    """
    Define 5 feature experiments.
    
    Experiments:
    - A_BASIC: Battery + Terrain features
    - B_DRIVING: A + Driving dynamics
    - C_POWERTRAIN: B + Motor/powertrain features
    - D_ENVIRONMENT: C + Environmental factors
    - E_FULL: All available features (excluding metadata)
    """
    
    # Base available features (non-metadata)
    all_features = [
        'vehicle_model', 'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',
        'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',
        'terrain_class', 'elevation_gain_100m', 'elevation_gain_500m', 'elevation_gain_1km',
        'elevation_loss_100m', 'elevation_loss_500m', 'elevation_loss_1km',
        'net_elevation_change_1km', 'mean_gradient_500m', 'mean_gradient_1km',
        'gradient_std_500m', 'gradient_std_1km', 'max_uphill_gradient', 'max_downhill_gradient',
        'current_speed_kmh', 'mean_speed_500m', 'mean_speed_1km', 'speed_variance_500m',
        'speed_variance_1km', 'mean_acceleration_500m', 'acceleration_variance_500m',
        'motor_power_kw_available', 'motor_torque_nm_available', 'regen_energy_joules_available',
        'motor_power_kw_current', 'motor_torque_nm_current', 'regen_active',
        'temperature_c', 'wind_speed_kmh', 'wind_direction_deg', 'precipitation_mm',
        'is_day', 'traffic_intensity_score', 'road_type_encoded'
    ]
    
    experiments = {
        'A_BASIC': {
            'name': 'Basic: Battery + Terrain',
            'description': 'Foundational features for energy consumption prediction',
            'features': [
                'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',  # Battery
                'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',  # Terrain base
                'terrain_class', 'elevation_gain_1km', 'elevation_loss_1km'  # Terrain aggregated
            ]
        },
        'B_DRIVING': {
            'name': 'Driving: A + Speed/Acceleration',
            'description': 'Add driving dynamics to predict energy from driver behavior',
            'features': [
                # From A_BASIC
                'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',
                'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',
                'terrain_class', 'elevation_gain_1km', 'elevation_loss_1km',
                # Driving dynamics
                'current_speed_kmh', 'mean_speed_500m', 'mean_speed_1km',
                'speed_variance_500m', 'speed_variance_1km',
                'mean_acceleration_500m', 'acceleration_variance_500m'
            ]
        },
        'C_POWERTRAIN': {
            'name': 'Powertrain: B + Motor/Regen',
            'description': 'Add powertrain telemetry for electromechanical insights',
            'features': [
                # From B_DRIVING
                'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',
                'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',
                'terrain_class', 'elevation_gain_1km', 'elevation_loss_1km',
                'current_speed_kmh', 'mean_speed_500m', 'mean_speed_1km',
                'speed_variance_500m', 'speed_variance_1km',
                'mean_acceleration_500m', 'acceleration_variance_500m',
                # Powertrain (marked as _available for missing data handling)
                'motor_power_kw_available', 'motor_torque_nm_available',
                'regen_energy_joules_available', 'regen_active'
            ]
        },
        'D_ENVIRONMENT': {
            'name': 'Environment: C + Weather/External',
            'description': 'Add environmental factors affecting energy consumption',
            'features': [
                # From C_POWERTRAIN
                'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',
                'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',
                'terrain_class', 'elevation_gain_1km', 'elevation_loss_1km',
                'current_speed_kmh', 'mean_speed_500m', 'mean_speed_1km',
                'speed_variance_500m', 'speed_variance_1km',
                'mean_acceleration_500m', 'acceleration_variance_500m',
                'motor_power_kw_available', 'motor_torque_nm_available',
                'regen_energy_joules_available', 'regen_active',
                # Environment (conditional - may have nulls)
                'temperature_c', 'wind_speed_kmh', 'precipitation_mm',
                'is_day', 'traffic_intensity_score'
            ]
        },
        'E_FULL': {
            'name': 'Full: All Available Features',
            'description': 'Maximum feature set for highest predictive capacity',
            'features': [
                # Everything except metadata (trip_id, vehicle_id, timestamp, vehicle_model)
                'current_soc_pct', 'current_soh_pct', 'battery_capacity_kwh',
                'current_altitude_m', 'current_gradient_pct', 'past_1km_gradient_pct',
                'terrain_class', 'elevation_gain_100m', 'elevation_gain_500m',
                'elevation_gain_1km', 'elevation_loss_100m', 'elevation_loss_500m',
                'elevation_loss_1km', 'net_elevation_change_1km', 'mean_gradient_500m',
                'mean_gradient_1km', 'gradient_std_500m', 'gradient_std_1km',
                'max_uphill_gradient', 'max_downhill_gradient',
                'current_speed_kmh', 'mean_speed_500m', 'mean_speed_1km',
                'speed_variance_500m', 'speed_variance_1km',
                'mean_acceleration_500m', 'acceleration_variance_500m',
                'motor_power_kw_available', 'motor_torque_nm_available',
                'regen_energy_joules_available', 'motor_power_kw_current',
                'motor_torque_nm_current', 'regen_active',
                'temperature_c', 'wind_speed_kmh', 'wind_direction_deg',
                'precipitation_mm', 'is_day', 'traffic_intensity_score',
                'road_type_encoded'
            ]
        }
    }
    
    return experiments


def prepare_data(
    train_file: str,
    val_file: str,
    features: List[str]
) -> Tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray]:
    """
    Load and prepare data for training.
    Remove rows with ANY missing feature values.
    """
    
    train_df = pd.read_parquet(train_file)
    val_df = pd.read_parquet(val_file)
    
    # Select features + target
    feature_cols = [f for f in features if f in train_df.columns]
    target_col = 'target_future_energy_kwh_per_km'
    
    # Train set
    train_full = train_df[feature_cols + [target_col]].copy()
    train_clean = train_full.dropna()
    
    # Validation set
    val_full = val_df[feature_cols + [target_col]].copy()
    val_clean = val_full.dropna()
    
    X_train = train_clean[feature_cols]
    y_train = train_clean[target_col].values
    
    X_val = val_clean[feature_cols]
    y_val = val_clean[target_col].values
    
    return X_train, X_val, y_train, y_val


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict:
    """Calculate comprehensive evaluation metrics."""
    
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    
    # SMAPE (Symmetric Mean Absolute Percentage Error)
    denominator = (np.abs(y_true) + np.abs(y_pred)) / 2
    # Avoid division by zero
    smape = np.mean(np.abs(y_pred - y_true) / np.maximum(denominator, 1e-10)) * 100
    
    return {
        'MAE': mae,
        'RMSE': rmse,
        'R2': r2,
        'SMAPE': smape
    }


def train_ridge_model(X_train: pd.DataFrame, y_train: np.ndarray) -> Pipeline:
    """Train Ridge regression with preprocessing."""
    
    # Identify categorical columns (object dtype)
    categorical_cols = X_train.select_dtypes(include='object').columns.tolist()
    numeric_cols = X_train.select_dtypes(include=[np.number]).columns.tolist()
    
    # Preprocessing pipeline
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_cols),
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_cols)
        ],
        remainder='passthrough'
    )
    
    # Ridge model
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('model', Ridge(alpha=1.0, random_state=RANDOM_SEED))
    ])
    
    pipeline.fit(X_train, y_train)
    
    return pipeline


def train_random_forest(X_train: pd.DataFrame, y_train: np.ndarray) -> RandomForestRegressor:
    """Train Random Forest with conservative settings."""
    
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=RANDOM_SEED,
        n_jobs=-1,
        verbose=0
    )
    
    # Encode categorical features
    X_encoded = X_train.copy()
    for col in X_encoded.select_dtypes(include='object').columns:
        X_encoded[col] = pd.Categorical(X_encoded[col]).codes
    
    model.fit(X_encoded, y_train)
    
    # Store encoder info for prediction
    model._categorical_cols = X_train.select_dtypes(include='object').columns.tolist()
    model._feature_names = X_train.columns.tolist()
    
    return model


def train_xgboost_model(X_train: pd.DataFrame, y_train: np.ndarray) -> xgb.XGBRegressor:
    """Train XGBoost with conservative settings."""
    
    if not HAS_XGBOOST:
        raise ImportError("XGBoost not installed. Install with: pip install xgboost")
    
    model = xgb.XGBRegressor(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RANDOM_SEED,
        tree_method='hist',
        device='cpu'
    )
    
    # Encode categorical features
    X_encoded = X_train.copy()
    for col in X_encoded.select_dtypes(include='object').columns:
        X_encoded[col] = pd.Categorical(X_encoded[col]).codes
    
    model.fit(X_encoded, y_train)
    
    # Store encoder info
    model._categorical_cols = X_train.select_dtypes(include='object').columns.tolist()
    model._feature_names = X_train.columns.tolist()
    
    return model


def predict_with_model(model, X_data: pd.DataFrame) -> np.ndarray:
    """Make predictions, handling categorical encoding."""
    
    if isinstance(model, Pipeline):
        return model.predict(X_data)
    
    # For tree-based models, need to encode categoricals
    X_encoded = X_data.copy()
    for col in X_encoded.select_dtypes(include='object').columns:
        X_encoded[col] = pd.Categorical(X_encoded[col]).codes
    
    return model.predict(X_encoded)


def main():
    """Run STEP 8D experiments."""
    
    project_root = Path(__file__).parent.parent.parent
    
    train_file = str(project_root / 'data' / 'processed' / 'v2_train.parquet')
    val_file = str(project_root / 'data' / 'processed' / 'v2_validation.parquet')
    output_dir = project_root / 'models' / 'step8'
    reports_dir = project_root / 'reports'
    
    # Create output directories
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print("STEP 8D: FEATURE EXPERIMENTS & MODEL TRAINING")
    print("="*70)
    
    # Get experiments
    experiments = get_feature_experiments()
    
    # Results storage
    all_results = []
    model_artifacts = {}
    
    print(f"\nExperiments: {len(experiments)}")
    print(f"Models: Ridge, Random Forest, XGBoost")
    print(f"Model architectures: {3}")
    print(f"Total combinations: {len(experiments) * 3}\n")
    
    # Train models
    for exp_id, (exp_name, exp_config) in enumerate(experiments.items(), 1):
        print(f"\n{'='*70}")
        print(f"EXPERIMENT {exp_id}/5: {exp_name}")
        print(f"Description: {exp_config['description']}")
        print(f"Features: {len(exp_config['features'])}")
        print(f"{'='*70}")
        
        # Prepare data
        try:
            X_train, X_val, y_train, y_val = prepare_data(
                train_file, val_file, exp_config['features']
            )
        except Exception as e:
            print(f"ERROR preparing data: {e}")
            continue
        
        print(f"Train: {X_train.shape[0]:,} samples, {X_train.shape[1]} features")
        print(f"Val:   {X_val.shape[0]:,} samples")
        
        # Train models
        model_results = {}
        
        # Ridge
        print(f"\n  [1/3] Ridge Regression...")
        try:
            ridge_model = train_ridge_model(X_train, y_train)
            ridge_pred = ridge_model.predict(X_val)
            ridge_metrics = calculate_metrics(y_val, ridge_pred)
            
            model_results['Ridge'] = ridge_metrics
            model_artifacts[f'{exp_name}_Ridge'] = ridge_model
            
            print(f"    MAE: {ridge_metrics['MAE']:.6f}, RMSE: {ridge_metrics['RMSE']:.6f}, R²: {ridge_metrics['R2']:.6f}")
        except Exception as e:
            print(f"    ERROR: {e}")
        
        # Random Forest
        print(f"  [2/3] Random Forest...")
        try:
            rf_model = train_random_forest(X_train, y_train)
            rf_pred = predict_with_model(rf_model, X_val)
            rf_metrics = calculate_metrics(y_val, rf_pred)
            
            model_results['RandomForest'] = rf_metrics
            model_artifacts[f'{exp_name}_RF'] = rf_model
            
            print(f"    MAE: {rf_metrics['MAE']:.6f}, RMSE: {rf_metrics['RMSE']:.6f}, R²: {rf_metrics['R2']:.6f}")
        except Exception as e:
            print(f"    ERROR: {e}")
        
        # XGBoost
        print(f"  [3/3] XGBoost...")
        try:
            xgb_model = train_xgboost_model(X_train, y_train)
            xgb_pred = predict_with_model(xgb_model, X_val)
            xgb_metrics = calculate_metrics(y_val, xgb_pred)
            
            model_results['XGBoost'] = xgb_metrics
            model_artifacts[f'{exp_name}_XGB'] = xgb_model
            
            print(f"    MAE: {xgb_metrics['MAE']:.6f}, RMSE: {xgb_metrics['RMSE']:.6f}, R²: {xgb_metrics['R2']:.6f}")
        except Exception as e:
            print(f"    ERROR: {e}")
        
        # Store results
        for model_name, metrics in model_results.items():
            all_results.append({
                'Experiment': exp_name,
                'Model': model_name,
                'Samples': X_train.shape[0],
                'Features': X_train.shape[1],
                'MAE': metrics['MAE'],
                'RMSE': metrics['RMSE'],
                'R2': metrics['R2'],
                'SMAPE': metrics['SMAPE']
            })
    
    # Save results
    print(f"\n{'='*70}")
    print("SAVING RESULTS")
    print(f"{'='*70}")
    
    results_df = pd.DataFrame(all_results)
    results_file = reports_dir / 'model_comparison_validation.csv'
    results_df.to_csv(results_file, index=False)
    print(f"✓ Results: {results_file}")
    
    # Save models
    for model_name, model in model_artifacts.items():
        model_file = output_dir / f'{model_name}.joblib'
        joblib.dump(model, model_file)
    print(f"✓ Models: {len(model_artifacts)} saved to {output_dir}")
    
    # Display summary
    print(f"\n{'='*70}")
    print("VALIDATION RESULTS SUMMARY")
    print(f"{'='*70}")
    print("\nBest MAE by Experiment:")
    for exp_name in experiments.keys():
        exp_results = results_df[results_df['Experiment'] == exp_name]
        best = exp_results.loc[exp_results['MAE'].idxmin()]
        print(f"  {exp_name}: {best['Model']} (MAE={best['MAE']:.6f})")
    
    print("\nBest Model Overall:")
    best_overall = results_df.loc[results_df['MAE'].idxmin()]
    print(f"  {best_overall['Experiment']} + {best_overall['Model']}")
    print(f"  MAE: {best_overall['MAE']:.6f}, RMSE: {best_overall['RMSE']:.6f}, R²: {best_overall['R2']:.6f}")
    
    print(f"\n✓ STEP 8D COMPLETE")
    
    return results_df


if __name__ == '__main__':
    results_df = main()

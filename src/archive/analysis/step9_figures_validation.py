"""
STEP 9: Generate validation-side diagnostic figures (9D, 9E, 9F, 9K).
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'processed'
REPORTS_DIR = PROJECT_ROOT / 'reports'
FIGURES_DIR = REPORTS_DIR / 'figures' / 'step9'

FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Load validation predictions
pred_df = pd.read_parquet(DATA_DIR / 'validation_predictions_step9.parquet')

# ---------------------------------------------------------------
# 9D - Error distribution + residual distribution
# ---------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

axes[0].hist(pred_df['absolute_error'], bins=40, edgecolor='black', alpha=0.8)
axes[0].set_xlabel('Absolute Error (kWh/km)')
axes[0].set_ylabel('Count')
axes[0].set_title('Validation Absolute Error Distribution')
axes[0].axvline(pred_df['absolute_error'].mean(), color='red', linestyle='--',
                label=f'Mean={pred_df["absolute_error"].mean():.4f}')

axes[1].hist(pred_df['signed_error'], bins=40, edgecolor='black', alpha=0.8)
axes[1].set_xlabel('Signed Error (pred - actual) (kWh/km)')
axes[1].set_ylabel('Count')
axes[1].set_title('Validation Residual Distribution')
axes[1].axvline(0, color='black', linestyle='-', linewidth=0.8)
axes[1].axvline(pred_df['signed_error'].mean(), color='red', linestyle='--',
                label=f'Mean={pred_df["signed_error"].mean():.4f}')

plt.tight_layout()
plt.savefig(FIGURES_DIR / 'error_distribution.png', dpi=150)
plt.close()

fig, ax = plt.subplots(figsize=(8, 5))
ax.hist(pred_df['signed_error'], bins=50, edgecolor='black', alpha=0.8)
ax.set_xlabel('Signed Error (kWh/km)')
ax.set_ylabel('Count')
ax.set_title('Validation Residual Distribution')
ax.axvline(0, color='black', linestyle='-', linewidth=0.8)
ax.axvline(pred_df['signed_error'].mean(), color='red', linestyle='--',
           label=f'Mean={pred_df["signed_error"].mean():.4f}')
ax.legend()
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'residual_distribution.png', dpi=150)
plt.close()
print('Saved: error_distribution.png, residual_distribution.png')

# ---------------------------------------------------------------
# 9E - Error by vehicle
# ---------------------------------------------------------------
vehicle_err = pd.read_csv(REPORTS_DIR / 'error_by_vehicle.csv')
fig, ax = plt.subplots(figsize=(8, 5))
x = np.arange(len(vehicle_err))
width = 0.35
ax.bar(x - width/2, vehicle_err['MAE'], width, label='MAE')
ax.bar(x + width/2, vehicle_err['RMSE'], width, label='RMSE')
ax.set_xticks(x)
ax.set_xticklabels(vehicle_err['vehicle'])
ax.set_ylabel('Error (kWh/km)')
ax.set_title('Validation Error by Vehicle')
ax.legend()
for i, row in vehicle_err.iterrows():
    ax.text(i - width/2, row['MAE'] + 0.002, f'{row["MAE"]:.4f}', ha='center', fontsize=8)
    ax.text(i + width/2, row['RMSE'] + 0.002, f'{row["RMSE"]:.4f}', ha='center', fontsize=8)
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'error_by_vehicle.png', dpi=150)
plt.close()
print('Saved: error_by_vehicle.png')

# ---------------------------------------------------------------
# 9F - Error by terrain
# ---------------------------------------------------------------
terrain_err = pd.read_csv(REPORTS_DIR / 'error_by_terrain.csv')
fig, ax = plt.subplots(figsize=(8, 5))
x = np.arange(len(terrain_err))
width = 0.35
ax.bar(x - width/2, terrain_err['MAE'], width, label='MAE')
ax.bar(x + width/2, terrain_err['RMSE'], width, label='RMSE')
ax.set_xticks(x)
ax.set_xticklabels(terrain_err['terrain'])
ax.set_ylabel('Error (kWh/km)')
ax.set_title('Validation Error by Terrain')
ax.legend()
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'error_by_terrain.png', dpi=150)
plt.close()
print('Saved: error_by_terrain.png')

# ---------------------------------------------------------------
# 9K - Feature importance figures
# ---------------------------------------------------------------
imp_df = pd.read_csv(REPORTS_DIR / 'step9_feature_importance.csv')

fig, ax = plt.subplots(figsize=(9, 6))
ax.barh(imp_df['feature'][::-1], imp_df['xgboost_importance'][::-1], color='steelblue')
ax.set_xlabel('XGBoost Importance (gain)')
ax.set_title('XGBoost Feature Importance (predictive importance)')
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'xgboost_feature_importance.png', dpi=150)
plt.close()

fig, ax = plt.subplots(figsize=(9, 6))
ax.barh(imp_df['feature'][::-1], imp_df['random_forest_importance'][::-1], color='seagreen')
ax.set_xlabel('Random Forest Importance')
ax.set_title('Random Forest Feature Importance (predictive importance)')
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'random_forest_feature_importance.png', dpi=150)
plt.close()
print('Saved: xgboost_feature_importance.png, random_forest_feature_importance.png')

print('\nAll validation-side figures generated.')
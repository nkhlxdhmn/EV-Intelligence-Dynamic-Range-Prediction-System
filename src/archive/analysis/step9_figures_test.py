"""
STEP 9V: Final test visualizations.
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

test_pred = pd.read_parquet(DATA_DIR / 'test_predictions_final.parquet')

# ---------------------------------------------------------------
# Final actual vs predicted
# ---------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 8))
ax.scatter(test_pred['actual_target'], test_pred['predicted_target'],
           alpha=0.4, s=15, edgecolor='none')
lims = [min(test_pred['actual_target'].min(), test_pred['predicted_target'].min()),
        max(test_pred['actual_target'].max(), test_pred['predicted_target'].max())]
ax.plot(lims, lims, 'r--', linewidth=1.5, label='Perfect prediction')
ax.set_xlabel('Actual Target (kWh/km)')
ax.set_ylabel('Predicted Target (kWh/km)')
ax.set_title('Final Test: Actual vs Predicted (Frozen A_BASIC + XGBoost)')
ax.legend()
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'final_actual_vs_predicted.png', dpi=150)
plt.close()
print('Saved: final_actual_vs_predicted.png')

# ---------------------------------------------------------------
# Final residuals
# ---------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 5))
ax.hist(test_pred['signed_error'], bins=50, edgecolor='black', alpha=0.8)
ax.set_xlabel('Signed Error (pred - actual) (kWh/km)')
ax.set_ylabel('Count')
ax.set_title('Final Test Residual Distribution')
ax.axvline(0, color='black', linestyle='-', linewidth=0.8)
ax.axvline(test_pred['signed_error'].mean(), color='red', linestyle='--',
           label=f'Mean={test_pred["signed_error"].mean():.4f}')
ax.legend()
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'final_residuals.png', dpi=150)
plt.close()
print('Saved: final_residuals.png')

# ---------------------------------------------------------------
# Final error by vehicle
# ---------------------------------------------------------------
by_vehicle = pd.read_csv(REPORTS_DIR / 'final_test_by_vehicle.csv')
fig, ax = plt.subplots(figsize=(8, 5))
x = np.arange(len(by_vehicle))
width = 0.35
ax.bar(x - width/2, by_vehicle['MAE'], width, label='MAE')
ax.bar(x + width/2, by_vehicle['RMSE'], width, label='RMSE')
ax.set_xticks(x)
ax.set_xticklabels(by_vehicle['vehicle'])
ax.set_ylabel('Error (kWh/km)')
ax.set_title('Final Test Error by Vehicle')
ax.legend()
for i, row in by_vehicle.iterrows():
    ax.text(i - width/2, row['MAE'] + 0.001, f'{row["MAE"]:.4f}', ha='center', fontsize=8)
    ax.text(i + width/2, row['RMSE'] + 0.001, f'{row["RMSE"]:.4f}', ha='center', fontsize=8)
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'final_error_by_vehicle.png', dpi=150)
plt.close()
print('Saved: final_error_by_vehicle.png')

# ---------------------------------------------------------------
# Final error by terrain
# ---------------------------------------------------------------
by_terrain = pd.read_csv(REPORTS_DIR / 'final_test_by_terrain.csv')
fig, ax = plt.subplots(figsize=(8, 5))
x = np.arange(len(by_terrain))
width = 0.35
ax.bar(x - width/2, by_terrain['MAE'], width, label='MAE')
ax.bar(x + width/2, by_terrain['RMSE'], width, label='RMSE')
ax.set_xticks(x)
ax.set_xticklabels(by_terrain['terrain'])
ax.set_ylabel('Error (kWh/km)')
ax.set_title('Final Test Error by Terrain')
ax.legend()
plt.tight_layout()
plt.savefig(FIGURES_DIR / 'final_error_by_terrain.png', dpi=150)
plt.close()
print('Saved: final_error_by_terrain.png')

print('\nAll final test figures generated.')
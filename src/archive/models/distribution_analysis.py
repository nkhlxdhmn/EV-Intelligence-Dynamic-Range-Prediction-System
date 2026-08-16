"""
Target distribution analysis and vehicle distribution summary.

Creates:
1. Target statistics for each split
2. Vehicle distribution table
3. Visualization of target distributions
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path


def calculate_target_stats(split_data: pd.DataFrame) -> dict:
    """Calculate comprehensive target statistics."""
    target = split_data['target_future_energy_kwh_per_km']
    
    return {
        'count': len(target),
        'mean': target.mean(),
        'median': target.median(),
        'std': target.std(),
        'min': target.min(),
        'max': target.max(),
        'P1': target.quantile(0.01),
        'P5': target.quantile(0.05),
        'P25': target.quantile(0.25),
        'P75': target.quantile(0.75),
        'P95': target.quantile(0.95),
        'P99': target.quantile(0.99),
    }


def create_distribution_analysis(
    train_file: str,
    val_file: str,
    test_file: str,
    output_csv: str = None,
    output_plot: str = None
) -> pd.DataFrame:
    """
    Create target distribution analysis and visualize.
    
    Returns:
    --------
    DataFrame with statistics for all splits.
    """
    
    # Load splits
    train = pd.read_parquet(train_file)
    val = pd.read_parquet(val_file)
    test = pd.read_parquet(test_file)
    
    # Calculate statistics
    splits = {
        'Train': train,
        'Validation': val,
        'Test': test
    }
    
    stats_rows = []
    for split_name, split_data in splits.items():
        stats = calculate_target_stats(split_data)
        stats['split'] = split_name
        stats_rows.append(stats)
    
    stats_df = pd.DataFrame(stats_rows)
    
    # Reorder columns
    cols = ['split', 'count', 'mean', 'median', 'std', 'min', 'max', 
            'P1', 'P5', 'P25', 'P75', 'P95', 'P99']
    stats_df = stats_df[cols]
    
    # Save CSV
    if output_csv:
        print(f"Saving target statistics to {output_csv}...")
        stats_df.to_csv(output_csv, index=False)
    
    # Create visualization
    if output_plot:
        print(f"Creating visualization at {output_plot}...")
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Target Distribution Across Splits', fontsize=16, fontweight='bold')
        
        # Histogram with KDE
        ax = axes[0, 0]
        for split_name, split_data in splits.items():
            target = split_data['target_future_energy_kwh_per_km']
            ax.hist(target, bins=50, alpha=0.5, label=split_name, density=True)
        ax.set_xlabel('Target (kWh/km)')
        ax.set_ylabel('Density')
        ax.set_title('Distribution Histogram')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Box plot
        ax = axes[0, 1]
        data_for_box = []
        labels_for_box = []
        for split_name, split_data in splits.items():
            data_for_box.append(split_data['target_future_energy_kwh_per_km'].values)
            labels_for_box.append(split_name)
        
        bp = ax.boxplot(data_for_box, patch_artist=True)
        ax.set_xticklabels(labels_for_box)
        for patch in bp['boxes']:
            patch.set_facecolor('lightblue')
        ax.set_ylabel('Target (kWh/km)')
        ax.set_title('Box Plot Comparison')
        ax.grid(True, alpha=0.3, axis='y')
        
        # KDE plot
        ax = axes[1, 0]
        for split_name, split_data in splits.items():
            target = split_data['target_future_energy_kwh_per_km']
            target.plot(kind='density', ax=ax, label=split_name, linewidth=2)
        ax.set_xlabel('Target (kWh/km)')
        ax.set_title('Kernel Density Estimate')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Statistics table
        ax = axes[1, 1]
        ax.axis('tight')
        ax.axis('off')
        
        table_data = []
        table_data.append(['Split', 'Mean', 'Std', 'Min', 'Max'])
        for _, row in stats_df.iterrows():
            table_data.append([
                row['split'],
                f"{row['mean']:.4f}",
                f"{row['std']:.4f}",
                f"{row['min']:.4f}",
                f"{row['max']:.4f}"
            ])
        
        table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                        colWidths=[0.2, 0.2, 0.2, 0.2, 0.2])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)
        
        # Style header row
        for i in range(5):
            table[(0, i)].set_facecolor('#40466e')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        ax.set_title('Summary Statistics', pad=20)
        
        plt.tight_layout()
        plt.savefig(output_plot, dpi=300, bbox_inches='tight')
        print(f"✓ Saved plot to {output_plot}")
        plt.close()
    
    return stats_df


def create_vehicle_distribution(
    train_file: str,
    val_file: str,
    test_file: str,
    output_csv: str = None
) -> pd.DataFrame:
    """
    Create vehicle distribution table.
    
    Columns:
    - split
    - vehicle_model
    - trip_count
    - sample_count
    - percentage
    """
    
    train = pd.read_parquet(train_file)
    val = pd.read_parquet(val_file)
    test = pd.read_parquet(test_file)
    
    distribution_rows = []
    
    for split_name, split_data in [('Train', train), ('Validation', val), ('Test', test)]:
        total_samples = len(split_data)
        
        vehicle_summary = split_data.groupby('vehicle_model').agg({
            'trip_id': 'nunique',
        }).reset_index()
        vehicle_summary.columns = ['vehicle_model', 'trip_count']
        
        # Add sample count
        sample_counts = split_data.groupby('vehicle_model').size().reset_index(name='sample_count')
        vehicle_summary = vehicle_summary.merge(sample_counts, on='vehicle_model')
        
        vehicle_summary['split'] = split_name
        vehicle_summary['percentage'] = (vehicle_summary['sample_count'] / total_samples * 100)
        
        distribution_rows.append(vehicle_summary)
    
    distribution_df = pd.concat(distribution_rows, ignore_index=True)
    
    # Reorder columns
    distribution_df = distribution_df[['split', 'vehicle_model', 'trip_count', 'sample_count', 'percentage']]
    
    # Add total row for each split
    totals = []
    for split_name in ['Train', 'Validation', 'Test']:
        split_data = distribution_df[distribution_df['split'] == split_name]
        totals.append({
            'split': split_name,
            'vehicle_model': 'TOTAL',
            'trip_count': split_data['trip_count'].sum(),
            'sample_count': split_data['sample_count'].sum(),
            'percentage': 100.0
        })
    
    distribution_df = pd.concat([distribution_df, pd.DataFrame(totals)], ignore_index=True)
    
    # Save CSV
    if output_csv:
        print(f"Saving vehicle distribution to {output_csv}...")
        distribution_df.to_csv(output_csv, index=False)
    
    return distribution_df


if __name__ == '__main__':
    project_root = Path(__file__).parent.parent.parent
    
    train_file = project_root / 'data' / 'processed' / 'train.parquet'
    val_file = project_root / 'data' / 'processed' / 'validation.parquet'
    test_file = project_root / 'data' / 'processed' / 'test.parquet'
    
    output_stats_csv = project_root / 'reports' / 'split_target_statistics.csv'
    output_dist_csv = project_root / 'data' / 'processed' / 'split_distribution.csv'
    output_plot = project_root / 'reports' / 'figures' / 'split_target_distribution.png'
    
    # Create figures directory if needed
    output_plot.parent.mkdir(parents=True, exist_ok=True)
    
    print("="*60)
    print("TARGET DISTRIBUTION ANALYSIS")
    print("="*60)
    
    target_stats = create_distribution_analysis(
        str(train_file),
        str(val_file),
        str(test_file),
        output_csv=str(output_stats_csv),
        output_plot=str(output_plot)
    )
    
    print("\n" + "="*60)
    print("TARGET STATISTICS")
    print("="*60)
    print(target_stats.to_string(index=False))
    
    print("\n" + "="*60)
    print("VEHICLE DISTRIBUTION ANALYSIS")
    print("="*60)
    
    vehicle_dist = create_vehicle_distribution(
        str(train_file),
        str(val_file),
        str(test_file),
        output_csv=str(output_dist_csv)
    )
    
    print(vehicle_dist.to_string(index=False))
    
    print("\n✓ Analysis complete")

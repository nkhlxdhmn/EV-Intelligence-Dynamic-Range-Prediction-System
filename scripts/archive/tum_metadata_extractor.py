import os
import pyarrow.parquet as pq
import pandas as pd
import json

base_dir = r"c:\Work_Space\EV Intelligence & Dynamic Range Prediction System\dataset\electric-vehicle-uds-dataset-main"

inventory = []

def process_dir(current_dir):
    for root, dirs, files in os.walk(current_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.parquet', '.json', '.csv']:
                full_path = os.path.join(root, file)
                size_mb = os.path.getsize(full_path) / (1024 * 1024)
                rel_path = os.path.relpath(full_path, base_dir)
                
                rows = None
                cols = None
                schema = None
                
                if ext == '.parquet':
                    # Read only metadata
                    pf = pq.ParquetFile(full_path)
                    rows = pf.metadata.num_rows
                    cols = pf.metadata.num_columns
                    schema = [pf.metadata.schema.column(i).name for i in range(cols)]
                    
                inventory.append({
                    'file': rel_path,
                    'extension': ext,
                    'size_mb': round(size_mb, 4),
                    'rows_if_available': rows,
                    'columns_if_available': cols,
                    'schema': json.dumps(schema) if schema else None
                })

process_dir(base_dir)

# Save inventory
out_dir = r"c:\Work_Space\EV Intelligence & Dynamic Range Prediction System\data\interim"
os.makedirs(out_dir, exist_ok=True)
pd.DataFrame(inventory).to_csv(os.path.join(out_dir, "tum_file_inventory.csv"), index=False)

# Get some sample stats from parquet to verify schema and timestamps
pq_files = [x for x in inventory if x['extension'] == '.parquet']
print(f"Found {len(pq_files)} Parquet files.")
for pf in pq_files:
    print(f"{pf['file']}: {pf['rows_if_available']} rows, {pf['columns_if_available']} cols")
    print(f"Schema: {pf['schema']}")

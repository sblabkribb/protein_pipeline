import os
import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import mean_squared_error

def load_cath_data(csv_path: str) -> pd.DataFrame:
    """Loads CATH batch data and filters valid rows."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Data file not found: {csv_path}")
    
    df = pd.read_csv(csv_path)
    required_cols = ['target_id', 'sequence', 'soluprot_score', 'plddt_score']
    missing_cols = [c for c in required_cols if c not in df.columns]
    
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
        
    df = df.dropna(subset=['target_id', 'sequence'])
    return df

def main():
    print("Starting LOTO Validation...")

if __name__ == "__main__":
    main()

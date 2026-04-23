import os
import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import mean_squared_error
import torch
from transformers import EsmModel, AutoTokenizer

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

def get_esm_embeddings(df: pd.DataFrame, cache_path: str = "cath_embeddings.npy") -> np.ndarray:
    """Generates or loads 320D ESM-2 embeddings for the sequences."""
    if os.path.exists(cache_path):
        print(f"Loading cached embeddings from {cache_path}")
        return np.load(cache_path)
        
    print("Generating ESM-2 embeddings... This may take a few minutes.")
    model_name = "facebook/esm2_t6_8M_UR50D"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = EsmModel.from_pretrained(model_name)
    model.eval()
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = model.to(device)
    
    embeddings = []
    sequences = df['sequence'].tolist()
    
    with torch.no_grad():
        for i in range(0, len(sequences), 16): # Batch size 16
            batch_seqs = sequences[i:i+16]
            inputs = tokenizer(batch_seqs, return_tensors="pt", padding=True, truncation=True, max_length=1024)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            outputs = model(**inputs)
            
            # Mean pooling over sequence length, ignoring padding tokens
            attention_mask = inputs['attention_mask'].unsqueeze(-1)
            sum_embeddings = torch.sum(outputs.last_hidden_state * attention_mask, dim=1)
            sum_mask = torch.clamp(attention_mask.sum(dim=1), min=1e-9)
            mean_pooled = sum_embeddings / sum_mask
            
            embeddings.append(mean_pooled.cpu().numpy())
            print(f"Processed {min(i+16, len(sequences))}/{len(sequences)}")
            
    final_embeddings = np.vstack(embeddings)
    np.save(cache_path, final_embeddings)
    return final_embeddings

def main():
    print("Starting LOTO Validation...")

if __name__ == "__main__":
    main()

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure pipeline_mcp modules can be found
sys.path.insert(0, "/opt/protein_pipeline/pipeline-mcp/src")

# Load environment variables
load_dotenv('pipeline-mcp/.env')

from pipeline_mcp.s3 import ncp_storage

def download_cath_batch(target_dir="cath_outputs"):
    ncp_storage._ensure_initialized()
    client = ncp_storage._client
    bucket = ncp_storage.bucket
    
    if not client:
        print("S3 credentials not found or invalid.")
        return
        
    print(f"Connected to bucket: {bucket}")
    Path(target_dir).mkdir(exist_ok=True)
    
    try:
        # Check what we have in outputs/ in S3
        prefix = "outputs/"
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        
        download_count = 0
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    # We are looking for CATH targets, they might look like "outputs/1a2bA00/..."
                    # Include all summary scoring files to ensure no missing data
                    target_files = [
                        'metrics.json', 
                        'soluprot.json', 
                        'af2_scores.json', 
                        'relax_scores.json', 
                        'designs_filtered.fasta',
                        'target.fasta'
                    ]
                    if any(key.endswith(f) for f in target_files):
                        local_path = Path(target_dir) / key.replace("outputs/", "")
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        if not local_path.exists():
                            print(f"Downloading {key} -> {local_path}")
                            client.download_file(bucket, key, str(local_path))
                            download_count += 1
                            
        print(f"Successfully downloaded {download_count} relevant files into {target_dir}/")
    except Exception as e:
        print(f"Error accessing S3: {e}")

if __name__ == "__main__":
    download_cath_batch()

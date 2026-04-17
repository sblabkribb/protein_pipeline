import sys
import os
import time
import argparse
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure imports work from project root
project_root = Path("/opt/protein_pipeline")
sys.path.append(str(project_root / "pipeline-mcp/src"))

from dotenv import load_dotenv
load_dotenv(str(project_root / "pipeline-mcp/.env"), override=True)

from pipeline_mcp.app import build_runner
from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.s3 import ncp_storage

MAX_CONCURRENT_PIPELINES = 5 

def _is_already_completed(run_id: str) -> bool:
    # Check local output first to see if it finished successfully
    report_file = project_root / "outputs" / run_id / "report.md"
    if report_file.exists():
        return True
    return False

def process_target(pdb_path: Path, runner, subset_name: str) -> bool:
    # run_id incorporates the subset name (e.g. cath_train_1v6z)
    run_id = f"cath_{subset_name}_{pdb_path.stem}"
    
    if _is_already_completed(run_id):
        print(f"[{run_id}] ⏭️ 이미 완료된 타겟입니다. 스킵합니다.")
        return True

    print(f"[{run_id}] 🚀 고유 진화 공정 시작 (30/50/70 Tiers, BioEmu+RFD3, Masking 6A)...")

    success = False
    try:
        pdb_content = pdb_path.read_text(encoding="utf-8")

        # 사용자 정의 파이프라인 수식: 3 (Tiers) * 2 (Backbones) * 10 (Samples) * 2 (MPNN) = 120
        request = PipelineRequest(
            target_fasta="",
            target_pdb=pdb_content,
            
            # 1. MSA & Conservation (보존도 30%, 50%, 70% 티어 설정)
            mmseqs_target_db="uniref90",
            conservation_tiers=[0.3, 0.5, 0.7], 
            
            # 2. Masking (리간드 6A 부위 고정 마스킹)
            ligand_mask_distance=6.0, 
            ligand_mask_use_original_target=True,
            
            # 3. Backbone Generation (BioEmu 10개 + RFD3 10개)
            bioemu_use=True,
            bioemu_num_samples=20,          # 충분히 20개를 생성하고
            bioemu_max_return_structures=10, # 필터링을 거쳐 10개만 리턴
            bioemu_target_rmsd_cutoff=4.0,  # 컷오프를 4.0A로 완화하여 더 많은 백본 통과 유도
            
            rfd3_mode="scaffold", 
            rfd3_max_return_designs=10,
            
            # 4. ProteinMPNN (백본당 2개씩 시퀀스 디자인)
            num_seq_per_tier=2, 
            sampling_temp=0.1,
            
            # 5. Evaluation & S3 Sync
            af2_provider="colabfold", 
            relax_enabled=True,
            novelty_enabled=True,
            wt_compare=True,      # 원본(WT)과의 비교 데이터셋 구축 필수
            agent_panel_enabled=False, # 대규모 배치이므로 LLM 에이전트 패널 비활성화 (토큰 절약)
            
            stop_after="novelty"
        )
        
        # 파이프라인 실행 (이 과정에서 내부적으로 120개 결과가 생성됨)
        runner.run(request, run_id=run_id)
        print(f"[{run_id}] ✅ 120개 시퀀스 진화 궤적 생성 완료.")
        success = True
        
    except Exception as e:
        print(f"[{run_id}] ❌ 에러 발생: {e}")
        success = False
    
    finally:
        # 에러가 나든 성공하든 무조건 S3로 지금까지 만들어진 데이터를 동기화합니다.
        print(f"[{run_id}] ☁️ 생성된 중간/최종 결과를 S3로 동기화 중...")
        try:
            ncp_storage.sync_outputs(run_id, local_root=str(project_root / "outputs"))
            print(f"[{run_id}] ☁️ S3 동기화 완료.")
        except Exception as s3_e:
            print(f"[{run_id}] ⚠️ S3 동기화 실패: {s3_e}")

    return success

def main():
    parser = argparse.ArgumentParser(description="Run full pipeline on CATH datasets.")
    parser.add_argument("--subset", type=str, required=True, choices=["train", "val", "test"], 
                        help="Which dataset subset to run (train, val, test).")
    args = parser.parse_args()
    
    subset_name = args.subset
    targets_dir = project_root / f"cath_{subset_name}"
    failed_log_file = project_root / f"failed_{subset_name}_targets.txt"
    
    if not targets_dir.exists():
        print(f"에러: {targets_dir} 폴더가 없습니다. 01_fetch_and_split_datasets.py를 먼저 실행하세요.")
        sys.exit(1)
        
    pdb_files = sorted(list(targets_dir.glob("*.pdb")))
    if not pdb_files:
        print("PDB 파일을 찾을 수 없습니다.")
        sys.exit(1)
        
    print(f"엄선된 {len(pdb_files)}개의 '{subset_name}' 타겟에 대해 '120 Trajectory' 배치를 시작합니다.")
    runner = build_runner()
    
    success_count = 0
    failed_targets = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PIPELINES) as executor:
        futures = {executor.submit(process_target, pdb, runner, subset_name): pdb for pdb in pdb_files}
        for future in as_completed(futures):
            pdb = futures[future]
            try:
                if future.result(): 
                    success_count += 1
                else:
                    failed_targets.append(pdb.name)
            except Exception as e:
                print(f"[{pdb.stem}] ❌ 알 수 없는 스레드 에러: {e}")
                failed_targets.append(pdb.name)

    # 실패한 타겟 기록
    if failed_targets:
        failed_log_file.write_text("\n".join(failed_targets) + "\n", encoding="utf-8")
        print(f"\n⚠️ 주의: {len(failed_targets)}개의 타겟 처리에 실패했습니다. '{failed_log_file.name}'에 기록되었습니다.")

    elapsed = time.time() - start_time
    print(f"\n✨ '{subset_name}' 배치 완료! 성공: {success_count}/{len(pdb_files)}, 소요시간: {elapsed/3600:.2f}h")

if __name__ == "__main__":
    main()

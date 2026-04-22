import sys
import time
import argparse
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Ensure imports work from project root
project_root = Path("/opt/protein_pipeline")
sys.path.append(str(project_root / "pipeline-mcp/src"))

from dotenv import load_dotenv

load_dotenv(str(project_root / "pipeline-mcp/.env"), override=True)

from pipeline_mcp.app import build_runner
from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.s3 import ncp_storage

# GPU 워커 6개 중 여유분 1개를 남기고 5개를 풀가동합니다.
MAX_CONCURRENT_PIPELINES = 5
MAX_RETRIES_PER_TARGET = 3

GLOBAL_STOP_EVENT = False


def build_cath_request(pdb_content: str) -> PipelineRequest:
    return PipelineRequest(
        target_fasta="",
        target_pdb=pdb_content,
        rfd3_use=False,
        mmseqs_target_db="uniref90",
        conservation_tiers=[0.3, 0.5, 0.7],
        ligand_mask_distance=6.0,
        ligand_mask_use_original_target=True,
        pdb_strip_nonpositive_resseq=True,
        pdb_renumber_resseq_from_1=True,
        bioemu_use=False,
        num_seq_per_tier=40,
        sampling_temp=0.1,
        soluprot_cutoff=0.0,
        af2_provider="colabfold",
        af2_max_candidates_per_tier=0,
        af2_top_k=0,
        relax_enabled=True,
        novelty_enabled=False,
        wt_compare=False,
        agent_panel_enabled=False,
        stop_after="af2",
        force=False,  # 이전에 완료된 단계는 건너뛰고 재개(Resume)
        auto_recover=True,  # 에러 났던 구간은 자동으로 재시도
    )


def get_log_paths(subset: str):
    return {
        "success": project_root / f"batch_success_{subset}.csv",
        "failed": project_root / f"batch_failed_{subset}.csv",
    }


def record_success(subset: str, run_id: str):
    path = get_log_paths(subset)["success"]
    if not path.exists():
        path.write_text("timestamp,run_id\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{now},{run_id}\n")


def record_failure(subset: str, run_id: str, error: str):
    path = get_log_paths(subset)["failed"]
    if not path.exists():
        path.write_text("timestamp,run_id,error\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clean_err = str(error).replace("\n", " ").replace(",", ";")[:200]
        f.write(f"{now},{run_id},{clean_err}\n")


def is_already_done(subset: str, run_id: str) -> bool:
    # 1. 로컬에 report.md가 있으면 완료
    if (project_root / "outputs" / run_id / "report.md").exists():
        return True
    # 2. 성공 로그 파일에 기록되어 있으면 완료 (로컬 삭제된 경우 대응)
    path = get_log_paths(subset)["success"]
    if path.exists():
        if run_id in path.read_text(encoding="utf-8"):
            return True

    # 3. 실패 로그 파일에 기록되어 있으면 일단 스킵 (무한 재실행 방지)
    #    (나중에 진짜 재실행이 필요하면 batch_failed_XXX.csv 에서 해당 줄을 지우고 실행하면 됨)
    fail_path = get_log_paths(subset)["failed"]
    if fail_path.exists():
        # 로그 파일의 내용에 run_id가 들어있는지 검사
        if run_id in fail_path.read_text(encoding="utf-8"):
            return True

    return False


def process_target(
    pdb_path: Path,
    runner,
    subset_name: str,
    *,
    keep_local: bool,
    stop_on_error: bool = False,
) -> bool:
    global GLOBAL_STOP_EVENT
    if GLOBAL_STOP_EVENT:
        return False

    run_id = f"cath_{subset_name}_{pdb_path.stem}"

    if is_already_done(subset_name, run_id):
        return True

    print(f"[{run_id}] 🚀 고유 진화 공정 투입...")

    pdb_content = pdb_path.read_text(encoding="utf-8")

    final_success = False
    last_error = "Unknown"

    for attempt in range(MAX_RETRIES_PER_TARGET):
        if GLOBAL_STOP_EVENT:
            return False
        try:
            request = build_cath_request(pdb_content)

            runner.run(request, run_id=run_id)

            final_success = True
            print(f"[{run_id}] ✅ 완료.")
            break

        except Exception as e:
            last_error = str(e)
            err_msg = last_error.lower()
            if attempt < MAX_RETRIES_PER_TARGET - 1 and any(
                x in err_msg
                for x in ["endpoint", "colabfold", "timeout", "failed to run"]
            ):
                wait = 60 * (attempt + 1)
                print(
                    f"[{run_id}] 🔄 서버 지연으로 재시도 ({attempt + 1}/{MAX_RETRIES_PER_TARGET}). {wait}s 대기..."
                )
                time.sleep(wait)
                continue
            else:
                break

    # 마무리 작업
    try:
        # 무조건 S3 동기화 (부분 결과라도 보존)
        ncp_storage.sync_outputs(run_id, local_root=str(project_root / "outputs"))

        if final_success:
            record_success(subset_name, run_id)
            if not keep_local:
                # 성공 시에만 로컬 삭제하여 용량 확보
                import shutil

                local_dir = project_root / "outputs" / run_id
                if local_dir.exists():
                    shutil.rmtree(local_dir)
        else:
            record_failure(subset_name, run_id, last_error)
            if stop_on_error:
                print(f"[{run_id}] 🛑 에러 발생으로 인한 전체 작업 중지 설정 활성화됨.")
                GLOBAL_STOP_EVENT = True

    except Exception as final_e:
        print(f"[{run_id}] ⚠️ 최종 기록 단계 에러: {final_e}")
        if stop_on_error:
            GLOBAL_STOP_EVENT = True

    if GLOBAL_STOP_EVENT:
        raise RuntimeError(
            f"Pipeline stopped on error at target {run_id}: {last_error}"
        )

    return final_success


def main():
    parser = argparse.ArgumentParser(description="Smart 24/7 Metadata-managed Batch")
    parser.add_argument(
        "--subset", type=str, required=True, choices=["train", "val", "test"]
    )
    parser.add_argument("--max-workers", type=int, default=MAX_CONCURRENT_PIPELINES)
    parser.add_argument("--keep-local", action="store_true")
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop processing if an error occurs",
    )
    args = parser.parse_args()

    targets_dir = project_root / f"cath_{args.subset}"
    pdb_files = sorted(list(targets_dir.glob("*.pdb")))

    log_paths = get_log_paths(args.subset)
    max_workers = max(1, int(args.max_workers or MAX_CONCURRENT_PIPELINES))
    print(f"💎 배치 가동 (타겟: {len(pdb_files)}, 동시성: {max_workers})")
    print(f"📝 성공 로그: {log_paths['success'].name}")
    print(f"📝 실패 로그: {log_paths['failed'].name}")
    print(f"🧷 keep_local={'yes' if args.keep_local else 'no'}")
    print(f"🛑 stop_on_error={'yes' if args.stop_on_error else 'no'}")

    runner = build_runner()

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(
                executor.map(
                    lambda p: process_target(
                        p,
                        runner,
                        args.subset,
                        keep_local=bool(args.keep_local),
                        stop_on_error=bool(args.stop_on_error),
                    ),
                    pdb_files,
                )
            )
    except Exception as e:
        print(f"\n❌ 작업 중단됨: {e}")
        sys.exit(1)

    print(f"\n✨ '{args.subset}' 작업 종료.")


if __name__ == "__main__":
    main()

"""게이트 0 캠페인용 PipelineRequest 빌더 (설계 6.1b).

핵심은 두 가지다.
1. MPNN 설정과 백본당 서열 수를 arm 과 무관하게 고정해 yield 를 비교 가능하게 만든다.
2. `soluprot_cutoff=0.0` 과 `af2_max_candidates_per_tier=0` 으로 **모든 후보에 AF2 를
   실행**한다. 기존 backbone ablation 은 `af2_max_candidates_per_tier=10` 이라
   SoluProt 상위 10개만 AF2 라벨을 가졌고, 그것이 절단 편향의 원인이었다(설계 3.5).
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_SRC = PROJECT_ROOT / "pipeline-mcp" / "src"
if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))

from pipeline_mcp.models import PipelineRequest  # noqa: E402

from .protocol import (  # noqa: E402
    GATE0_AF2_EXTRA_FLAGS,
    GATE0_BACKBONES_PER_RUN,
    GATE0_MPNN_SETTINGS,
    GATE0_SEQUENCES_PER_BACKBONE,
    GATE0_TIERS,
)

GATE0_ARMS = ("target", "rfd3", "bioemu")

_ARM_BACKBONE_CONFIG: dict[str, dict[str, int | bool]] = {
    "target": {
        "rfd3_use": False, "bioemu_use": False,
        "rfd3_max_return_designs": 0,
        "bioemu_num_samples": 0, "bioemu_max_return_structures": 0,
    },
    "rfd3": {
        "rfd3_use": True, "bioemu_use": False,
        "rfd3_max_return_designs": GATE0_BACKBONES_PER_RUN,
        "bioemu_num_samples": 0, "bioemu_max_return_structures": 0,
    },
    "bioemu": {
        "rfd3_use": False, "bioemu_use": True,
        "rfd3_max_return_designs": 0,
        "bioemu_num_samples": 5 * GATE0_BACKBONES_PER_RUN,
        "bioemu_max_return_structures": GATE0_BACKBONES_PER_RUN,
    },
}


def build_gate0_request(pdb_text: str, arm: str, *, seed: int,
                        stop_after: str = "af2",
                        start_from: str | None = None) -> PipelineRequest:
    """게이트 0 의 고정 요청을 만든다.

    `stop_after` 기본값은 캠페인이 쓴 "af2" 다. 백본만 만들고 멈추려면 "rfd3" 을
    준다 - 홀드아웃 백본 생성이 그 경로를 쓴다. 기본값을 바꾸지 않으므로 62 타겟
    캠페인의 요청은 그대로다.

    `start_from="rfd3"` 는 MSA 를 건너뛴다. RFD3 는 타겟 구조에 조건을 걸고
    MSA 를 읽지 않으므로, 백본만 만들 때 MSA 는 순수한 낭비다. 실제로 홀드아웃
    1 단계의 첫 실행이 mmseqs_msa 에서 50 분 동안 멈춰 있었고 mmseqs 프로세스는
    아예 없었다. 기본값은 None 이라 캠페인 경로는 그대로다.
    """
    if arm not in GATE0_ARMS:
        raise ValueError(f"unknown gate0 arm: {arm!r}; expected one of {GATE0_ARMS}")
    cfg = _ARM_BACKBONE_CONFIG[arm]
    bioemu_samples = int(cfg["bioemu_num_samples"])
    bioemu_return = int(cfg["bioemu_max_return_structures"])

    return PipelineRequest(
        target_fasta="",
        target_pdb=pdb_text,
        rfd3_use=bool(cfg["rfd3_use"]),
        rfd3_use_ensemble=bool(cfg["rfd3_use"]),
        rfd3_max_return_designs=int(cfg["rfd3_max_return_designs"]),
        rfd3_partial_t=5.0,
        rfd3_target_rmsd_cutoff=2.0,
        bioemu_use=bool(cfg["bioemu_use"]),
        bioemu_num_samples=bioemu_samples,
        bioemu_max_return_structures=bioemu_return,
        bioemu_base_seed=int(seed),
        bioemu_batch_size_100=1,
        bioemu_max_attempted_structures=max(bioemu_samples, bioemu_return),
        conservation_tiers=list(GATE0_TIERS),
        ligand_mask_distance=6.0,
        ligand_mask_use_original_target=True,
        pdb_strip_nonpositive_resseq=True,
        pdb_renumber_resseq_from_1=True,
        # --- arm 과 무관하게 고정되는 MPNN 설정 ---
        num_seq_per_tier=GATE0_SEQUENCES_PER_BACKBONE,
        sampling_temp=float(GATE0_MPNN_SETTINGS["sampling_temp"]),
        batch_size=int(GATE0_MPNN_SETTINGS["batch_size"]),
        seed=int(GATE0_MPNN_SETTINGS["seed"]),
        # --- 선택 편향 제거 ---
        soluprot_cutoff=0.0,
        af2_provider="colabfold",
        af2_max_candidates_per_tier=0,
        af2_top_k=0,
        af2_extra_flags=GATE0_AF2_EXTRA_FLAGS,
        relax_enabled=False,
        novelty_enabled=False,
        wt_compare=False,
        agent_panel_enabled=False,
        stop_after=stop_after,
        start_from=start_from,
        force=False,
        auto_recover=True,
    )

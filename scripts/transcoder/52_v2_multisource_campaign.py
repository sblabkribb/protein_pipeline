#!/usr/bin/env python3
"""RAPID v2.0 multi-source prospective validation — 실행 러너 (Step 8).

동결 정본은 `public_data/benchmark/gate0/multisource_validation_plan.json` 이다.
**이 스크립트는 그 파일에서 숫자를 읽는다. 어떤 동결값도 여기에 다시 적지
않는다** - 두 곳에 적으면 언젠가 갈라지고, 갈라지면 어느 쪽이 정본인지 코드를
읽어야 알 수 있게 된다.

무엇을 하는가
-------------
```
A. backbone 생성   (target x source) 48 조합. 파이프라인 경로를 쓴다.
                   동결된 attempt cap 까지만 시도하고, RMSD <= 2.0 A 를
                   통과한 것만 받는다.
B. 서열 설계+용해도 ProteinMPNN 을 보존도 tier 별로 호출하고 SoluProt 을 붙인다.
C. AF2 폴딩        전 후보를 접는다. 선택 편향이 없어야 replay 가 성립한다.
```

무엇을 하지 않는가
------------------
```
MSA 를 다시 돌리지 않는다   계획이 runs_per_target=1 · shared_across_sources 다.
                            source 마다 다시 돌리면 동결된 보존도 마스크가 깨진다.
부족분을 채우지 않는다      cap 까지 시도하고 통과한 것으로 간다. 타겟을 예비로
                            바꾸지 않고, 2.0 A 를 풀지 않고, 무한 재시도하지 않는다.
후보를 고르지 않는다        soluprot_cutoff=0 · af2 상한 0. 전수를 접는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
PLAN_PATH = BASE / "multisource_validation_plan.json"
MSA_MANIFEST = BASE / "full_msa_manifest.json"
OUT_DIR = BASE / "v2_multisource"

SOURCES = ("rfd3", "bioemu")

#: (target x source) 하나를 **실행** 해 보는 최대 횟수. 생성 예산(cap 40/200)과
#: 다른 축이다 - 워커가 job 을 잃거나 죽었을 때 한 번 더 걸어 보는 것이고, 매
#: 시도는 여전히 같은 동결 cap 안에서 돈다.
#:
#: 상한이 필요한 이유는 시간이 아니라 **편향** 이다. 처음에는 실패한 unit 을
#: 무제한 재시도하게 두었는데, 그러면 성공한 unit 은 1 회, 실패한 unit 은 무한이
#: 되어 동결 규칙을 정면으로 어긴다 - "어려운 타겟에만 생성을 더 주지 않는다".
#: 모든 unit 에 같은 상한을 주고, 다 쓰면 확보된 것을 그대로 들고 넘어간다.
MAX_RUN_ATTEMPTS = 2


# ---------------------------------------------------------------- 동결값 읽기

def load_plan() -> dict:
    """동결 계획. `status != frozen` 이면 돌지 않는다."""
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if plan.get("status") != "frozen":
        raise SystemExit(
            f"계획이 frozen 이 아니다 (status={plan.get('status')!r}). "
            "동결되지 않은 설계로 전향 검증을 돌리지 않는다.")
    if plan.get("version") != "2.0":
        raise SystemExit(f"예상한 version 2.0 이 아니다: {plan.get('version')!r}")
    return plan


def cohort_rows(plan: dict, msa: dict) -> list[dict]:
    """(cohort, target) 를 동결된 selected 순서대로. MSA 산출물과 맞물린다.

    타겟 목록을 여기서 다시 만들지 않는다 - 동결된 `selected` 와 그 sha256 을
    쓰고, MSA 매니페스트에 그 타겟이 없으면 조용히 넘기지 않고 선다.
    """
    by_domain = {t["domain"]: t for t in msa["targets"]}
    rows: list[dict] = []
    for cohort_name, cohort in plan["cohorts"].items():
        selected = list(cohort["selected"])
        # 기존 freeze 테스트와 **같은 직렬화**를 쓴다 (기본 구분자).
        # pipeline-mcp/tests/test_calibration_v2_cohort_freeze.py:78 와
        # test_masked_holdout_freeze.py:57 이 정본이다 - 여기서 새 규약을
        # 만들면 같은 목록이 두 digest 를 갖게 된다.
        digest = hashlib.sha256(json.dumps(selected).encode()).hexdigest()
        if digest != cohort["selected_sha256"]:
            raise SystemExit(
                f"{cohort_name} 의 selected 가 동결 sha256 과 다르다.\n"
                f"  기록 {cohort['selected_sha256']}\n  계산 {digest}")
        for domain in selected:
            entry = by_domain.get(domain)
            if entry is None:
                raise SystemExit(
                    f"{cohort_name}/{domain} 의 MSA 가 매니페스트에 없다. "
                    "MSA 는 source 마다 다시 돌리지 않으므로 여기서 만들지 않는다.")
            rows.append({
                "cohort": cohort_name,
                "target_id": domain,
                "seed": int(cohort["seed"]),
                "pdb": entry["pdb"],
                "a3m_path": entry["a3m_path"],
                "length_aa": entry["length_aa"],
                "conservation": entry["conservation"],
            })
    return rows


def candidates_per_backbone(plan: dict, cohort: str) -> tuple[int, dict[str, int]]:
    design = plan["per_source_design"]
    if cohort == "calibration_v2":
        return (int(design["calibration_candidates_per_backbone"]),
                {k: int(v) for k, v in design["calibration_tier_counts"].items()})
    if cohort == "confirmatory":
        return (int(design["confirmatory_candidates_per_backbone"]),
                {k: int(v) for k, v in design["confirmatory_tier_counts"].items()})
    raise SystemExit(f"알 수 없는 cohort: {cohort!r}")


# ------------------------------------------------------------ 보존도 fixed pos

def conservation_config() -> dict:
    """보존도 설정을 **배포 기본값에서** 읽는다.

    `50_full_msa.py:128` 와 같은 출처다. 여기 상수를 다시 적으면 MSA 단계와
    설계 단계가 서로 다른 tier 로 돌 수 있고, 그러면 digest 대조가 통과해도
    설계에 쓰인 마스크가 기록된 마스크와 다를 수 있다.
    """
    import dataclasses

    from pipeline_mcp.models import PipelineRequest

    def default(name):
        f = PipelineRequest.__dataclass_fields__[name]
        return (f.default if f.default is not dataclasses.MISSING
                else f.default_factory())

    return {"tiers": list(default("conservation_tiers")),
            "mode": default("conservation_mode")}


def tier_fixed_positions(row: dict) -> dict[str, list[int]]:
    """A3M 에서 tier 별 고정 위치를 **다시 계산하고 동결 digest 와 대조한다**.

    매니페스트에는 개수와 sha256 만 있고 위치 자체는 없다. 다시 만든 것이
    그때 쓰인 것과 같다는 보장을 주석으로 하지 않는다 - `50_full_msa.py:245`
    와 같은 방식으로 digest 를 내고 다르면 선다.

    키 규약이 두 개라 여기서 잇는다. 매니페스트는 `str(0.3)`, 동결 계획의
    tier_counts 는 `"30"` 이다. 돌려주는 쪽은 **계획의 키**로 맞춘다 -
    호출부가 배분 수를 계획에서 읽기 때문이다.
    """
    from pipeline_mcp.bio.a3m import compute_conservation

    cfg = conservation_config()
    a3m_text = (PROJECT_ROOT / row["a3m_path"]).read_text(encoding="utf-8")
    cons = compute_conservation(a3m_text, tiers=cfg["tiers"],
                                mode=cfg["mode"], weights=None)
    recorded = row["conservation"]["fixed_positions_sha256"]

    out: dict[str, list[int]] = {}
    for tier, positions in cons.fixed_positions_by_tier.items():
        want = recorded.get(str(tier))
        if want is None:
            raise SystemExit(
                f"{row['target_id']}: 매니페스트에 tier {tier} digest 가 없다.")
        got = hashlib.sha256(json.dumps(positions).encode()).hexdigest()
        if got != want:
            raise SystemExit(
                f"{row['target_id']} tier {tier} 의 fixed positions 가 동결 "
                f"digest 와 다르다.\n  기록 {want}\n  재계산 {got}\n"
                "보존도 마스크가 달라지면 설계가 동결된 실험이 아니다.")
        out[str(int(round(float(tier) * 100)))] = list(positions)
    return out


# ------------------------------------------------------------------ A. 백본

_STAGER = None


def stager():
    """검증된 staging 을 `25_generate_holdout_backbones.py` 에서 그대로 쓴다.

    **다시 구현하지 않는다.** 그 파일의 `drop_ca_less_atoms` docstring 이
    여기서 겪은 실패를 이미 적어 두었다 - "원자는 있고 CA 가 없는 잔기가
    번호에 끼면 contig 가 원자 배열에 없는 잔기를 가리켜 검증에서 죽는다
    (2iayA00: contig A3-113 인데 A28 이 없다)". 처음에 원본 CATH 파일을
    그대로 보냈다가 `[component=X41] Residue X41 not found in atom array`
    로 같은 자리에서 죽었다. 홀드아웃 캠페인이 성공한 이유가 이 staging 이고,
    그 경로를 두 번 구현하면 또 갈라진다.
    """
    global _STAGER
    if _STAGER is None:
        path = (PROJECT_ROOT / "scripts" / "transcoder"
                / "25_generate_holdout_backbones.py")
        spec = importlib.util.spec_from_file_location("holdout_gen", path)
        _STAGER = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_STAGER)
    return _STAGER


def staged_target(pdb_path: str) -> tuple[str, dict]:
    """RFD3/BioEmu 에 실제로 보낼 구조. 원본 CATH 파일을 그대로 보내지 않는다."""
    from pipeline_mcp.bio.pdb import preprocess_pdb

    mod = stager()
    raw = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
    single, n_models = mod.first_model_only(raw)
    filtered = mod.drop_ca_less_atoms(single)
    processed, _mapping = preprocess_pdb(
        filtered, strip_nonpositive_resseq=True, renumber_resseq_from_1=True)

    def n_ca(text: str) -> int:
        return sum(1 for ln in text.splitlines()
                   if ln.startswith("ATOM") and ln[12:16].strip() == "CA")

    return processed, {
        "source_pdb": pdb_path,
        "n_models": n_models,
        "took_first_model": n_models > 1,
        "n_ca_raw": n_ca(raw),
        "n_ca_staged": n_ca(processed),
        "staged_sha256": hashlib.sha256(processed.encode("utf-8")).hexdigest(),
    }


def design_chain(pdb_text: str) -> str:
    """폴리머 체인 식별자. ATOM 레코드에서 읽는다 (HETATM 은 보지 않는다)."""
    chains = {line[21] for line in pdb_text.splitlines()
              if line.startswith("ATOM") and len(line) > 21}
    if len(chains) != 1:
        raise SystemExit(
            f"ATOM 체인이 하나가 아니다: {sorted(chains)}. 이 코호트의 타겟은 "
            "CATH 도메인 하나이므로 단일 체인이어야 한다.")
    return chains.pop()


def frozen_fixed_atoms(chain: str) -> dict[str, str]:
    """동결 §generation_rules.rfd3 의 `{A1: ALL}` 을 이 타겟의 체인에 적용한다.

    **동결 문구는 체인 A 를 전제로 쓰였다.** 24 타겟 중 23 개가 체인 A 라
    거기서는 글자 그대로 `{A1: ALL}` 이 된다. 남은 하나(`1pp1X02`)는 체인 X 다.

    그 타겟에 `{A1: ALL}` 을 글자 그대로 넣으면 프로토콜이 재현되지 않는다 -
    atomworks 가 비폴리머(물 382 개)를 분리하면서 그쪽 체인을 "A" 로 이름
    붙이기 때문에, `A1` 이 설계 체인의 첫 잔기가 아니라 **물** 을 가리킨다.
    실제로 RFD3 가 `[component=X41] Residue X41 not found` 로 죽었다.

    그래서 문구가 뜻하는 것(설계 체인의 첫 잔기, 전체 원자)을 체인에 맞춰
    적용한다. 체인 A 타겟에서는 동결 문구와 **바이트 단위로 같다**.
    `pdb_renumber_resseq_from_1=True` 이므로 첫 잔기 번호는 항상 1 이다.
    """
    return {f"{chain}1": "ALL"}


def build_v2_request(plan: dict, pdb_text: str, source: str, *, seed: int):
    """동결된 v2 파라미터로 백본 생성 요청. gate0 상수를 쓰지 않는다."""
    from pipeline_mcp.models import PipelineRequest

    rules = plan["generation_rules"][source]
    common = dict(
        target_fasta="",
        target_pdb=pdb_text,
        conservation_tiers=[0.3, 0.5, 0.7],
        pdb_strip_nonpositive_resseq=True,
        pdb_renumber_resseq_from_1=True,
        soluprot_cutoff=0.0,
        af2_max_candidates_per_tier=0,
        af2_top_k=0,
        relax_enabled=False,
        novelty_enabled=False,
        wt_compare=False,
        agent_panel_enabled=False,
        force=False,
        auto_recover=True,
    )
    if source == "rfd3":
        return PipelineRequest(
            **common,
            rfd3_use=True,
            rfd3_use_ensemble=True,
            rfd3_max_return_designs=int(rules["accepted_needed_per_target"]),
            rfd3_max_attempted_designs=int(rules["max_attempts_per_target"]),
            rfd3_partial_t=float(rules["partial_t"]),
            rfd3_target_rmsd_cutoff=2.0,
            # `select_fixed_atoms` 를 **주지 않는다.** 동결 문서의 `{A1: ALL}`
            # 은 주입할 파라미터가 아니라 파이프라인이 스스로 만들어 내는 값을
            # 적어 둔 것이다. 검증된 `build_gate0_request` 도 None 이고, 실제로
            # None 으로 돌려도 rfd3/inputs.json 에 `{"A1": "ALL"}` 이 그대로
            # 찍힌다(측정함). 넣어도 같은 값이지만, 검증된 경로와 요청을
            # 다르게 만들 이유가 없다.
            bioemu_use=False,
            seed=seed,
            start_from="rfd3",
            stop_after="rfd3",
        )
    return PipelineRequest(
        **common,
        rfd3_use=False,
        bioemu_use=True,
        bioemu_model_name=str(rules["model_name"]),
        bioemu_num_samples=int(rules["num_samples"]),
        bioemu_max_return_structures=int(rules["max_return_structures"]),
        bioemu_max_attempted_structures=int(rules["max_attempted_structures"]),
        bioemu_target_rmsd_cutoff=float(rules["target_rmsd_cutoff"]),
        bioemu_filter_samples=bool(rules["filter_samples"]),
        bioemu_base_seed=seed,
        bioemu_batch_size_100=1,
        seed=seed,
        start_from="bioemu",
        stop_after="bioemu",
    )


def collect_backbones(output_root: Path, run_id: str, source: str, *,
                      wanted: int, cutoff: float) -> tuple[list[Path], dict]:
    """**게이트를 통과한 집합**. 디렉터리를 훑지 않는다.

    처음에는 `designs/*.pdb` 를 glob 했는데, BioEmu 는 `designs/` 옆에
    `raw_samples/` 를 같이 남긴다. 그래서 거부된 구조까지 21 개가 잡혔고,
    그대로 갔으면 2.0 A accept gate 가 무력화된 채 폴딩이 돌았을 것이다.
    정본은 `target_gate_summary.json` 이다 - u 를 디렉터리 내용이 아니라
    동결된 게이트에 묶는다.

    돌려주는 두 번째 값은 근거다: 몇 번 시도했고(`input_count`), 무엇이
    왜 떨어졌는지(`rejected_ids` · `rmsd_by_id`). 부족분은 결함이 아니라
    기록해야 할 결과이므로 숫자만 남기지 않는다.
    """
    run_dir = output_root / run_id / source
    gate_path = run_dir / "target_gate_summary.json"
    if not gate_path.exists():
        # 생성 자체가 아무것도 내지 못한 경우. 0 은 정상적인 결과다.
        return [], {"gate_summary_present": False, "attempts_used": 0}

    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gate.get("applied"):
        raise SystemExit(
            f"{run_id}: target gate 가 적용되지 않았다. 게이트 없이 얻은 "
            "백본은 동결된 accept 기준을 통과한 것이 아니다.")
    if abs(float(gate.get("cutoff", -1)) - cutoff) > 1e-9:
        raise SystemExit(
            f"{run_id}: accept cutoff 가 {gate.get('cutoff')} 다. 동결값은 "
            f"{cutoff} 이며 실행 중에 바꾸지 않는다.")

    accepted = list(gate.get("accepted_ids") or [])
    if len(accepted) > wanted:
        raise SystemExit(
            f"{run_id}: 통과 백본이 {len(accepted)} 개로 목표 {wanted} 을 "
            "넘었다. 여기서 잘라내면 그것이 곧 선택이 되므로 멈춘다 "
            "(동결 규칙: 구조 점수나 yield 로 고르지 않는다).")

    paths: list[Path] = []
    for design_id in accepted:
        pdb = run_dir / "designs" / f"{design_id}.pdb"
        if not pdb.exists():
            raise SystemExit(
                f"{run_id}: accept 된 {design_id} 의 PDB 가 없다 ({pdb}).")
        paths.append(pdb)
    if len(paths) != int(gate.get("accepted_count", -1)):
        raise SystemExit(
            f"{run_id}: accepted_count 와 파일 수가 다르다 "
            f"({gate.get('accepted_count')} vs {len(paths)}).")

    return paths, {
        "gate_summary_present": True,
        "attempts_used": int(gate.get("input_count", 0)),
        "accepted_ids": accepted,
        "rejected_ids": list(gate.get("rejected_ids") or []),
        "rmsd_by_id": gate.get("rmsd_by_id"),
        "gate_cutoff": gate.get("cutoff"),
        "gate_mask_mode": gate.get("mask_mode"),
        "gate_method": gate.get("method"),
    }


def stage_backbones(plan: dict, rows: list[dict], *, output_root: Path,
                    sources: tuple[str, ...], dry_run: bool) -> dict:
    from pipeline_mcp.app import build_runner

    state_path = OUT_DIR / "backbones.json"
    state = (json.loads(state_path.read_text(encoding="utf-8"))
             if state_path.exists() else {"runs": {}})
    runner = None if dry_run else build_runner()
    want = int(plan["per_source_design"]["backbones_per_target"])

    planned = [(row, source) for row in rows for source in sources]
    print(f"[A] backbone 생성 대상 {len(planned)} 조합 "
          f"(타겟 {len(rows)} x source {len(sources)})", flush=True)

    for index, (row, source) in enumerate(planned, start=1):
        run_id = f"v2_{row['cohort']}_{row['target_id']}_{source}"
        prior = state["runs"].get(run_id) or {}
        if prior.get("done"):
            continue
        attempt_no = int(prior.get("run_attempts") or 0) + 1
        rules = plan["generation_rules"][source]
        cap = int(rules.get("max_attempts_per_target")
                  or rules.get("max_attempted_structures"))
        if dry_run:
            print(f"  [dry-run] {run_id}  cap={cap} want={want}")
            continue

        # **원본 CATH 파일을 그대로 보내지 않는다.** 홀드아웃 캠페인이 성공한
        # 이유가 이 staging 이고, 이것을 건너뛰었을 때 RFD3 가 5 개 타겟에서
        # `Residue ... not found in atom array` 로 죽었다.
        pdb_text, staging = staged_target(row["pdb"])
        chain = design_chain(pdb_text)
        request = build_v2_request(plan, pdb_text, source, seed=row["seed"])
        started = time.time()
        print(f"  [{index}/{len(planned)}] {run_id} (cap {cap}, chain {chain}, "
              f"staged CA {staging['n_ca_staged']})", flush=True)
        record = {
            "run_id": run_id, "cohort": row["cohort"],
            "target_id": row["target_id"], "backbone_source": source,
            "seed": row["seed"], "attempt_cap": cap, "wanted": want,
            "design_chain": chain,
            "staging": staging,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            runner.run(request, run_id=run_id)
            record["run_status"] = "ok"
        except Exception as exc:  # 생성 실패도 결과다 - 숨기지 않는다
            record["run_status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"[:400]
            print(f"      실패: {record['error'][:160]}", flush=True)

        pdbs, gate = collect_backbones(output_root, run_id, source,
                                       wanted=want, cutoff=2.0)
        u = len(pdbs)
        # `SOURCE_GENERATION_INFEASIBLE` 은 **결과**다 - cap 까지 시도했는데
        # 2.0 A 를 통과한 것이 없다는 측정이다. 워커가 죽었거나 게이트가
        # 아예 돌지 않은 것은 결과가 아니라 동작 실패이고, 그것을 같은
        # 라벨로 적으면 실패를 과학적 결론으로 둔갑시킨다. 둘을 가른다.
        #
        # 판정 기준은 `run_status` 가 **아니다.** BioEmu 는 cap 까지 다 돌고
        # 0 개가 통과하면 `BackboneContractError` 를 던진다 - "10 개를
        # 원했는데 0 개" 라는 파이프라인의 계약 위반이지, 동결 프로토콜에서는
        # 정상적인 측정 결과다. 그것을 실행 오류로 적으면 사전등록된 결과를
        # 버리게 된다. 기준은 **게이트가 cap 까지 돌았는가** 하나다.
        gate_ran = bool(gate.get("gate_summary_present"))
        attempts = int(gate.get("attempts_used") or 0)
        exhausted = gate_ran and attempts >= cap
        infeasible = bool(u == 0 and exhausted)
        errored = bool(u == 0 and not infeasible)
        record.update({
            "u_accepted": u,
            "backbone_paths": [str(p) for p in pdbs],
            "gate": gate,
            "shortfall": bool(0 < u < want),
            "source_generation_infeasible": infeasible,
            # 재시도 대상. infeasible 과 달리 이것은 고쳐야 하는 상태다.
            "generation_error": errored,
            # 동결 §unequal_units 의 공식. u<10 은 실패가 아니라 사전등록된
            # 상태이므로 분석이 쓸 값을 여기서 같이 남긴다.
            "warmup_for_this_unit": 4 * u,
            "ceiling_for_this_unit": 18 * u,
            "elapsed_s": round(time.time() - started, 1),
            "done": True,
        })
        # 실행 시도를 센다. 생성 예산과 다른 축이며, 모든 unit 에 같은 상한이
        # 걸린다 - 실패한 unit 만 더 돌리면 코호트가 편향된다.
        record["run_attempts"] = attempt_no
        exhausted_attempts = attempt_no >= MAX_RUN_ATTEMPTS
        record["run_attempts_exhausted"] = bool(errored and exhausted_attempts)

        if infeasible:
            tail = "  [SOURCE_GENERATION_INFEASIBLE]"
        elif errored and exhausted_attempts:
            tail = (f"  [생성 오류 · 실행 {attempt_no}/{MAX_RUN_ATTEMPTS} 소진 "
                    "- 확보된 것으로 넘어간다]")
        elif errored:
            tail = f"  [생성 오류 · 실행 {attempt_no}/{MAX_RUN_ATTEMPTS} 재시도 대상]"
        elif u < want:
            tail = "  [shortfall]"
        else:
            tail = ""
        print(f"      accept {u}/{want}{tail}", flush=True)

        # 상한을 다 쓰면 결과가 무엇이든 닫는다. 동결 규칙이 "확보된 것을
        # 그대로 쓴다" 이고, 여기서 더 돌리는 것은 어려운 타겟에만 예산을
        # 더 주는 것이 된다.
        record["done"] = (not errored) or exhausted_attempts
        state["runs"][run_id] = record
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    return state


# ------------------------------------------------- B. 설계 + 용해도, C. 폴딩

def _worker_url(port: int) -> str:
    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    return f"http://{host}:{port}" if host else ""


def _refold_module():
    path = PROJECT_ROOT / "scripts" / "transcoder" / "22_refold_with_artifacts.py"
    spec = importlib.util.spec_from_file_location("refold_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def backbone_chain_id(pdb_text: str) -> str:
    """백본 PDB 의 체인 ID. `fixed_positions` 의 키가 되므로 실제 값이어야 한다.

    RFD3 는 입력의 체인 ID 를 그대로 물려준다. 코호트에서 24 개 타겟 중
    `1pp1X02` 하나만 체인 X 이고, 나머지는 전부 A 다. 여기를 "A" 로 박아 두면
    그 하나에서 ProteinMPNN 이 존재하지 않는 체인을 고정하라는 요청을 받고
    exit=1 로 죽는다 - 실제로 2026-09-13 design 패스에서 tier 세 개가 모두
    그렇게 실패해 그 백본의 후보 12 개가 통째로 비었다. 체인이 하나가 아니면
    조용히 첫 번째를 고르지 않고 세운다: 어느 체인을 고정했는지가 결과에서
    보이지 않게 되는 쪽이 더 나쁘다.
    """
    chains = {line[21] for line in pdb_text.splitlines()
              if line.startswith(("ATOM  ", "HETATM"))}
    if len(chains) != 1:
        raise ValueError(f"백본 체인이 하나가 아니다: {sorted(chains)}")
    return chains.pop()


def stage_design(plan: dict, rows: list[dict], state: dict, *, mpnn_url: str,
                 soluprot_url: str, mpnn_timeout: float) -> list[dict]:
    """보존도 tier 별로 설계하고 SoluProt 을 붙인다. 후보를 고르지 않는다."""
    from pipeline_mcp.clients.proteinmpnn import ProteinMPNNClient
    from pipeline_mcp.clients.soluprot import SoluProtClient
    from rapid_sr.protocol import GATE0_MPNN_SETTINGS

    mpnn = ProteinMPNNClient(runpod=None, endpoint_id=None, gpu_url=mpnn_url,
                             gpu_timeout_s=mpnn_timeout)
    soluprot = SoluProtClient(url=soluprot_url)
    by_target = {(r["cohort"], r["target_id"]): r for r in rows}

    out_path = OUT_DIR / "candidates.json"
    done_rows = (json.loads(out_path.read_text(encoding="utf-8"))
                 if out_path.exists() else [])
    done_backbones = {r["backbone_key"] for r in done_rows}
    all_rows = list(done_rows)

    # `rows` 가 --cohort/--limit-targets 로 좁혀졌을 수 있다. 상태 파일에는
    # 그보다 많은 run 이 들어 있으므로, 이번 호출의 대상만 고른다 - 좁히지
    # 않으면 범위 밖 run 에서 KeyError 로 선다.
    runs = [r for r in state["runs"].values()
            if r.get("u_accepted", 0) > 0
            and (r["cohort"], r["target_id"]) in by_target]
    print(f"[B] 설계 대상 run {len(runs)} (u>0 이고 이번 범위인 것만)", flush=True)

    for run in runs:
        key = (run["cohort"], run["target_id"])
        row = by_target[key]
        n_total, tier_counts = candidates_per_backbone(plan, run["cohort"])
        fixed = tier_fixed_positions(row)

        for bb_index, pdb_path in enumerate(run["backbone_paths"]):
            backbone_key = f"{run['target_id']}|{run['backbone_source']}|b{bb_index}"
            if backbone_key in done_backbones:
                continue
            pdb_text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
            chain_id = backbone_chain_id(pdb_text)
            produced: list[dict] = []
            for tier_key, count in sorted(tier_counts.items()):
                try:
                    _native, samples, _meta = mpnn.design(
                        pdb_text=pdb_text,
                        pdb_name=backbone_key.replace("|", "_"),
                        fixed_positions={chain_id: fixed[tier_key]},
                        use_soluble_model=bool(GATE0_MPNN_SETTINGS["use_soluble_model"]),
                        model_name=str(GATE0_MPNN_SETTINGS["model_name"]),
                        num_seq_per_target=count,
                        batch_size=int(GATE0_MPNN_SETTINGS["batch_size"]),
                        sampling_temp=float(GATE0_MPNN_SETTINGS["sampling_temp"]),
                        seed=int(run["seed"]),
                    )
                except Exception as exc:
                    print(f"  [mpnn 실패] {backbone_key} tier {tier_key}: "
                          f"{type(exc).__name__}: {exc}"[:180], flush=True)
                    continue
                for i, sample in enumerate(s for s in samples if s.sequence):
                    produced.append({
                        "sequence_id": f"{backbone_key}|t{tier_key}|s{i}",
                        "sequence": sample.sequence,
                        # 동결된 지표 스크립트(22_)가 요구하는 열. 이 실험에서
                        # 온도는 변수가 아니라 고정값이다.
                        "temperature": float(GATE0_MPNN_SETTINGS["sampling_temp"]),
                        "conservation_tier": float(tier_key) / 100.0,
                        "backbone_key": backbone_key,
                        "backbone_pdb": pdb_path,
                        "target_id": run["target_id"],
                        "backbone_source": run["backbone_source"],
                        "cohort": run["cohort"],
                    })
            if not produced:
                continue
            from pipeline_mcp.models import SequenceRecord
            records = [SequenceRecord(id=p["sequence_id"], sequence=p["sequence"])
                       for p in produced]
            try:
                scores = soluprot.score(records)
            except Exception as exc:
                print(f"  [soluprot 실패] {type(exc).__name__}: {exc}"[:150],
                      flush=True)
                scores = {}
            for p in produced:
                p["soluprot"] = scores.get(p["sequence_id"])
            all_rows.extend(produced)
            print(f"  {backbone_key}: 후보 {len(produced)}/{n_total}", flush=True)
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(all_rows, ensure_ascii=False),
                                encoding="utf-8")
    return all_rows


def stage_fold(candidates: list[dict], *, colabfold_url: str, workers: int,
               timeout_s: float) -> dict:
    from pipeline_mcp.bio.pdb import dssp_non_loop_positions_by_chain
    from pipeline_mcp.clients.local_http import LocalHTTPAlphaFold2Client

    refold = _refold_module()
    client = LocalHTTPAlphaFold2Client(colabfold_url, None, timeout_s)
    out_csv = OUT_DIR / "af2_order_metric.csv"
    model_dir = OUT_DIR / "af2_models"
    model_dir.mkdir(parents=True, exist_ok=True)

    refs: dict[str, tuple] = {}
    for c in candidates:
        if c["backbone_key"] in refs:
            continue
        text = Path(c["backbone_pdb"]).read_text(encoding="utf-8", errors="replace")
        refs[c["backbone_key"]] = (
            text, dssp_non_loop_positions_by_chain(text),
            hashlib.sha256(text.encode("utf-8")).hexdigest())

    done: dict[str, dict] = {}
    retrying = 0
    if out_csv.exists():
        for r in csv.DictReader(out_csv.open(encoding="utf-8")):
            if r.get("status") == "ok":
                done[r["sequence_id"]] = r
            else:
                retrying += 1
    pending = [c for c in candidates if c["sequence_id"] not in done]
    print(f"[C] 폴딩 전체 {len(candidates)} · 완료 {len(done)} · 남은 {len(pending)}"
          + (f" (이전 실패 {retrying} 재시도)" if retrying else ""), flush=True)

    results = list(done.values())
    lock = threading.Lock()
    started = time.monotonic()
    completed = 0

    # 동결된 지표 스키마에 v2 의 설계 축 두 개를 덧댄다. `22_` 의 FIELDS 를
    # 고치지 않는다 - 그 파일은 v1 지표 경로이고, 여기서 열을 더한다고 해서
    # 그쪽 산출물의 스키마가 달라지면 안 된다. extrasaction="ignore" 라
    # 덧대지 않으면 cohort 와 tier 가 조용히 버려진다.
    fieldnames = list(refold.FIELDS) + ["cohort", "conservation_tier"]

    def flush():
        with out_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

    def work(row):
        nonlocal completed
        entry = refold.fold_one(client, row, refs, model_dir)
        for carry in ("cohort", "backbone_source", "conservation_tier", "soluprot"):
            entry.setdefault(carry, row.get(carry))
        with lock:
            results.append(entry)
            completed += 1
            if completed % 20 == 0 or completed == len(pending):
                rate = (time.monotonic() - started) / completed
                left = (len(pending) - completed) * rate / 60
                print(f"  [C] {completed}/{len(pending)} (~{left:.0f}분 남음)",
                      flush=True)
                flush()

    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, pending))
    flush()
    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"[C] 완료 · ok {ok}/{len(results)} · {out_csv}", flush=True)
    return {"n": len(results), "ok": ok,
            "csv": str(out_csv.relative_to(PROJECT_ROOT))}


# ------------------------------------------------------------------- main

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all",
                        choices=["backbones", "design", "fold", "all"])
    parser.add_argument("--cohort", default="all",
                        choices=["all", "calibration_v2", "confirmatory"])
    parser.add_argument("--sources", default="rfd3,bioemu")
    parser.add_argument("--limit-targets", type=int, default=0,
                        help="연기 시험용. 0 이면 전부.")
    parser.add_argument("--output-root", default="/opt/protein_pipeline/outputs")
    parser.add_argument("--env-file",
                        default="/opt/protein_pipeline/pipeline-mcp/.env")
    parser.add_argument("--mpnn-url", default="")
    parser.add_argument("--colabfold-url", default="")
    parser.add_argument("--soluprot-url", default="")
    parser.add_argument("--mpnn-timeout", type=float, default=1800.0)
    parser.add_argument("--af2-timeout", type=float, default=7200.0)
    parser.add_argument("--fold-workers", type=int, default=0,
                        help="0 이면 PIPELINE_AF2_MAX_WORKERS 를 따른다.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(str(env_file), override=False)

    plan = load_plan()
    msa = json.loads(MSA_MANIFEST.read_text(encoding="utf-8"))
    if int(msa.get("n_done", 0)) != int(msa.get("n_planned", -1)):
        raise SystemExit(
            f"MSA 가 끝나지 않았다 ({msa.get('n_done')}/{msa.get('n_planned')}). "
            "여기서 MSA 를 만들지 않는다.")

    rows = cohort_rows(plan, msa)
    if args.cohort != "all":
        rows = [r for r in rows if r["cohort"] == args.cohort]
    if args.limit_targets > 0:
        rows = rows[: args.limit_targets]
    sources = tuple(s.strip() for s in args.sources.split(",") if s.strip())
    for s in sources:
        if s not in SOURCES:
            raise SystemExit(f"알 수 없는 source: {s!r}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_root = Path(args.output_root)
    mpnn_url = args.mpnn_url or _worker_url(18101)
    colabfold_url = args.colabfold_url or os.environ.get("COLABFOLD_URL", "")
    soluprot_url = args.soluprot_url or os.environ.get("SOLUPROT_URL", "")
    workers = args.fold_workers or int(
        os.environ.get("PIPELINE_AF2_MAX_WORKERS", "1"))

    print(f"타겟 {len(rows)} · source {sources} · fold workers {workers}",
          flush=True)

    state = {"runs": {}}
    if args.stage in {"backbones", "all"}:
        state = stage_backbones(plan, rows, output_root=output_root,
                                sources=sources, dry_run=args.dry_run)
    else:
        p = OUT_DIR / "backbones.json"
        if p.exists():
            state = json.loads(p.read_text(encoding="utf-8"))

    if args.dry_run:
        return 0

    candidates: list[dict] = []
    if args.stage in {"design", "all"}:
        candidates = stage_design(plan, rows, state, mpnn_url=mpnn_url,
                                  soluprot_url=soluprot_url,
                                  mpnn_timeout=args.mpnn_timeout)
    else:
        p = OUT_DIR / "candidates.json"
        if p.exists():
            candidates = json.loads(p.read_text(encoding="utf-8"))

    if args.stage in {"fold", "all"} and candidates:
        stage_fold(candidates, colabfold_url=colabfold_url, workers=workers,
                   timeout_s=args.af2_timeout)

    # 요약. 부족분은 결함이 아니라 결과이므로 눈에 띄게 적는다.
    runs = list(state["runs"].values())
    infeasible = [r["run_id"] for r in runs if r.get("source_generation_infeasible")]
    short = [r["run_id"] for r in runs
             if r.get("shortfall") and not r.get("source_generation_infeasible")]
    summary = {
        "plan": str(PLAN_PATH.relative_to(PROJECT_ROOT)),
        "n_runs": len(runs),
        "n_source_generation_infeasible": len(infeasible),
        "n_shortfall": len(short),
        "source_generation_infeasible": infeasible,
        "shortfall": short,
        "n_candidates": len(candidates),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT_DIR / "campaign_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nrun {len(runs)} · infeasible {len(infeasible)} · "
          f"shortfall {len(short)} · 후보 {len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

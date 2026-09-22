#!/usr/bin/env bash
# 계층형 배분 confirmatory 코호트를 MSA -> backbone -> design -> fold 로 돌린다.
#
# 규칙은 `docs/specs/hierarchical-confirmatory-prespec.md` (v1.3) 에 동결돼
# 있고 숫자는 `hier_confirmatory_plan.json` 에서 읽는다. 여기에 동결값은 없다.
#
# **폴딩만 파일럿 결과에 걸려 있다.** MSA·백본·설계는 어느 쪽이든 필요하고
# 상대적으로 싸다. 8,568 fold(약 6 일)는 파일럿이 깊이 가정을 확인했을 때만
# 쓴다 - 사전지정 §6 의 판정 규칙이다.
set -u
cd /opt/protein_pipeline-work
PY=/opt/protein_pipeline/venv/bin/python
LOG=logs/hier
PLAN=public_data/benchmark/gate0/hier_confirmatory_plan.json
MANIFEST=public_data/benchmark/gate0/hier_msa_manifest.json
OUTDIR=public_data/benchmark/gate0/hier_confirmatory
mkdir -p "$LOG" "$OUTDIR"

# MSA 클라이언트는 URL 을 RAPID_GPU_HOST 에서 만든다 (50_full_msa.py:309).
# 비어 있으면 http://:18106 이 되어 0.0 s 만에 endpoint_status=failed 로
# 떨어진다 - 자격증명 문제가 아니라 호스트가 없는 것이다. 2026-09-21 에
# 실제로 이렇게 한 번 헛돌았다.
export RAPID_GPU_HOST="${RAPID_GPU_HOST:-211.188.35.221}"

# 백본·설계 단계는 .env 가 필요하다. `.env` 는 공백이 든 값이 있어 `source`
# 로 읽을 수 없다 - 첫 '=' 로만 자른다 (docs/restart_after_changes.md 정본).
ENV_FILE=/opt/protein_pipeline/pipeline-mcp/.env
if [ -f "$ENV_FILE" ]; then
  while IFS= read -r raw; do
    case "$raw" in ''|'#'*) continue;; *'='*) ;; *) continue;; esac
    export "${raw%%=*}=${raw#*=}"
  done < "$ENV_FILE"
fi

step () { echo "=== $1 $(date -u +%FT%TZ)"; }

# ---------------------------------------------------------------- M. MSA
step "[M] MSA"
# 이미 돌고 있으면 끝나기를 기다린다. 두 프로세스가 같은 A3M 디렉터리를
# 건드리면 부분 파일이 남는다.
# 패턴을 인터프리터 경로까지 포함해 좁힌다. "50_full_msa.py --cohorts ..."
# 만으로 잡으면 그 문자열을 명령줄에 담은 **감시용 셸**까지 걸려서 드라이버가
# 영원히 기다린다 - 2026-09-22 에 실제로 그렇게 멈췄다.
while pgrep -f "venv/bin/python scripts/transcoder/50_full_msa\.py" >/dev/null 2>&1; do
  sleep 60
done
# 파일이 있다는 것만으로 건너뛰지 않는다 - 중간에 죽으면 부분 매니페스트가
# 남는다 (2026-09-21 에 n_done=1/34 로 남았다). 완결 여부로 판단한다.
complete () {
  [ -f "$MANIFEST" ] && $PY - "$MANIFEST" <<'PYC' >/dev/null 2>&1
import json,sys
d=json.loads(open(sys.argv[1]).read())
sys.exit(0 if int(d.get("n_done",0))==int(d.get("n_planned",-1)) else 1)
PYC
}
if ! complete; then
  $PY scripts/transcoder/50_full_msa.py --cohorts hier_confirmatory \
      --out "$MANIFEST" --workers 4 >>"$LOG/conf_msa.log" 2>&1
fi
$PY - "$MANIFEST" <<'PYCHK' || { echo "MSA 가 완결되지 않았다. 멈춘다."; exit 1; }
import json,sys,collections
d=json.loads(open(sys.argv[1]).read())
c=collections.Counter(t.get("classification") for t in d["targets"])
print("  MSA 판정", dict(c))
if int(d.get("n_done",0)) != int(d.get("n_planned",-1)):
    sys.exit(1)
PYCHK

# --------------------------------------------------- A-B. 백본과 서열 설계
step "[A] 백본 생성"
$PY scripts/transcoder/52_v2_multisource_campaign.py \
    --plan "$PLAN" --msa-manifest "$MANIFEST" --out-dir "$OUTDIR" \
    --sources rfd3 --stage backbones >>"$LOG/conf_backbones.log" 2>&1

step "[B] 서열 설계"
$PY scripts/transcoder/52_v2_multisource_campaign.py \
    --plan "$PLAN" --msa-manifest "$MANIFEST" --out-dir "$OUTDIR" \
    --sources rfd3 --stage design >>"$LOG/conf_design.log" 2>&1

# ------------------------------------------------- 게이트. 파일럿 판정
step "[G] 파일럿 게이트"
$PY - <<'PYGATE'
import json,os,sys
p="public_data/benchmark/gate0/depth_scaling.json"
if not os.path.exists(p):
    print("  파일럿 분석이 아직 없다. 폴딩을 시작하지 않는다."); sys.exit(2)
c=json.load(open(p))["contrasts"].get("greedy_fill|B80")
if not c or "delta" not in c:
    print("  파일럿 주 비교가 없다. 폴딩을 시작하지 않는다."); sys.exit(2)
ok = c["excludes_zero"] and c["delta"] > 0
print(f"  D(42)-D(18) = {c['delta']:+.3f} "
      f"[{c['ci95'][0]:+.3f},{c['ci95'][1]:+.3f}] · unit {c['n_units']}")
print("  판정:", "양성 -> 폴딩 진행" if ok else "미확인/음성 -> 폴딩 보류")
sys.exit(0 if ok else 2)
PYGATE
GATE=$?
if [ "$GATE" -ne 0 ]; then
  echo "=== 폴딩을 시작하지 않았다. 백본과 설계는 준비돼 있다."
  echo "    사람이 판단해 아래를 직접 부르면 폴딩만 이어서 돈다:"
  echo "    $PY scripts/transcoder/52_v2_multisource_campaign.py \\"
  echo "        --plan $PLAN --msa-manifest $MANIFEST --out-dir $OUTDIR \\"
  echo "        --sources rfd3 --stage fold --fold-workers 4"
  exit 0
fi

# ---------------------------------------------------------------- C. 폴딩
step "[C] 폴딩 8,568"
$PY scripts/transcoder/52_v2_multisource_campaign.py \
    --plan "$PLAN" --msa-manifest "$MANIFEST" --out-dir "$OUTDIR" \
    --sources rfd3 --stage fold --fold-workers 4 >>"$LOG/conf_fold.log" 2>&1
step "[C] 폴딩 종료"

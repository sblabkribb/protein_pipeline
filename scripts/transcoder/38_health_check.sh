#!/usr/bin/env bash
# 격자·체인 건강 점검. **문제가 있을 때만** 한 줄씩 출력한다.
#
# 왜 필요한가
# -----------
# 이 세션에서 세 번 잘못 진단했다. pgrep 이 전이 프로세스를 잡아 "죽었다" 고
# 판단해 중복 실행을 만들었고(클라이언트 8개가 업스트림 4개에 붙어 처리율이
# 절반이 됐다), 방화벽이 막은 포트를 "워커가 매달렸다" 고 읽었고, ps 를 head 로
# 잘라 프로세스 수를 잘못 셌다. 사람이 눈으로 보는 것보다 규칙으로 세는 게 낫다.
#
# 침묵 = 정상. 출력이 있으면 그것만 조치한다.
set -uo pipefail
cd /opt/protein_pipeline-work

GRID_CSV=public_data/benchmark/gate0/holdout_grid/af2_order_metric.csv
GRID_MODELS=public_data/benchmark/gate0/holdout_grid/models

# PPID 1 인 실제 프로세스만 센다. 전이 래퍼를 잡지 않는다.
count_real () { ps -eo pid,ppid,cmd --no-headers | awk -v pat="$1" '$2==1 && $0 ~ pat' | wc -l; }
pids_real ()  { ps -eo pid,ppid,cmd --no-headers | awk -v pat="$1" '$2==1 && $0 ~ pat {print $1}'; }

n_grid=$(count_real '26_holdout_grid')
n_chain=$(count_real '30_after_grid_chain')

# 1. 중복 실행. 같은 CSV 에 두 writer 가 붙으면 서로를 덮어쓴다.
if [ "$n_grid" -gt 1 ]; then
  echo "PROBLEM 격자 프로세스 $n_grid 개 (중복): $(pids_real '26_holdout_grid' | tr '\n' ' ')"
fi
if [ "$n_chain" -gt 1 ]; then
  echo "PROBLEM 후속 체인 $n_chain 개 (중복): $(pids_real '30_after_grid_chain' | tr '\n' ' ')"
fi

# 2. 격자가 끝났는데 체인이 없으면 후속 작업이 실행되지 않는다.
done_rows=$(( $(wc -l < "$GRID_CSV" 2>/dev/null || echo 1) - 1 ))
ok_rows=$(awk -F, 'NR>1 && $0 ~ /,ok,/ {n++} END{print n+0}' "$GRID_CSV" 2>/dev/null || echo 0)
if [ "$n_grid" -eq 0 ]; then
  if [ "$ok_rows" -lt 1700 ]; then
    echo "PROBLEM 격자 프로세스 없음 · ok $ok_rows/1728 (미완료 상태에서 중단)"
  elif [ "$n_chain" -eq 0 ]; then
    echo "PROBLEM 격자 완료(ok $ok_rows)인데 후속 체인이 없다 - 후속 작업 미실행"
  fi
fi

# 3. 정체. 모델 파일이 30 분간 늘지 않으면 실제로 멈춘 것이다.
if [ "$n_grid" -ge 1 ] && [ -d "$GRID_MODELS" ]; then
  recent=$(find "$GRID_MODELS" -name '*.pdb.gz' -newermt '-30 minutes' 2>/dev/null | wc -l)
  if [ "$recent" -eq 0 ]; then
    echo "PROBLEM 격자가 돌고 있는데 최근 30분간 새 모델 0개 (정체)"
  fi
fi

# 4. 실패율. 5% 를 넘으면 워커나 경합 문제다.
if [ "$done_rows" -gt 100 ]; then
  failed=$(( done_rows - ok_rows ))
  pct=$(( failed * 100 / done_rows ))
  if [ "$pct" -ge 5 ]; then
    echo "PROBLEM 격자 실패율 ${pct}% ($failed/$done_rows) - 5% 임계 초과"
  fi
fi

# 5. 쓰기 유실. 모델 파일이 CSV 행보다 많으면 flush 가 덮였다는 신호다.
if [ -d "$GRID_MODELS" ]; then
  n_models=$(find "$GRID_MODELS" -name '*.pdb.gz' | wc -l)
  if [ "$n_models" -gt $(( done_rows + 20 )) ]; then
    echo "PROBLEM 모델 $n_models 개 > CSV $done_rows 행 +20 - 쓰기 유실 의심"
  fi
fi

# 6. 워커. LB 는 외부에 열려 있고 개별 업스트림은 ACG 가 막는다. LB 만 본다.
if ! curl -s -o /dev/null -m 10 "http://${RAPID_GPU_HOST:-127.0.0.1}:18160/healthz"; then
  echo "PROBLEM ColabFold LB(18160) 무응답"
fi

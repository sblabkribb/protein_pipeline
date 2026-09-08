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
# 완료 여부는 행 수로 추측하지 않는다. 격자는 끝날 때 manifest 를 쓰므로
# 그 파일이 유일한 완료 마커다. 행 수 임계값(<1700)을 쓰던 예전 판정은
# 실패 51 건으로 정상 종료한 격자를 "미완료 중단" 으로 잘못 불렀다.
GRID_MANIFEST=public_data/benchmark/gate0/holdout_grid/manifest.json

# 최근 N 분 안에 생긴 파일 수. find -newermt 는 이 시스템에서 믿을 수 없다
# (bfs 가 최근 30분 0 개인 디렉터리에 10 개를 보고했다). mtime 을 직접 센다.
recent_files () {
  python3 -c "
import pathlib, sys, time
d, pattern, minutes = pathlib.Path(sys.argv[1]), sys.argv[2], float(sys.argv[3])
cut = time.time() - minutes * 60
print(sum(1 for f in d.glob(pattern) if f.stat().st_mtime >= cut)) if d.is_dir() else print(0)
" "$1" "$2" "$3" 2>/dev/null || echo -1
}

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
  if [ ! -f "$GRID_MANIFEST" ]; then
    echo "PROBLEM 격자 프로세스 없음 · manifest 없음 · ok $ok_rows (완료 전 중단)"
  # 완료 마커는 체인 마지막 줄의 "[HH:MM] 완료" 다. 맨 '완료' 로 찾으면
  # 진행 로그의 "완료 819" 에 걸려서, 체인이 죽어도 조용해진다 (실제로 그랬다).
  elif [ "$n_chain" -eq 0 ] \
       && ! grep -qE '^\[[0-9]{2}:[0-9]{2}\] 완료$' /tmp/after_grid.log 2>/dev/null; then
    # 어디까지 갔는지 함께 낸다. 이전 체인은 bash 구문 오류로 조용히 죽었고
    # 로그를 사람이 읽을 때까지 아무도 몰랐다. 마지막 단계가 곧 조치 지점이다.
    stage=$(grep -o '=====* [^=]* =====*' /tmp/after_grid.log 2>/dev/null \
            | tail -1 | tr -d '=' | sed 's/^ *//;s/ *$//')
    echo "PROBLEM 격자 완료(ok $ok_rows)인데 후속 체인이 없다 - 마지막 단계: ${stage:-없음}"
  fi
fi

# 3. 정체. 모델 파일이 30 분간 늘지 않으면 실제로 멈춘 것이다.
# 격자는 두 단계다: 먼저 백본 72 개의 서열을 만들고(모델이 안 나온다), 그 다음
# 접는다. 생성 단계에서 "모델 0 개" 는 정상인데 예전 판정은 그것을 정체로 불렀다
# (재시도 실행에서 실제로 오경보가 났다). 이 실행에서 접기가 시작됐는지를 먼저
# 본다 - 프로세스 시작보다 새로운 모델이 하나라도 있으면 접는 중이다.
if [ "$n_grid" -ge 1 ] && [ -d "$GRID_MODELS" ]; then
  grid_age=$(ps -eo etimes,ppid,cmd --no-headers \
             | awk '$2==1 && /26_holdout_grid/ {print $1; exit}')
  if [ -n "$grid_age" ]; then
    since_start=$(recent_files "$GRID_MODELS" '*.pdb.gz' "$((grid_age / 60 + 1))")
    if [ "$since_start" -eq 0 ]; then
      # 아직 접기 전이다. 다만 한 시간이 넘도록 시작을 못 했으면 그건 문제다.
      if [ "$grid_age" -gt 3600 ]; then
        echo "PROBLEM 격자가 ${grid_age}초째 도는데 이번 실행의 모델이 0개 (서열 생성에서 멈춤?)"
      fi
    elif [ "$(recent_files "$GRID_MODELS" '*.pdb.gz' 30)" -eq 0 ]; then
      echo "PROBLEM 격자가 접는 중인데 최근 30분간 새 모델 0개 (정체)"
    fi
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

#!/usr/bin/env bash
#
# 용량이 큰 구조 파일을 Zenodo 등 보관소에 올릴 묶음으로 만든다.
#
# 저장소에는 통계 분석에 필요한 입력(약 28MB)만 두고, 구조 분산 진단에만 쓰이는
# 예측 구조 7,722개는 이 묶음으로 따로 배포한다.
#
# 사용법:
#   bash scripts/make_zenodo_package.sh [출력_디렉터리]
#
# 업로드는 하지 않는다. 묶음과 체크섬만 만든다.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="${1:-dist/zenodo}"
SRC="public_data/benchmark/gate0/hier_confirmatory/af2_models"
NAME="rapid-hier-confirmatory-af2-models"

[[ -d "$SRC" ]] || { echo "없는 경로: $SRC"; exit 1; }
mkdir -p "$OUT"

n=$(find "$SRC" -name '*.pdb.gz' | wc -l)
echo "구조 파일 $n개를 묶는다."

# .pdb.gz 는 이미 압축되어 있으므로 tar 만 쓴다. 재현 시 경로가 그대로
# 복원되도록 저장소 기준 상대 경로를 유지한다.
tar -cf "$OUT/$NAME.tar" \
    -C public_data/benchmark/gate0/hier_confirmatory af2_models

cat > "$OUT/README.md" <<'EOF'
# RAPID — 후속 평가의 예측 구조 파일

이 묶음은 원고의 후속 평가(계획 34개 표적, 분석 32개)에서 생성한 AlphaFold2/
ColabFold 예측 구조 7,722개다. 파일 이름은 `<표적>_<생성원>_<백본>_<온도>_<표본>.pdb.gz`
형식이며, 구조예측 격자 `af2_order_metric.csv` 의 `sequence_id` 와 대응한다.

## 쓰임

통계 분석(선택 규칙 비교, 정규화 회수율, EFBC)에는 이 파일이 필요하지 않다.
저장소에 포함된 격자 CSV 와 후보 목록만으로 재실행된다. 이 묶음은 보충자료
S5.2 의 구조 분산 진단을 다시 계산할 때만 쓴다.

## 복원

    tar -xf rapid-hier-confirmatory-af2-models.tar \
        -C <저장소>/public_data/benchmark/gate0/hier_confirmatory/

풀고 나면 다음으로 진단을 다시 만들 수 있다.

    python3 scripts/benchmark/41_structural_dispersion.py

## 무결성

같은 디렉터리의 `SHA256SUMS` 로 확인한다.

    sha256sum -c SHA256SUMS

## 분석 코드와 절차

코드와 통계 입력, 실행 절차는 함께 공개된 저장소에 있다. 재현 범위와 환경은
저장소의 `docs/reproducibility.md` 를 따른다.
EOF

cp public_data/benchmark/gate0/repro_manifest.json "$OUT/" 2>/dev/null || true

( cd "$OUT" && sha256sum "$NAME.tar" README.md \
    $( [[ -f repro_manifest.json ]] && echo repro_manifest.json ) > SHA256SUMS )

echo
ls -la "$OUT"
echo
echo "업로드하지 않았다. 묶음만 만들었다: $OUT"

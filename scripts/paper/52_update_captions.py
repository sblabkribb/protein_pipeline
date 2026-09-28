#!/usr/bin/env python3
"""그림을 다시 그렸으므로 캡션을 그림에 맞춘다.

패널 구성이 바뀐 것, 색 인코딩이 바뀐 것, 그리고 **캡션에도 남아 있던
"(A)…(C)" 댕글링 참조**를 고친다. 그림에서 그 이름을 고쳐도 캡션이 옛 이름을
부르면 독자는 여전히 찾지 못한다.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

OPT = Path("/opt")
BACKUP = OPT / "archive" / "backups"
CAP = re.compile(r"^\s*(보충그림\s*S?\d+|그림\s*\d+)\s*[.．]")

NEW = {
"용해성 지향 단백질 재설계 파이프라인.docx": {
 "그림 3": (
  "그림 3. 구조 컨텍스트 3-arm 비교(9 CATH 표적). 표적당 약 10,000개 pool 에서 "
  "Top-20 을 고른 뒤 그 20개 집합에서 잰 값이다. 다양성은 1 − 평균 쌍대 동일성이며 "
  "정렬 없이 같은 위치끼리 비교한다(§3.4). (A) arm 별 다양성. 점은 표적 하나, 회색 "
  "선은 같은 표적을 세 arm 에서 이은 것, 굵은 가로선과 숫자는 평균이다. (B) 앙상블·"
  "대리모델을 기준으로 한 짝지은 차이와 표적 부트스트랩 95% 구간(2,000회, seed "
  "20260921). 단일 backbone 대비는 +0.197 [+0.146, +0.246] 로 9/9 상승하지만, "
  "앙상블·무작위 대비는 −0.036 [−0.090, +0.008] 로 구별되지 않는다 — 다양성을 "
  "만드는 것은 앙상블이지 대리모델이 아니다. (C) 같은 대비의 부수 지표. pLDDT 는 "
  "낮아지고 SoluProt 은 변하지 않는다. 표시 편의상 pLDDT 는 10 으로 나눴다."),
 "그림 4": (
  "그림 4. 실험 3 — 수확과 탐색 폭(RFD3 confirmatory, B=80). (A) 여지 회수율"
  "(균등·무작위 0%, oracle 100%)이다. 기술 통계이므로 구간을 붙이지 않았고, 막대 "
  "길이만으로 정책을 비교하지 않는다. (B) 같은 자료의 정책 간 차이와 표적 클러스터 "
  "부트스트랩 95% 구간. 주 비교인 `RF + 백본 배분 − RF 순위화만`은 +0.25 "
  "[−0.58, +1.25] 로 0 을 포함한다 — (A) 의 50.5% 와 52.6% 차이는 검출되지 "
  "않았다는 뜻이다. 나머지 세 대비는 0 을 제외한다. (C) 선택 40개가 닿은 서로 다른 "
  "백본 수(가용 10). 배분은 2.0개 백본에 91%를 몰아넣는 반면 백본을 모르는 RF 는 "
  "6.8개에 퍼뜨린다. 즉 두 정책은 수확이 같고 폭만 다르다."),
 "그림 5": (
  "그림 5. 깊이 확장 파일럿. 세로축 D 는 여지 회수율 기준으로 greedy 가 RF-only "
  "보다 얼마나 더 회수했는지다. 점 하나가 표적 하나이고 선은 같은 표적을 두 깊이에서 "
  "이었다(파랑은 깊이가 늘며 D 가 커진 표적, 주황은 줄어든 표적. 범례 참조). 굵은 "
  "가로선은 평균이다. 왼쪽이 주 비교(greedy_fill)이고 오른쪽은 36_ 과 같은 정책"
  "(greedy_thompson)으로, 두 정책 모두 깊이가 늘자 D 가 줄었다. 깊이 42 에서 주 "
  "정책의 평균 D 는 −0.010 으로 0 선에 붙는다."),
},
"RAPID_ResearchNote_KR_v1.0_polished.docx": {
 "그림 1": (
  "그림 1. RAPID의 후보 생성·선별 흐름과 본 보고서의 주 분석. 학습 경로는 초기 30개 "
  "AF2/ColabFold 라벨을 같은 총 folding 예산 B 안에서 사용하고, ProteinMPNN "
  "기준선은 생성 시 이미 얻는 NLL 점수로 B개 후보를 직접 선택한다. 주 분석 1은 "
  "67표적의 고유 서열 pLDDT 순위화이고, 주 분석 2는 v2 다중생성원 stored-candidate "
  "cohort 의 same-budget joint-pass 비교다. 초기 11-target RFD3 pilot 은 "
  "Supplement 에서만 보조적으로 보고한다."),
 "그림 2": (
  "그림 2. 표적별 surrogate의 예측 신호와 실용적 추가가치를 분리한 핵심 결과. "
  "(A) 67표적 고유 서열 pLDDT 순위화에서 RF−무작위, RF−Ridge, RF−XGBoost 의 "
  "Top-20 recall 차이다. local calibration 이 후보를 변별하는지를 평가한다. "
  "(B) v2 multi-source 후보 풀의 B=80 same-budget 비교에서 RF−무작위와 "
  "RF−ProteinMPNN 의 joint-pass 확보량 차이를 source 별로 보여준다. 두 패널은 서로 "
  "다른 종점과 코호트를 쓰므로 효과크기를 직접 비교하지 않는다. 패널 B 의 양의 차이는 "
  "초기 30개 라벨 비용을 포함하고도 RF 가 더 많은 joint-pass 후보를 확보했다는 뜻이며, "
  "다중성 보정 여부는 그림 3 과 표 2 에서 별도로 제시한다. 가로 막대는 모두 95% CI 다."),
 "그림 3": (
  "그림 3. v2 stored-candidate triage의 source별 same-budget 비교. 점은 RF와 "
  "기준선 사이의 평균 joint-pass 확보량 차이, 수염은 개별 95% CI 다. 별표는 그 대비가 "
  "두 대비 × 네 예산점 = 8개 검정 family 보정(99.375% CI) 후에도 0 을 제외한다는 "
  "표시다. RF−ProteinMPNN 은 B=40 에서 두 source 모두 0 을 포함하지만 B=60·80·100 "
  "에서는 명목 95% CI 가 0 위에 있다. 그러나 보정하면 근거가 유지되는 조건은 RFD3 "
  "B=100 과 BioEmu B=80·100 으로 줄어든다. 따라서 이 그림은 “RF가 항상 우월하다”보다 "
  "“추가 라벨의 가치는 예산과 source 에 따라 달라진다”는 것으로 해석해야 한다."),
},
"RAPID_ResearchNote_supplement_KR_v1.0_polished.docx": {
 "보충그림 S1": (
  "보충그림 S1. 9개 CATH 표적의 구조 컨텍스트 3-arm 분포. 상자는 사분위, 다이아몬드는 "
  "평균, 점은 표적 하나다. 본문 그림 3 이 대비와 구간을 내는 데 반해 이 그림은 퍼짐을 "
  "그대로 보여준다. 다양성이 가장 높은 것은 대리모델 arm 이 아니라 무작위 선택 arm 이다."),
},
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    for fname, table in NEW.items():
        path = OPT / fname
        doc = Document(str(path))
        hits = []
        for p in doc.paragraphs:
            t = p.text.strip()
            m = CAP.match(t)
            if not m:
                continue
            key = m.group(1).replace("  ", " ")
            if key not in table:
                continue
            text = table[key]
            for r in list(p.runs):
                r._r.getparent().remove(r._r)
            cut = CAP.match(text).end()
            for chunk, bold in ((text[:cut], True), (text[cut:], False)):
                r = p.add_run(chunk)
                r.bold = bold
                r.font.size = Pt(10)
                r.font.name = "맑은 고딕"
                r._element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")
            hits.append(key)
        print(f"\n=== {fname}\n    갱신 {hits}")
        missing = set(table) - set(hits)
        if missing:
            print(f"    !! 찾지 못함 {sorted(missing)}")
        if not a.dry_run:
            BACKUP.mkdir(parents=True, exist_ok=True)
            bak = BACKUP / (path.name + ".bak-captions")
            if not bak.exists():
                shutil.copy2(path, bak)
            doc.save(str(path))
    print("\n(dry-run)" if a.dry_run else "\n저장 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

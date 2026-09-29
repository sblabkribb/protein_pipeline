#!/usr/bin/env python3
"""확증 결과가 나오면서 낡은 문장들을 고친다.

네 문서가 "34표적 확증 코호트는 실행하지 않았다" 를 전제로 쓰여 있었다.
그 코호트를 실제로 돌렸으므로 그 문장들은 이제 결과 절과 모순된다.

주의해서 구분한 것
    v2 adaptive-allocation confirmatory 가 BLOCKED / NOT_EVALUABLE 이었다는
    연구노트의 서술은 **여전히 참이다.** 그것은 v2 코호트의 다른 분석이고,
    이번에 돌린 것은 34표적 hierarchical confirmatory 다. 그래서 그 문장을
    고치지 않고 포인터만 덧붙인다.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from docx import Document

OPT = Path("/opt")
BACKUP = OPT / "archive" / "backups"

EDITS = {
"용해성 지향 단백질 재설계 파이프라인.docx": [
 ("계획했던 34표적·8,568 fold 전향 확증 코호트는 자동으로 시작하지 않는다",
  "사전지정 §6 의 판정 규칙에 따라 이 결과는 “확인되지 않음” 이고, 계획했던 "
  "34표적 전향 확증 코호트는 자동으로 시작하지 않는다. 그 뒤 사람이 구간 축소를 "
  "목적으로 실행을 승인했고(사전지정 v1.6), 그 코호트의 설계는 §3.5, 결과는 "
  "§4.5–§4.7 에 있다."),
 ("coverage 를 목적함수로 두고 수확을 가드레일로 쓰는 설계는 아직 평가 중이다",
  "다만 배분 자체가 무용하다는 결론은 아니다. 여기서 시험한 것은 수확을 "
  "목적함수로 둔 정책이고, coverage 를 목적함수로 두고 수확을 가드레일로 쓰는 "
  "설계는 별도 종점으로 평가했다. 수확 목적의 집중이 이득 없이 폭을 좁혔다는 이 "
  "관찰은 그 설계 전환의 동기와 같은 방향이며, 그 평가의 종점·정책·가드레일은 "
  "결과를 보기 전에 동결했다. 결과는 §4.7 이다 — 그 정책은 제 목적함수인 EFBC "
  "에서는 네 예산점 모두 이겼으나 채택 가드레일을 넘지 못했다."),
 ("계획했던 34표적 전향 확증 코호트는 사전지정된 게이트를 통과하지 못해 실행하지 않았다",
  "이 판정의 근거는 비대칭이다. 서열 순위화가 작동한다는 쪽은 67표적과 "
  "29 target×source·생성원 2개에서 확인되어 튼튼하다. 배분에 이득이 없다는 쪽은 "
  "파일럿 단계에서 8 unit(주 비교)과 5 unit(깊이)에 근거해 얇았고, 그래서 사람이 "
  "구간 축소를 목적으로 34표적 확증 코호트의 실행을 승인했다. 그 코호트에서 주 "
  "종점은 +0.086 [−0.059, +0.212] 로 여전히 0 을 포함했으나 구간은 눈에 띄게 "
  "좁아졌다(자격 16 unit, 설계 검정력 73%). 네 가지 다른 물음(배분 추가·되먹임·"
  "깊이 확장·coverage 목적)에서 일관되게 0 또는 채택 미달이 나왔고 탐색 폭 축소는 "
  "방향이 분명하다. 다만 자격 unit 이 사전지정 경계값에 걸쳤으므로 이 음성을 "
  "“효과 없음” 으로 쓰지 않는다."),
],
"용해성 지향 단백질 재설계 파이프라인_supplementary.docx": [
 ("계획했던 34표적·8,568 fold 확증 코호트는 사전지정 §6 의 게이트를 통과하지 못해 실행하지 않았다",
  "계획했던 34표적 확증 코호트는 사전지정 §6 의 게이트를 통과하지 못했고, 그 뒤 "
  "사람이 구간 축소를 목적으로 실행을 승인했다(v1.6). 실제로 수행한 것은 표적당 "
  "백본 6 개·백본당 서열 42 개의 34표적 격자이며, 백본 수용이 0 인 2 표적을 빼면 "
  "실효 32 표적이고 폴딩 7,728 건 중 7,722 건이 성공했다. 결과는 본문 §4.5–§4.7 "
  "이다. EFBC 와 coverage 종점은 이 코호트에서 처음 계산했다 — 앞선 분석들이 EFBC "
  "계산을 금지한 것은 그 분석들의 범위 제한이었고, 이 코호트의 사전지정"
  "(docs/specs/coverage-preserving-prespec.md)이 그 점을 명시한다. calibration "
  "코호트는 여전히 정책 비교에 쓰지 않았다."),
],
"RAPID_ResearchNote_KR_v1.0_polished.docx": [
 ("별도 v2 adaptive-allocation confirmatory가 RFD3에서 BLOCKED",
  None),   # 뒤에 문장을 덧붙인다
],
"RAPID_ResearchNote_supplement_KR_v1.0_polished.docx": [
 ("따라서 confirmatory allocation 효과는 보고하지 않는다",
  None),
],
}

APPEND = {
"RAPID_ResearchNote_KR_v1.0_polished.docx":
  " 그 뒤 별도의 34표적 코호트에서 배분 축의 확증 분석이 수행되었다. 본 연구노트의 "
  "범위 밖이므로 여기서 판정에 쓰지 않으며, 설계와 결과는 파이프라인 보고서에 있다.",
"RAPID_ResearchNote_supplement_KR_v1.0_polished.docx":
  " 그 판단은 v2 코호트에 대한 것이며 지금도 유효하다. 이와 별도로 34표적 "
  "hierarchical confirmatory 코호트(RFD3 단독, 표적당 백본 6, 백본당 서열 42, 폴딩 "
  "7,728)가 이후 수행되었고 그 결과는 파이프라인 보고서 §4.5–§4.7 에 보고한다. "
  "주 종점은 +0.086 [−0.059, +0.212] 로 0 을 포함했다. 본문의 stored-candidate "
  "triage 와는 여전히 다른 질문이다.",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    for fname, edits in EDITS.items():
        path = OPT / fname
        doc = Document(str(path))
        done = []
        for needle, replacement in edits:
            hit = next((p for p in doc.paragraphs if needle in p.text), None)
            if hit is None:
                print(f"  !! 못 찾음: {needle[:44]}")
                continue
            if replacement is None:                    # 덧붙이기
                tail = APPEND[fname]
                if tail.strip()[:20] in hit.text:
                    print("  (이미 덧붙임)")
                    continue
                r = hit.runs[-1] if hit.runs else hit.add_run("")
                r.text = r.text + tail
                done.append("덧붙임")
            else:                                      # 문단 교체
                if hit.runs:
                    hit.runs[0].text = replacement
                    for r in hit.runs[1:]:
                        r.text = ""
                else:
                    hit.add_run(replacement)
                done.append("교체")
        print(f"=== {fname}: {done}")
        if not a.dry_run and done:
            BACKUP.mkdir(parents=True, exist_ok=True)
            bak = BACKUP / (path.name + ".bak-prestale")
            if not bak.exists():
                shutil.copy2(path, bak)
            doc.save(str(path))
    print("(dry-run)" if a.dry_run else "저장 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

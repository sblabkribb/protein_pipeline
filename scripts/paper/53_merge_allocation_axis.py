#!/usr/bin/env python3
"""배분 축 확증 결과를 파이프라인 보고서에 병합한다.

`docs/notes/allocation-axis-draft.md` 의 내용을 문서 체재에 맞춰 옮긴다.
초안의 코드블록은 monospace 로 넣지 않고 **표**로 만든다 - 전부 수치표이고,
문서의 다른 절이 표를 쓰는 방식과 맞춘다.

삽입 위치
    3.5 - 3.7   "4. 결과" 앞
    4.5 - 4.7   "5. 논의" 앞
    5.4         "6. 한계" 앞
    한계 추가   "7. 결론" 앞
    결론 추가   "참고문헌" 앞

한 번만 돌린다. 이미 §3.5 가 있으면 멈춘다.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt

OPT = Path("/opt")
DOC = OPT / "용해성 지향 단백질 재설계 파이프라인.docx"
FIG = Path("/opt/protein_pipeline-work/figures/submission")
BACKUP = OPT / "archive" / "backups"

H2, H3, BODY = 14.0, 12.0, 10.0


# ------------------------------------------------------------------ 작성기

class Builder:
    """문단·표·그림을 만들어 두었다가 기준 문단 앞으로 한꺼번에 옮긴다."""

    def __init__(self, doc):
        self.doc = doc
        self.body_w = (doc.sections[0].page_width - doc.sections[0].left_margin
                       - doc.sections[0].right_margin)
        self.made = []

    def _p(self, text, size, bold, style="Normal"):
        p = self.doc.add_paragraph()
        p.style = self.doc.styles[style]
        r = p.add_run(text)
        r.bold = bold
        r.font.size = Pt(size)
        self.made.append(p._p)
        return p

    def h2(self, t):
        return self._p(t, H2, True)

    def h3(self, t):
        return self._p(t, H3, True)

    def body(self, t):
        return self._p(t, BODY, False)

    def caption(self, text):
        p = self.doc.add_paragraph()
        p.style = self.doc.styles["Caption"]
        cut = text.index(".") + 1
        for chunk, bold in ((text[:cut], True), (text[cut:], False)):
            r = p.add_run(chunk)
            r.bold = bold
            r.font.size = Pt(10)
            r.font.name = "맑은 고딕"
            r._element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")
        self.made.append(p._p)
        return p

    def table(self, rows):
        t = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, row in enumerate(rows):
            for j, cell in enumerate(row):
                c = t.cell(i, j)
                c.text = ""
                r = c.paragraphs[0].add_run(str(cell))
                r.font.size = Pt(9)
                r.bold = (i == 0)
        self.made.append(t._tbl)
        return t

    def figure(self, name):
        from PIL import Image
        import io
        src = FIG / f"{name}.png"
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(str(src), width=self.body_w)
        w, h = Image.open(io.BytesIO(src.read_bytes())).size
        sh = self.doc.inline_shapes[-1]
        sh.width, sh.height = self.body_w, Emu(int(self.body_w * h / w))
        self.made.append(p._p)
        return p

    def flush_before(self, anchor_p):
        for el in self.made:
            anchor_p._p.addprevious(el)
        self.made = []


def find(doc, prefix):
    for p in doc.paragraphs:
        if p.text.strip().startswith(prefix):
            return p
    raise SystemExit(f"기준 문단을 찾지 못했다: {prefix!r}")


# ------------------------------------------------------------------ 내용

def build_methods(b):
    b.h3("3.5 실험 4: 배분 가설의 확증 코호트")
    b.body("실험 3 은 v2 코호트 8 unit 과 깊이 파일럿에서 배분을 쟀다. 그 자료는 "
           "가설을 만든 자료다. greedy_frozen − rf_only = +1.55 [−0.60, +4.25] 에서 "
           "+1.55 의 대부분이 표적 하나(1n81A00, +10.00)에서 나왔고 그것을 빼면 "
           "+0.34 였다. 즉 가설이지 증거가 아니었다. 이 절은 그 가설을 처음으로 미리 "
           "고정한 정책으로 새 표적에서 시험한다. 규칙은 docs/specs/"
           "hierarchical-confirmatory-prespec.md (v1.6) 에 실행 전 동결했다.")
    b.body("코호트는 RFD3 단독 생성원의 34 표적이다. CATH pilot 중 v2 와 코호트 B "
           "어디에도 쓰이지 않은 것을 골랐고, 같은 PDB 엔트리를 두 번 쓰지 않으며 "
           "쌍대 서열 동일성 30% 이상인 쌍도 배제했다. 길이는 80–400 aa 다. 표적당 "
           "백본 6 개를 계획해 184/204 가 수용됐고, 백본당 서열 42 개를 전수 "
           "폴딩했다(7,728 건). 전수 격자이므로 어떤 배분 정책도 추가 folding 없이 "
           "오프라인으로 재생할 수 있다 — 이 설계 선택이 이 절 전체의 전제다.")
    b.body("두 가지를 한계로 적는다. 생성 실패로 백본 수용이 0 인 표적이 2 개이고, "
           "사전지정 §9 대로 표적을 새로 고르지 않고 모자란 채로 보고한다(실효 32 "
           "표적). 또 CATH superfamily 분류가 로컬에 없어 superfamily 수준의 비중복은 "
           "확인하지 못했다.")
    b.body("이 실행은 깊이 게이트를 통과하지 못한 뒤 사람이 승인한 것이다. 사전지정 "
           "§7.0 은 표본 크기를 깊이 파일럿의 효과 D_p 로 정하게 해 두었고 D_p ≤ 0 "
           "이면 멈추도록 했는데, 파일럿 결과는 D(42) = −0.010 이었다. 그 뒤 사람이 "
           "구간 축소를 목적으로 실행을 승인했다(v1.6). 따라서 이 결과는 구간을 좁히는 "
           "데 쓰고, 양성이 나와도 게이트를 소급해 통과시키지 않는다.")
    b.body("정책 greedy_frozen 은 사전지정 §5 에 전부 고정했다. 백본마다 sentinel "
           "4 개를 무작위로 접어 warm-up 24 회를 만들고, 그 24 개로 RF 를 적합한 뒤, "
           "백본 posterior mean = (통과 + 1)/(관측 + 2) 내림차순으로 정렬해(동점이면 "
           "backbone_key 사전순) 한 백본씩 정원 min(40, 후보수) − 4 까지 꽉 채운다. "
           "백본 안에서는 RF 예측 상위부터 고르고 동점이면 sequence_id 사전순이다. "
           "posterior 갱신도 탐색 몫도 없다. 모든 arm 이 같은 seed 에서 같은 warm-up "
           "표본을 받고, 차이는 남은 예산을 쓰는 방식에서만 생긴다.")
    b.body("주 종점은 정규화 회수율의 차이다. G(policy) = (Y_policy − Y_equal_random) "
           "/ (Y_oracle − Y_equal_random) 이고 주 비교는 G(greedy_frozen) − G(rf_only) "
           "의 표적 평균(B=80)이다. 분모가 0 에 가까우면 비율이 폭발하므로 자격 규칙을 "
           "결과 전에 정했다 — 분모(r) = H·r + min(B−H, (N−H)·r) − B·r ≥ 5 이며, "
           "자격은 실측 joint-pass 율로만 판정하고 정책 결과를 보고 판정하지 않는다. "
           "보조 종점은 자격 규칙을 적용하지 않은 원시 개수 차이다.")
    b.body("구간은 표적 클러스터 부트스트랩 2,000 회(seed 20260921)이고 seed 는 "
           "42·123·7·2024·31337 다. 주 종점이 하나이므로 다중성 보정을 하지 않는다. "
           "검정력도 미리 적어 두었다 — 파일럿의 정규화 효과(평균 +0.118, 자격 unit "
           "SD 0.184)와 v2 실측 자격률 55% 를 쓰면 34 표적에서 자격 unit 약 18.7, "
           "검정력 약 79% 다. 자격 unit 이 16 개 아래면 검정력이 73% 밑이며, 그 경우 "
           "음성 결과를 “효과 없음” 으로 쓰지 않고 관측된 자격 unit 수와 그때의 "
           "검정력을 함께 적는다.")

    b.h3("3.6 선택 이득을 백본 간과 백본 내로 가른다")
    b.body("동결된 판정 셋이 서로 맞지 않아 보인다. Gate 2 는 백본 내부에서 cheap "
           "predictor 가 서열을 못 가른다고 판정했고(NO-GO), 실험 1·2 는 표적의 전체 "
           "풀에서 RF 가 잘 고른다고 했으며, 실험 3 은 명시적 백본 배분을 얹어도 추가 "
           "이득이 없다고 했다. estimand 가 다르다. 가설은 RF 의 이득이 주로 백본 간 "
           "판별에서 오고 그래서 명시적 배분이 중복이라는 것이다. 맞으면 세 결과가 "
           "하나의 기전으로 정리된다. 규칙은 docs/specs/"
           "selection-gain-decomposition-prespec.md 에 동결했다.")
    b.body("네 arm 이 같은 warm-up 표본과 같은 RF 적합을 공유하고 선택만 다르다. "
           "배분과 백본 내 선택을 각각 RF 와 균등·무작위로 교차시켜 2×2 를 만든다 — "
           "rf/rf, rf/rand, unif/rf, unif/rand 다. Total = Y(rf/rf) − Y(unif/rand), "
           "Between = Y(rf/rand) − Y(unif/rand), Within = Y(unif/rf) − Y(unif/rand) "
           "이고 Inter 는 나머지로 어느 쪽에도 귀속하지 않는다. 주 종점은 "
           "Between − Within 이며 사전 예측은 Within ≈ 0 이었다. rf/rf 가 실제로 고른 "
           "백본별 개수를 rf/rand 의 배분으로 그대로 쓰므로, 두 arm 은 백본별 호출 수가 "
           "정확히 같고 백본 안에서의 선택만 다르다.")

    b.h3("3.7 목적함수를 coverage 로 바꾼 정책의 평가")
    b.body("실험 3–4 는 모두 수확을 목적함수로 둔 배분을 시험한다. 그러나 RAPID 의 "
           "정본 coverage-preserving 정책은 수확을 목적함수로 삼지 않는다 — coverage 를 "
           "최적화하고 수확은 acceptance guardrail 로만 쓴다. 따라서 앞선 결과는 그 "
           "정책에 대한 판정이 아니며, 오히려 목적함수를 바꾼 이유를 뒷받침한다. 이 "
           "절은 정본 정책을 제 종점으로 잰다. 규칙은 docs/specs/"
           "coverage-preserving-prespec.md 에 동결했다.")
    b.body("coverage unit 은 backbone_id 로 고정한다. 이 값은 coverage accounting 을 "
           "위한 operational design-context unit 이며, 각 backbone 이 서로 다른 "
           "biological basin 을 뜻한다고 주장하지 않는다. 주 종점은 EFBC 다 — "
           "EFBC(f) = exp(−Σ p_b log p_b), p_b = f_b / Σ f 이고 f_b 는 backbone b 에서 "
           "얻은 joint-pass 후보 수이며 EFBC(0) = 0 이다. EFBC 는 발견한 backbone 수가 "
           "아니라 feasible candidate mass 가 backbone design context 사이에 얼마나 "
           "효과적으로 분산돼 있는지를 잰다. 그래서 이미 한 backbone 에 mass 가 몰려 "
           "있을 때 거기 성공이 하나 더 붙으면 EFBC 가 감소할 수 있다 — 이 비단조성은 "
           "오류가 아니라 정의의 직접적 결과다.")
    b.body("정책은 one-step myopic 이다. q_b 는 다음 계산이 joint-pass 후보 하나를 낳을 "
           "posterior-predictive 확률이고, warm-up 은 백본당 4 회이며 이 구간에서 STOP 을 "
           "허용하지 않는다. 사전분포는 표적 수준 부분 풀링으로 만든다 — "
           "α = p̂_t·κ, β = (1 − p̂_t)·κ, κ = 4.0 이다. Gate 0 사전분포는 쓰지 않는다. "
           "기존 Gate 0 모델은 structural-success 로 학습됐고 여기서 요구하는 joint-pass "
           "예측기가 아니기 때문이다. κ = 4.0 은 엄밀한 conjugate hierarchical posterior "
           "가 아니라 고정 강도 shrinkage 규칙이므로 결과를 “hierarchical Bayesian "
           "posterior” 라고 기술하지 않는다. acquisition 은 "
           "A_b = q_b · [EFBC(f + e_b) − EFBC(f)] 이고, max_b A_b ≤ 0 이면 STOP 한다.")
    b.body("주 비교군은 same-cap static/equal 배분이고, 보조 비교군은 수확 탐욕형 "
           "greedy_fill 이며, 민감도로 static/equal 을 v2 의 realized calls 에 맞춘 판도 "
           "낸다. 예산은 B = 42·84·126·168 이고 주 예산점은 126 이다. 채택 가드레일은 "
           "structural-yield 비열등성으로, 비율의 단측 95% 하한이 0.90 이상이어야 한다. "
           "가드레일을 못 넘으면 뒤에서 수확 정책으로 fallback 하여 결과를 구제하지 "
           "않고, 그 조건에서 acceptance criterion 미충족으로 판정한다.")
    b.body("구조 진단은 따로 둔다. EFBC 가 높다고 structural diversity 가 높다고 "
           "주장하지 않는다. feasible 후보가 있는 백본을 하나씩 대표로 써서 Kabsch 중첩 "
           "후 pairwise CA-RMSD 를 내고, 비가중과 feasible-mass 가중을 함께 보고한다. "
           "clustering 은 threshold/linkage 불안정이 확인됐으므로 탐색적 민감도로만 쓰고 "
           "배분 단위로 쓰지 않는다. 해석 규칙도 결과 전에 갈라 적었다 — EFBC 와 "
           "dispersion 이 함께 오르면 coverage 증가가 greater structural dispersion 과 "
           "동반되었다고 보고하고, dispersion 이 그대로면 operational coverage 증가는 "
           "확인되었으나 measurable structural diversification 으로 이어지지 않았다고 "
           "보고한다.")


def build_results(b):
    b.h3("4.5 실험 4: 배분은 수확을 늘리지 않았다")
    b.body("폴딩 7,728 건 중 7,722 건이 성공했다(실패 6). 백본 수용이 0 인 2 표적은 "
           "사전지정 §9 대로 교체하지 않았으므로 실효 32 표적이다. 주 종점은 세 "
           "예산점 모두에서 0 을 포함한다. 사전지정 §10 의 “primary 0 포함” 경로이며 "
           "가설을 지지하지 않는다.")
    b.table([
        ["예산", "주 종점 G 차이 [95% CI]", "자격 unit", "설계 검정력", "판정"],
        ["B=60", "−0.056 [−0.221, +0.084]", "13 / 32", "64%", "0 포함"],
        ["B=80 (주)", "+0.086 [−0.059, +0.212]", "16 / 32", "73%", "0 포함"],
        ["B=100", "+0.105 [−0.037, +0.225]", "18 / 32", "78%", "0 포함"],
        ["B=80 보조", "+0.63 [−0.69, +1.83] (원시 개수)", "32 / 32", "—", "0 포함"],
    ])
    b.caption("표 6. 확증 코호트의 주 종점과 자격·검정력. 자격은 실측 joint-pass 율로 "
              "계산한 닫힌 형태 분모 ≥ 5 로 판정하며 정책 결과를 보고 판정하지 않는다. "
              "검정력은 파일럿에서 미리 고정한 효과 0.118 과 SD 0.184 를 쓴 설계 "
              "검정력이며, 관측된 효과로 되짚는 observed power 가 아니다.")
    b.body("자격 unit 이 주 예산점에서 정확히 16 개다. 사전지정 §7.1 이 “자격 unit 이 "
           "16 개 아래로 떨어지면 검정력이 73% 밑이며 그 경우 음성 결과를 ‘효과 없음’ "
           "으로 쓰지 않는다” 고 미리 적어 두었고, 경계값에 걸쳤으므로 그 규칙을 그대로 "
           "따른다. 이 결과는 배분 이득이 없다는 뜻이 아니라, 이 표본에서 +0.12 이상의 "
           "효과를 배제할 만큼의 정밀도를 확보하지 못했다는 뜻이다. 주 예산점 구간의 "
           "상한 +0.212 가 그 한계를 그대로 보여준다.")
    b.table([
        ["정책", "표적당 joint-pass", "여지 회수율", "비고"],
        ["oracle", "55.40", "100.0%", "눈금"],
        ["adaptive_sentinel", "50.02", "52.0%", "탐색 arm · 판정하지 않음"],
        ["greedy_frozen", "49.84", "50.4%", "주 정책"],
        ["backbone_only", "49.29", "45.5%", "배분만, 백본 안은 무작위"],
        ["rf_only", "49.21", "44.8%", "주 비교 상대"],
        ["mpnn_only", "45.95", "15.7%", "같은 warm-up 지불"],
        ["equal_random", "44.19", "0.0%", "기준선"],
    ])
    b.caption("표 7. B=80 에서 정책별 수확과 여지 회수율. 여지 회수율은 균등·무작위를 "
              "0%, oracle 을 100% 로 둔 정규화 값이다. 기술 통계이므로 구간을 붙이지 "
              "않았고, 수준 차이만으로 정책을 비교하지 않는다.")
    b.figure("fig6_confirmatory_harvest")
    b.caption("그림 6. 확증 코호트의 수확 결과. (A) 주 예산점의 arm 별 여지 회수율이다. "
              "기술 통계이므로 구간을 붙이지 않았다. (B) 예산별 주 종점과 표적 클러스터 "
              "부트스트랩 95% 구간이며, 주 예산점 B=80 은 0 을 포함한다. (C) 자격 unit "
              "수와 그때의 설계 검정력이다. 점선은 사전지정 §7.1 이 정한 16 unit "
              "경계이고, 주 예산점이 그 경계에 걸친다. (D) 자격 표적별 차이를 실측 "
              "joint-pass 율에 대해 흩뿌린 것이다. 평균 하나로 덮이지 않는 이질성을 "
              "보여준다.")
    b.body("자격 16 표적 중 11 개가 양의 방향이고 중앙값은 +0.106 이다. 그러나 퍼짐이 "
           "크다 — 1r7lA00 의 +0.600 부터 1bxmA00 의 −0.569 까지다. 평균 하나로 덮이지 "
           "않는 표적 간 이질성이 이 코호트에서도 그대로이며, 이것은 34 표적 설계의 "
           "근거였던 “지금 문제는 백본 수가 아니라 표적 간 효과 이질성” 이라는 판단을 "
           "다시 확인한다. 집중 상한은 예산에 따라 크게 달라진다(B=60 99.2%, "
           "B=80 65.0%, B=100 48.8%). B=60 에서 greedy 가 사실상 한 백본을 다 채우고도 "
           "음의 방향이 나온 것은, 집중 자체가 수확을 만들지 않는다는 뜻이다.")
    b.body("보조 비교에서 G(backbone_only) − G(rf_only) 는 +0.046 [−0.147, +0.202] 로 "
           "0 을 포함하고, G(mpnn_only) − G(rf_only) 는 −0.162 [−0.334, +0.017] 이다. "
           "한편 탐색 arm 인 adaptive_sentinel 은 G 차이 +0.097 [+0.004, +0.179] 로 "
           "0 을 제외했다. sentinel 관측으로 posterior 를 갱신하고 탐색 몫 25% 를 두는 "
           "판이다. 사전지정 §8 이 이 arm 을 탐색으로 함께 내고 주 판정을 바꾸지 "
           "않는다고 미리 못박았으므로 여기서 결론을 바꾸지 않는다 — 결과를 보고 판정 "
           "arm 을 고르면 사전등록이 의미를 잃기 때문이다. 다만 실험 3 이 깊이 18 에서 "
           "되먹임의 기여를 +0.00 [−0.32, +0.25] 로 측정했고 그것이 확증 설계에서 "
           "되먹임을 뺀 근거였는데, 깊이 42 에서는 방향이 다르게 나왔다. 다음 "
           "사전지정에서 판정 arm 으로 올릴 후보이지 이 문서의 결론이 아니다.")

    b.h3("4.6 선택 이득은 백본 간에서만 오지 않는다")
    b.table([
        ["예산", "Total", "Between", "Within", "Inter", "Between − Within"],
        ["B=40", "+1.77", "+1.22 [+0.66, +1.87]", "+0.70 [+0.29, +1.22]", "−0.15",
         "+0.53 [−0.22, +1.27]"],
        ["B=60", "+5.25", "+3.38 [+1.67, +5.33]", "+2.19 [+0.93, +3.85]", "−0.33",
         "+1.19 [−1.16, +3.49]"],
        ["B=80 (주)", "+7.64", "+4.66 [+2.13, +7.52]", "+3.13 [+1.33, +5.45]", "−0.14",
         "+1.53 [−1.81, +4.96]"],
        ["B=100", "+10.14", "+6.36 [+3.26, +9.81]", "+4.57 [+2.01, +7.76]", "−0.78",
         "+1.79 [−2.38, +6.01]"],
    ])
    b.caption("표 8. 선택 이득의 백본 간·백본 내 분해. 단위는 표적당 joint-pass 개수다. "
              "네 arm 이 같은 warm-up 표본과 같은 RF 적합을 공유하고 선택만 다르다. "
              "주 종점은 Between − Within 이며 네 예산점 모두 0 을 포함한다. Within 은 "
              "네 예산점 모두 0 을 제외한다.")
    b.figure("fig7_selection_decomposition")
    b.caption("그림 7. 선택 이득의 분해. (A) 주 예산점에서 네 성분과 95% 구간이다. "
              "(B) 예산별 주 종점 Between − Within 이다. 주 종점은 0 을 포함하지만 "
              "Within 자체는 0 을 제외한다 — 사전 예측이 틀렸음을 보여주는 부분이다.")
    b.body("주 종점은 0 을 포함하므로 두 성분이 구별되지 않았다. 그러나 이 절의 중요한 "
           "결과는 주 종점이 아니라 Within 이다. 사전지정에 Within ≈ 0 을 예측으로 "
           "적었다 — Gate 2 가 NO-GO 였으니 백본 내부에서는 cheap predictor 가 서열을 "
           "가르지 못할 것이라는 논리였다. 그 예측은 틀렸다. Within 은 네 예산점 모두 "
           "0 을 제외하고, Between 의 3 분의 2 에 이르며, 예산에 따라 나란히 커진다. "
           "Inter 는 네 예산 모두 0 을 포함하므로 두 축이 거의 가법적으로 쌓인다.")
    b.body("이것이 §3.6 이 풀려던 외견상 모순의 답을 바꾼다. “RF 의 이득이 백본 간 "
           "판별에서 오고 그래서 명시적 배분이 중복이다” 라는 설명은 성립하지 않는다. "
           "배분이 이득을 내지 못하는 이유는 다른 곳에서 찾아야 한다. Gate 2 의 NO-GO "
           "와의 차이는 estimand 로 설명된다 — Gate 2 는 고정된 얕은 관측에서 백본 내 "
           "판별을 물었고, 여기서는 warm-up 으로 표적별 보정을 한 RF 가 깊이 42 의 풀 "
           "안에서 고른다. 같은 이름의 질문이 아니다. 어느 쪽도 번복되지 않으며 두 "
           "결과는 서로 다른 조건의 측정으로 함께 남는다.")

    b.h3("4.7 coverage 목적함수: 이기지만 채택되지 않는다")
    b.table([
        ["예산", "EFBC v2", "EFBC 균등", "EFBC 수확탐욕",
         "v2 − 균등 [95% CI]", "실제 호출", "STOP", "가드레일 비율 (LCB)"],
        ["B=42", "4.22", "4.01", "2.81", "+0.201 [+0.095, +0.310]", "30.2 / 42",
         "0.70", "0.629 (0.602)"],
        ["B=84", "4.35", "4.11", "2.51", "+0.242 [+0.112, +0.392]", "40.4 / 84",
         "0.80", "0.327 (0.313)"],
        ["B=126 (주)", "4.42", "4.16", "2.92", "+0.268 [+0.122, +0.446]", "47.3 / 126",
         "0.91", "0.221 (0.211)"],
        ["B=168", "4.45", "4.18", "3.38", "+0.276 [+0.114, +0.466]", "49.1 / 168",
         "0.99", "0.167 (0.159)"],
    ])
    b.caption("표 9. coverage-preserving 정책을 제 종점으로 잰 결과. EFBC 차이는 네 "
              "예산점 모두 0 을 제외한다. 가드레일은 structural-yield 비율이며 괄호는 "
              "단측 95% 하한이다 — 채택 기준은 그 하한이 0.90 이상인 것이고, 네 예산점 "
              "모두 미달이다. 실제 호출은 상한 대비 실제로 소모한 folding 횟수다.")
    b.figure("fig8_coverage_efbc")
    b.caption("그림 8. coverage 목적함수의 평가. (A) 정책별 terminal EFBC 다. "
              "(B) 주 비교의 차이와 95% 구간으로, 네 예산점 모두 0 을 제외한다. "
              "(C) 실제로 소모한 호출 수다. 상한을 네 배로 늘려도 v2 의 소모는 49 회 "
              "근처에서 포화한다. (D) 가드레일로, 원은 비율이고 삼각형은 단측 95% "
              "하한이다. 점선이 채택 기준 0.90 이다.")
    b.body("정본 정책은 제 목적함수에서 네 예산점 모두 이긴다. 수확 탐욕형과의 격차는 "
           "훨씬 크다(B=126 에서 +1.506 [+1.197, +1.806]). 수확 목적과 coverage 목적이 "
           "같은 자료에서 정반대 방향의 배분을 만든다는 것이 여기서 확인된다. 그러나 "
           "채택 가드레일은 네 예산점 모두 미달이다. 사전지정 §10 의 “EFBC 우위 + "
           "가드레일 실패” 경로이며, 그 조건에서 coverage mode 가 acceptance criterion "
           "을 충족하지 못했다고 판정한다. §5 가 금지한 대로 뒤에서 수확 정책으로 "
           "fallback 하여 결과를 구제하지 않는다.")
    b.body("원인은 정책이 예산을 다 쓰지 않는 데 있다. 상한을 42 에서 168 로 네 배 "
           "늘려도 실제 소모는 30.2 에서 49.1 로만 늘고 49 근처에서 포화한다. 예산을 "
           "늘릴수록 가드레일 비율이 오히려 나빠지는 것(0.629 → 0.167)은 분모인 "
           "same-cap 비교군만 예산을 다 쓰기 때문이다. 이 포화의 기전은 §5.4 에서 따로 "
           "다룬다.")
    b.body("구조 진단은 별도로 본다. 표적 내 백본 쌍 453 개의 CA-RMSD 는 평균 2.29 Å "
           "이고 분위는 q05 1.14 · q50 2.28 · q95 3.39 Å 다. B=126 에서 비가중 dispersion "
           "차이는 +0.0038 Å [+0.0003, +0.0096] 로 0 을 제외하지만, 크기가 거리 분포 "
           "평균의 0.2% 에 불과하다. 가중 차이는 +0.0207 Å [−0.0003, +0.0513] 로 0 을 "
           "포함한다. B=168 에서 네 대비 중 셋이 0 을 제외하지만 크기는 여전히 "
           "0.004–0.031 Å 다. 닿은 context 수도 정책 간에 사실상 같다(B=126 에서 "
           "v2 5.5, 균등 5.5, 수확탐욕 5.1). 사전지정 §6 이 결과 전에 갈라 적어 둔 두 "
           "갈래 중 “operational coverage 증가는 확인되었으나 measurable structural "
           "diversification 으로 이어지지 않았다” 쪽이다. 통계적 구별과 크기를 구분해 "
           "적는다 — 구간이 0 을 제외한다는 사실만으로 구조가 다양해졌다고 쓰지 않는다.")
    b.figure("fig9_structural_dispersion")
    b.caption("그림 9. 구조 dispersion 진단. (A) 표적 내 백본 쌍 CA-RMSD 의 분위 "
              "분포다. (B) 주 예산점의 dispersion 대비와 95% 구간이다. 일부 대비가 "
              "0 을 제외하지만 크기가 0.004–0.03 Å 로 (A) 의 2.29 Å 규모에 비해 "
              "무시할 수준이다.")


def build_discussion(b):
    b.h3("5.4 STOP 규칙은 정책이 목표 상태에 도달하는 순간 발동한다")
    b.body("§4.7 이 보인 “상한을 네 배로 늘려도 소모가 49 회에서 포화” 하는 현상에는 "
           "자료에 의존하지 않는 설명이 있다. 백본 k 개의 feasible mass 가 균등하면 "
           "f = (n, …, n) 이고 EFBC(f) = k 다. 어느 한 곳에 1 을 더하면 분포가 균등에서 "
           "멀어져 엔트로피가 엄격히 줄므로 EFBC(f + e_b) − EFBC(f) < 0 이 모든 b 에 "
           "대해 성립한다. q_b ≥ 0 이므로 A_b ≤ 0 이고 곧 STOP 이다. 즉 one-step "
           "myopic EFBC 정책은 자기 목적함수의 최적점에서 스스로 멈춘다. k = 2…12, "
           "n = 1…40 격자에서 부호를 직접 확인했고 최대 이득은 −1.5×10⁻⁴ 였다. 이 "
           "명제는 관측을 하나도 쓰지 않으며, 이 코호트의 성질이 아니라 엔트로피류 "
           "목적에 local-saturation STOP 을 붙이는 acquisition 설계 일반의 성질이다.")
    b.body("그 상태에 얼마나 자주 닿는지는 자료가 답한다. B=126 에서 (표적, seed) "
           "160 회 중 145 회(91%)가 STOP 했고, STOP 시점 f 의 최대/최소 비 중앙값은 "
           "1.00 이며 68% 가 완전 균등이었다. warm-up 4 회가 대개 모든 백본에 성공을 "
           "하나 이상 남기므로 정책은 몇 수 안에 균등에 도달하고 거기서 멈춘다.")
    b.body("멈춘 대가는 탐색적으로만 잰다. STOP 만 뺀 판을 같은 격자에서 재생했는데, "
           "가드레일이 실패한 것을 본 뒤에 돌린 반사실이므로 확증 주장으로 쓰지 않는다. "
           "두 가지를 정확히 적는다. 첫째, EFBC 는 달라지지 않는다 — 차이가 B=42 에서 "
           "+0.018 [−0.002, +0.049], B=126 에서 +0.037 [−0.016, +0.114] 로 0 을 "
           "포함하고 B=168 에서는 부호가 바뀐다(−0.040 [−0.131, +0.052]). 네 예산 중 "
           "0 을 제외하는 것은 B=84 하나뿐이다. 즉 STOP 은 목적함수를 지켜주지 못하며, "
           "멈추는 지점은 전역 최적이 아니라 국소 최적이다. 둘째, 가드레일은 STOP 을 "
           "빼도 통과하지 못한다 — 점추정 비율은 0.884–0.930 으로 기준을 넘는 것처럼 "
           "보이지만 사전지정이 요구하는 것은 단측 95% 하한 ≥ 0.90 이고 그 값은 "
           "0.817–0.886 이다. 가장 좋은 B=168 에서도 0.886 으로 미달이다.")
    b.table([
        ["예산", "EFBC (유지 → 제거)", "수확 (유지 → 제거)", "호출 (유지 → 제거)",
         "가드레일 비율 (제거 후 LCB)"],
        ["B=42", "4.22 → 4.23", "15.0 → 21.8", "30 → 42", "0.629 → 0.910 (0.864)"],
        ["B=84", "4.35 → 4.40", "15.6 → 42.1", "40 → 83", "0.327 → 0.884 (0.817)"],
        ["B=126", "4.42 → 4.46", "15.8 → 63.8", "47 → 123", "0.221 → 0.895 (0.831)"],
        ["B=168", "4.45 → 4.41", "15.8 → 88.2", "49 → 163", "0.167 → 0.930 (0.886)"],
    ])
    b.caption("표 10. STOP 규칙을 제거한 탐색적 반사실. 확증 주장이 아니다 — 가드레일 "
              "실패를 본 뒤에 돌린 계산이므로 이 값으로 §4.7 의 채택 판정을 뒤집지 "
              "않는다. EFBC 는 사실상 그대로이고 가드레일은 단측 95% 하한 기준으로 네 "
              "예산점 모두 여전히 0.90 에 못 미친다.")
    b.figure("fig10_stop_rule_diagnosis")
    b.caption("그림 10. STOP 규칙 진단. 판정이 아니라 §4.7 결과의 기전 설명이다. "
              "(A) 해석적 주장으로, 균등한 f 에서 한계 EFBC 이득이 모든 k·n 에 대해 "
              "음수다. 관측을 쓰지 않는다. (B) 그 상태에 닿는 빈도다. (C) STOP 을 뺀 "
              "탐색적 반사실이며 유지 판 대비 비율이다. EFBC 는 그대로이고 수확과 "
              "호출만 늘어난다.")
    b.body("따라서 STOP 제거는 실패의 성격을 바꾸는 것이지 결과를 구제하는 것이 "
           "아니다. 구조적 불가능(하한 0.211)에서 근소한 미달(하한 0.886)로 옮길 "
           "뿐이며, 이 값으로 §4.7 의 채택 판정을 뒤집지 않는다. 이 절에서 확증적인 "
           "것은 해석적 주장 하나뿐이고, 빈도는 단순 관측이며, 반사실은 탐색적이다.")


LIMITS = [
    "주 종점의 정밀도가 부족하다. 자격 unit 16 개는 사전지정 §7.1 의 경계값이고 설계 "
    "검정력은 약 73% 다. 음성을 “효과 없음” 으로 쓰지 않으며, 구간 상한 +0.212 까지의 "
    "효과는 배제되지 않는다.",
    "확증 실행은 깊이 게이트를 통과하지 못한 뒤 사람이 구간 축소를 목적으로 승인한 "
    "것이다. 결과가 음성이므로 게이트를 소급해 다루는 문제는 발생하지 않는다.",
    "superfamily 수준 비중복은 확인하지 못했다. 비중복은 PDB 엔트리와 쌍대 서열 동일성 "
    "30% 로만 보장된다.",
    "백본 수용이 0 인 표적 2 개를 교체하지 않았다. 실효 32 표적이다.",
    "표적 간 효과 이질성이 크다(−0.569 ~ +0.600). 평균 하나로 요약되지 않는다.",
    "§5.4 의 반사실은 탐색적이다. 사전지정 밖의 정책이며 채택 판정을 바꾸지 않는다.",
    "backbone_id 를 biological basin 이라고 주장하지 않으며 EFBC 를 structural "
    "diversity metric 이라고 부르지 않는다.",
    "탐색 arm adaptive_sentinel 이 0 을 제외했으나 사전지정 §8 대로 판정하지 않는다. "
    "다음 사전지정의 후보일 뿐이다.",
]

CONCLUSION = [
    "배분 축의 확증 코호트에서 두 목적함수 모두 이득이 확인되지 않았다. 수확 목적에서 "
    "주 종점은 +0.086 [−0.059, +0.212] 로 0 을 포함했고(자격 16 unit, 설계 검정력 73%), "
    "coverage 목적에서는 EFBC 가 +0.268 [+0.122, +0.446] 로 이겼으나 structural-yield "
    "가드레일이 단측 95% 하한 0.211 로 기준 0.90 에 미달했다. 구조 진단에서도 coverage "
    "상승이 measurable structural diversification 으로 이어지지 않았다(0.004 Å, 거리 "
    "분포 평균 2.29 Å 대비). 현 운용 기본값을 바꿀 근거가 없다 — 다중 backbone 으로 "
    "후보 공간을 넓히고 구조예측 예산은 sequence-level triage 에 쓴다.",
    "다만 §4.6 이 그 이유에 대한 기존 설명을 무너뜨렸다. 선택 이득은 백본 간 성분과 "
    "백본 내 성분 양쪽에서 나오며(Within +3.13 [+1.33, +5.45]), 따라서 “배분이 중복이라 "
    "이득이 없다” 는 설명은 쓸 수 없다. 왜 배분이 그 이득을 회수하지 못하는지는 열린 "
    "질문으로 남긴다.",
    "방법론 기여는 §5.4 의 해석적 주장이다. 엔트로피류 목적에 붙인 local-saturation "
    "STOP 규칙은 정책이 목표 상태에 도달하는 순간 발동하며, 그 결과 예산의 상당 부분을 "
    "남기고 종료해 채택 가드레일을 구조적으로 통과하기 어렵게 만든다. 이 주장은 자료에 "
    "의존하지 않고 증명되며 coverage-preserving acquisition 설계 일반에 적용된다.",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    doc = Document(str(DOC))
    if any(p.text.strip().startswith("3.5 실험 4") for p in doc.paragraphs):
        print("이미 병합돼 있다. 중단한다.")
        return 1

    b = Builder(doc)
    build_methods(b);     b.flush_before(find(doc, "4. 결과"))
    build_results(b);     b.flush_before(find(doc, "5. 논의"))
    build_discussion(b);  b.flush_before(find(doc, "6. 한계"))

    for t in LIMITS:
        b.body("· " + t)
    b.flush_before(find(doc, "7. 결론"))
    for t in CONCLUSION:
        b.body(t)
    b.flush_before(find(doc, "참고문헌"))

    n_p = len([p for p in doc.paragraphs if p.text.strip()])
    print(f"문단 {n_p} · 표 {len(doc.tables)} · 그림 {len(doc.inline_shapes)}")
    if not a.dry_run:
        BACKUP.mkdir(parents=True, exist_ok=True)
        bak = BACKUP / (DOC.name + ".bak-premerge")
        if not bak.exists():
            shutil.copy2(DOC, bak)
        doc.save(str(DOC))
        print(f"저장 · 백업 {bak}")
    else:
        print("(dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

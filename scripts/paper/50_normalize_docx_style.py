#!/usr/bin/env python3
"""네 문서의 표·그림 체재를 /opt/RAPID_manuscript_KR_compact.docx 에 맞춘다.

범본에서 읽어 온 규약
---------------------
    표 캡션    표 **위** · Caption 스타일 · "표 N." 라벨 굵게
    그림 캡션  그림 **아래** · Caption 스타일 · "그림 N." 라벨 굵게
    데이터 표  Table Grid · 헤더 행 굵게 + 연회색 음영 + 쪽 넘김 시 반복
    그림 폭    문서 안에서 균일 · 가운데 정렬

현 상태가 왜 문제인가
---------------------
    표 스타일  `Normal Table` 은 **테두리가 없다.** 네 문서에 섞여 있다.
    캡션 위치  연구노트 보충은 표1·3·4 가 아래, 표5·6·7 이 위로 섞여 있다.
    캡션 누락  파이프라인 본문은 표 5 개 전부 캡션이 없다.
    그림 폭    파이프라인 본문이 15.92 / 15.50 / 16.00 / 15.50 / 15.50 이다.

문장을 새로 쓰지 않는 것이 원칙이다. 보충자료처럼 캡션 문장이 이미 있고
라벨만 없는 경우에는 **라벨만 앞에 붙인다.** 아예 없는 경우에만 새로 쓴다.

1x1 표는 데이터 표가 아니라 콜아웃 박스다. 번호를 붙이지 않고 음영 박스로만
구분한다.
"""

from __future__ import annotations

import argparse
import copy
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt, RGBColor

OPT = Path("/opt")
BACKUP = OPT / "archive" / "backups"
HEADER_FILL = "EDEDED"
CALLOUT_FILL = "F5F5F5"

CAP_TBL = re.compile(r"^\s*(보충표\s*S?\d+|표\s*\d+|Table\s*\d+)\s*[.．]")
CAP_FIG = re.compile(r"^\s*(보충그림\s*S?\d+|그림\s*\d+|Figure\s*\d+)\s*[.．]")

#: 캡션이 아예 없어 새로 쓰는 것. 표 내용을 읽고 적었다.
NEW = {
    "용해성 지향 단백질 재설계 파이프라인.docx": {
        1: "표 1. RAPID 파이프라인의 단계 구성. 각 단계가 답하는 질문, 그 단계에서 "
           "쓰는 도구와 규칙, 전체 흐름에서 맡는 역할을 구분했다.",
        2: "표 2. 실험 1 결과. 67개 CATH 표적에서 동일 서열 반복을 (표적, 서열) 단위로 "
           "묶은 뒤 측정한 RF 의 pLDDT Top-20 순위화 성능이다. 괄호는 표적을 클러스터로 "
           "한 부트스트랩 2,000회의 95% 신뢰구간이다.",
        3: "표 3. 평가 축과 종점의 배치. 축마다 무엇을 주 평가로 두고 무엇을 보조·"
           "가드레일로만 쓰는지 구분했다. 주 평가를 결과를 보고 바꾸지 않기 위해 미리 "
           "고정한 배치다.",
        4: "표 4. 현재 한계와 대응. 한계마다 지금 취한 대응과, 그 대응이 허용하는 해석의 "
           "범위를 함께 적었다.",
        5: "표 5. 핵심 지표의 정의와 역할. 지표가 무엇을 재는지와 RAPID 안에서 어떤 "
           "판단에 쓰이는지를 구분했다.",
    },
    "용해성 지향 단백질 재설계 파이프라인_supplementary.docx": {
        5: "보충표 S5. 핵심 지표의 정의와 역할. 본문 부록 A 와 같은 내용을 보충자료에서도 "
           "찾을 수 있게 옮겨 둔 것이다.",
    },
}
#: 캡션 문장은 있는데 라벨이 없는 것. 문장을 보존하고 라벨만 앞에 붙인다.
PREFIX = {
    "용해성 지향 단백질 재설계 파이프라인_supplementary.docx": {
        2: "보충표 S2. ", 3: "보충표 S3. ", 4: "보충표 S4. ",
    },
}
#: 데이터 표가 아니라 콜아웃 박스. 번호를 붙이지 않는다.
CALLOUT = {"RAPID_ResearchNote_KR_v1.0_polished.docx": {1, 2}}


# ------------------------------------------------------------------ 도구

def _shade(el, fill):
    tcPr = el.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn("w:tblHeader")) is None:
        trPr.append(OxmlElement("w:tblHeader"))


def _grid_borders(tbl, sz=4, val="single"):
    """`Table Grid` 가 정의돼 있지 않은 문서가 있다. 테두리를 직접 넣는다."""
    tblPr = tbl._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), val)
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:color"), "808080")
        b.append(e)
    tblPr.append(b)


def _no_borders(tbl):
    tblPr = tbl._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), "none")
        b.append(e)
    tblPr.append(b)


def _disp_len(txt: str) -> float:
    """한글·한자는 라틴 문자보다 넓다. 폭 배분에 그 차이를 반영한다."""
    return sum(1.8 if ord(c) > 0x2E80 else 1.0 for c in txt)


def fit_columns(tbl, body_w, min_cm=1.8, damp=0.65):
    """열 너비를 내용량에 비례시킨다.

    균등 배분이나 손으로 준 폭은 내용과 어긋나 있는 경우가 많다 - 이 문서들
    에서는 글자 수가 가장 많은 열이 가장 좁은 경우까지 있었다. 긴 열 하나가
    표를 독식하지 않도록 지수 `damp` 로 눌러서 나눈다.
    """
    n = len(tbl.columns)
    if n < 2:
        return False
    raw = [max(_disp_len(r.cells[c].text.strip()) for r in tbl.rows) for c in range(n)]
    w = [max(v, 1.0) ** damp for v in raw]
    total_cm = Emu(body_w).cm
    cm_w = [total_cm * x / sum(w) for x in w]
    #: 최소 폭을 보장하고 남은 폭을 나머지 열에서 비례로 회수한다
    for _ in range(3):
        short = [i for i, v in enumerate(cm_w) if v < min_cm]
        if not short:
            break
        debt = sum(min_cm - cm_w[i] for i in short)
        rest = [i for i in range(n) if i not in short]
        pool = sum(cm_w[i] for i in rest)
        if pool <= debt:
            break
        for i in short:
            cm_w[i] = min_cm
        for i in rest:
            cm_w[i] -= debt * cm_w[i] / pool
    grid = tbl._tbl.find(qn("w:tblGrid"))
    if grid is None:
        return False
    cols = grid.findall(qn("w:gridCol"))
    if len(cols) != n:
        return False
    tblPr = tbl._tbl.tblPr
    for old in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(old)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    for i, g in enumerate(cols):
        g.set(qn("w:w"), str(int(cm_w[i] * 567)))
    for r in tbl.rows:
        for i, c in enumerate(r.cells):
            if i < n:
                c.width = Emu(int(cm_w[i] * 360000))
    return True


def ensure_caption_style(doc):
    from docx.enum.style import WD_STYLE_TYPE
    try:
        st = doc.styles["Caption"]
    except KeyError:
        st = doc.styles.add_style("Caption", WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = doc.styles["Normal"]
    st.font.size = Pt(10)
    st.font.bold = False
    st.font.italic = False
    st.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    st.paragraph_format.space_before = Pt(4)
    st.paragraph_format.space_after = Pt(4)
    return st


def make_caption(p, text, font_name, style):
    """문단을 캡션으로 만든다. 라벨 부분만 굵게 한다."""
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    m = CAP_TBL.match(text) or CAP_FIG.match(text)
    cut = m.end() if m else 0
    p.style = style
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for chunk, bold in ((text[:cut], True), (text[cut:], False)):
        if not chunk:
            continue
        r = p.add_run(chunk)
        r.bold = bold
        r.font.size = Pt(10)
        if font_name:
            r.font.name = font_name
            r._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
    return p


def body_items(doc):
    out = []
    for ch in doc.element.body.iterchildren():
        if ch.tag == qn("w:p"):
            t = "".join(n.text or "" for n in ch.iter(qn("w:t"))).strip()
            out.append(("IMG" if ch.find(".//" + qn("a:blip")) is not None else "P",
                        t, ch))
        elif ch.tag == qn("w:tbl"):
            out.append(("TBL", "", ch))
    return out


# ------------------------------------------------------------------ 본체

def normalize(path: Path, dry: bool) -> list[str]:
    log = []
    doc = Document(str(path))
    cap_style = ensure_caption_style(doc)
    sec = doc.sections[0]
    body_w = sec.page_width - sec.left_margin - sec.right_margin
    font = "맑은 고딕"
    name = path.name
    new, pre, callout = NEW.get(name, {}), PREFIX.get(name, {}), CALLOUT.get(name, set())

    # --- 1. 그림: 폭 균일 · 가운데 · 캡션은 아래
    widths = [sh.width for sh in doc.inline_shapes]
    if widths:
        target = min(max(widths), body_w)
        for sh in doc.inline_shapes:
            if sh.width != target:
                ratio = sh.height / sh.width
                sh.width, sh.height = target, Emu(int(target * ratio))
        log.append(f"그림 {len(widths)}개 폭 {Emu(target).cm:.2f} cm 로 통일")
    items = body_items(doc)
    for k, t, el in items:
        if k == "IMG":
            p = [p for p in doc.paragraphs if p._p is el]
            if p:
                p[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # --- 2. 표: 스타일 · 헤더 · 캡션 위치
    items = body_items(doc)
    ti = 0
    n_cap_moved = n_cap_new = n_cap_pre = n_fit = 0
    #: 캡션 하나가 두 표에 잡히면 안 된다. 표1 의 캡션이 표1 과 표2 사이에
    #: 있으면 표2 가 그것을 제 캡션으로 오인한다.
    used: set = set()
    for i, (k, _, el) in enumerate(items):
        if k != "TBL":
            continue
        ti += 1
        tbl = next(t for t in doc.tables if t._tbl is el)

        if ti in callout:                       # 콜아웃 박스
            _no_borders(tbl)
            for row in tbl.rows:
                for c in row.cells:
                    _shade(c._tc, CALLOUT_FILL)
            continue

        _grid_borders(tbl)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        if fit_columns(tbl, body_w):
            n_fit += 1
        hdr = tbl.rows[0]
        _repeat_header(hdr)
        for c in hdr.cells:
            _shade(c._tc, HEADER_FILL)
            for p in c.paragraphs:
                for r in p.runs:
                    r.bold = True

        # 캡션 찾기: 바로 앞 -> 바로 뒤
        cap_el = None
        for j in range(i - 1, max(-1, i - 3), -1):
            if items[j][0] == "P" and items[j][1]:
                if CAP_TBL.match(items[j][1]) and items[j][2] not in used:
                    cap_el = items[j][2]
                break
        if cap_el is None:
            for j in range(i + 1, min(len(items), i + 3)):
                if items[j][0] == "P" and items[j][1]:
                    if CAP_TBL.match(items[j][1]) and items[j][2] not in used:
                        cap_el = items[j][2]
                        n_cap_moved += 1
                    break
        if cap_el is None and ti in pre:         # 문장은 있고 라벨만 없다
            for j in range(i - 1, max(-1, i - 3), -1):
                if items[j][0] == "P" and items[j][1] and items[j][2] not in used:
                    cap_el = items[j][2]
                    txt = pre[ti] + items[j][1]
                    para = next(p for p in doc.paragraphs if p._p is cap_el)
                    make_caption(para, txt, font, cap_style)
                    n_cap_pre += 1
                    break
        if cap_el is None and ti in new:         # 아예 없다
            para = doc.add_paragraph()
            make_caption(para, new[ti], font, cap_style)
            cap_el = para._p
            n_cap_new += 1
        if cap_el is not None:
            used.add(cap_el)
            para = next((p for p in doc.paragraphs if p._p is cap_el), None)
            if para is not None and CAP_TBL.match(para.text.strip()):
                make_caption(para, para.text.strip(), font, cap_style)
            el.addprevious(cap_el)               # 표 바로 위로 옮긴다

    log.append(f"표 {ti}개 → Table Grid · 헤더 강조 · 열폭 재배분 {n_fit} "
               f"(캡션 새로 {n_cap_new} · 라벨 보강 {n_cap_pre} · 위로 이동 {n_cap_moved}"
               f" · 콜아웃 제외 {len(callout)})")

    # --- 3. 그림 캡션 스타일
    n_fig = 0
    for p in doc.paragraphs:
        if CAP_FIG.match(p.text.strip()):
            make_caption(p, p.text.strip(), font, cap_style)
            n_fig += 1
    log.append(f"그림 캡션 {n_fig}개 → Caption 스타일")

    if not dry:
        BACKUP.mkdir(parents=True, exist_ok=True)
        bak = BACKUP / (path.name + ".bak-paperstyle")
        if not bak.exists():          # 첫 변경 전 상태를 덮어쓰지 않는다
            shutil.copy2(path, bak)
        doc.save(str(path))
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("files", nargs="*", default=None)
    a = ap.parse_args(argv)
    files = a.files or [
        "용해성 지향 단백질 재설계 파이프라인.docx",
        "용해성 지향 단백질 재설계 파이프라인_supplementary.docx",
        "RAPID_ResearchNote_KR_v1.0_polished.docx",
        "RAPID_ResearchNote_supplement_KR_v1.0_polished.docx"]
    for f in files:
        p = OPT / f
        print(f"\n=== {f}")
        for line in normalize(p, a.dry_run):
            print(f"    {line}")
    print("\n(dry-run — 저장하지 않았다)" if a.dry_run else f"\n백업 {BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""새로 그린 영어 그림을 문서의 같은 자리에 갈아 끼운다.

문서 안의 순서대로 일대일 교체한다. 캡션·위치·문단은 건드리지 않는다.
가로세로비가 달라졌으므로 폭은 문서의 본문폭에 맞추고 높이는 비율로 다시
계산한다. 그러지 않으면 새 그림이 찌그러진다.
"""

from __future__ import annotations

import argparse
import io
import shutil
from pathlib import Path

from docx import Document
from docx.shared import Emu
from PIL import Image

OPT = Path("/opt")
FIG = Path("/opt/protein_pipeline-work/figures/submission")
BACKUP = OPT / "archive" / "backups"

PLAN = {
    "용해성 지향 단백질 재설계 파이프라인.docx": [
        "fig1_workflow", "fig2_experiment2_forest", "fig3_structural_context",
        "fig4_allocation", "fig5_depth_scaling"],
    "RAPID_ResearchNote_KR_v1.0_polished.docx": [
        "note_fig1_design", "note_fig2_headline", "note_fig3_source_stratified"],
    "RAPID_ResearchNote_supplement_KR_v1.0_polished.docx": [
        "note_figS1_threeway_distribution"],
}


def embed(path: Path, names: list[str], dry: bool) -> list[str]:
    doc = Document(str(path))
    sec = doc.sections[0]
    body_w = sec.page_width - sec.left_margin - sec.right_margin
    shapes = doc.inline_shapes
    log = []
    if len(shapes) != len(names):
        return [f"그림 수가 맞지 않는다: 문서 {len(shapes)} · 계획 {len(names)}"]
    for sh, nm in zip(shapes, names):
        src = FIG / f"{nm}.png"
        if not src.exists():
            log.append(f"{nm}: 파일 없음 - 건너뛴다")
            continue
        blob = src.read_bytes()
        w_px, h_px = Image.open(io.BytesIO(blob)).size
        part = doc.part.related_parts[sh._inline.graphic.graphicData.pic.blipFill.blip.embed]
        part._blob = blob
        sh.width = body_w
        sh.height = Emu(int(body_w * h_px / w_px))
        log.append(f"{nm}: {w_px}x{h_px}px → {Emu(body_w).cm:.2f} cm "
                   f"({w_px / (Emu(body_w).cm / 2.54):.0f} dpi)")
    if not dry:
        BACKUP.mkdir(parents=True, exist_ok=True)
        bak = BACKUP / (path.name + ".bak-enfigs")
        if not bak.exists():
            shutil.copy2(path, bak)
        doc.save(str(path))
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    for f, names in PLAN.items():
        print(f"\n=== {f}")
        for line in embed(OPT / f, names, a.dry_run):
            print(f"    {line}")
    print("\n(dry-run)" if a.dry_run else f"\n백업 {BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

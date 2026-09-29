#!/usr/bin/env python3
"""표 번호를 문서 순서에 맞춘다.

배분 축을 §4.5-§4.7 에 끼워 넣으면서 새 표가 기존 표 3-5 앞에 놓였다. 캡션
번호는 1, 2, 6, 7, 8, 9, 3, 10, 4, 5 순으로 어긋났고 독자가 훑을 때 깨진다.

본문 안의 "(표 N)" 참조도 같은 사상으로 바꾼다. 보충자료는 본문 **그림**만
참조하고 표는 참조하지 않는 것을 확인했으므로 건드리지 않는다.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

OPT = Path("/opt")
DOC = OPT / "용해성 지향 단백질 재설계 파이프라인.docx"
BACKUP = OPT / "archive" / "backups"
CAP = re.compile(r"^(\s*표\s*)(\d+)(\s*[.．])")
REF = re.compile(r"(표\s*)(\d+)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    doc = Document(str(DOC))

    #: 문서 순서대로 표 캡션을 모은다. 캡션은 표 **바로 위** 문단이다.
    caps, pos = [], 0
    for ch in doc.element.body.iterchildren():
        if ch.tag == qn("w:p"):
            txt = "".join(n.text or "" for n in ch.iter(qn("w:t"))).strip()
            if CAP.match(txt):
                caps.append((ch, txt))
        elif ch.tag == qn("w:tbl"):
            pos += 1
    mapping = {}
    for new, (ch, txt) in enumerate(caps, 1):
        old = int(CAP.match(txt).group(2))
        mapping[old] = new
    print("표 재사상:", " ".join(f"{o}->{n}" for o, n in sorted(mapping.items())))
    if all(o == n for o, n in mapping.items()):
        print("이미 순서대로다. 중단한다.")
        return 1

    para = {p._p: p for p in doc.paragraphs}
    n_cap = n_ref = 0
    for ch, txt in caps:
        old = int(CAP.match(txt).group(2))
        new = mapping[old]
        if old == new:
            continue
        p = para[ch]
        #: 라벨은 첫 run 에 굵게 들어 있다. 그 run 만 고친다.
        for r in p.runs:
            if CAP.match(r.text):
                r.text = CAP.sub(lambda m: f"{m.group(1)}{new}{m.group(3)}", r.text, 1)
                n_cap += 1
                break

    #: 본문 참조. 캡션 문단은 건너뛴다.
    capset = {ch for ch, _ in caps}
    for p in doc.paragraphs:
        if p._p in capset or p.style.name == "Caption":
            continue
        for r in p.runs:
            if not REF.search(r.text):
                continue
            def sub(m):
                nonlocal n_ref
                old = int(m.group(2))
                if old in mapping and mapping[old] != old:
                    n_ref += 1
                    return f"{m.group(1)}{mapping[old]}"
                return m.group(0)
            r.text = REF.sub(sub, r.text)

    print(f"캡션 {n_cap} · 본문 참조 {n_ref}")
    if not a.dry_run:
        BACKUP.mkdir(parents=True, exist_ok=True)
        bak = BACKUP / (DOC.name + ".bak-prerenumber")
        if not bak.exists():
            shutil.copy2(DOC, bak)
        doc.save(str(DOC))
        print("저장")
    else:
        print("(dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

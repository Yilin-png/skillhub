#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查生成的 .docx（无需 officecli）。build.py 每次构建后自动调用。

报告：所有 XML 部件是否良构；重复 pPr/tcPr；属性子元素顺序；
每张表的行列、合并（gridSpan / vMerge）、表头行灰底与居中、列宽；
封面分节 vAlign、目录、正文分页；脚注 / 公式数量。

用法：python scripts/inspect_docx.py out.docx [--json]
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ooxml import ORDERS, W_NS, get_val, local, w, wattr  # noqa: E402
from table_fit import grid_span, is_header_row, is_vmerge_continue  # noqa: E402

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _order_problems(root: ET.Element) -> list[str]:
    probs = []
    for el in root.iter():
        name = local(el.tag)
        if not el.tag.startswith(f"{{{W_NS}}}") or name not in ORDERS:
            continue
        order = {n: i for i, n in enumerate(ORDERS[name])}
        if "footerReference" in order:  # EG_HdrFtrReferences：页眉页脚引用可任意交错
            order["footerReference"] = order["headerReference"]
        last = -1
        for c in el:
            if not c.tag.startswith(f"{{{W_NS}}}"):
                continue
            i = order.get(local(c.tag))
            if i is None:
                continue
            if i < last:
                probs.append(f"<w:{name}> 中 <w:{local(c.tag)}> 顺序不符合 schema")
                break
            last = i
        tags = [c.tag for c in el if c.tag.startswith(f"{{{W_NS}}}")
                and local(c.tag) not in ("headerReference", "footerReference")]
        if len(tags) != len(set(tags)):
            probs.append(f"<w:{name}> 中有重复的子元素")
    return probs


def inspect(path: Path) -> dict:
    path = Path(path)
    rep: dict = {"file": str(path), "errors": [], "warnings": []}
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            rep["errors"].append(f"zip 损坏：{bad}")
        names = z.namelist()
        if any("\\" in n for n in names):
            rep["errors"].append("zip 路径含反斜杠")
        for n in names:
            if n.endswith(".xml") or n.endswith(".rels"):
                try:
                    ET.fromstring(z.read(n))
                except ET.ParseError as e:
                    rep["errors"].append(f"{n} 不是良构 XML：{e}")
        doc = ET.fromstring(z.read("word/document.xml"))
        has_footnotes = "word/footnotes.xml" in names

    # duplicates & order
    dup = 0
    for tag, pr in (("p", "pPr"), ("tc", "tcPr"), ("tbl", "tblPr"), ("r", "rPr")):
        for el in doc.iter(w(tag)):
            if len(el.findall(w(pr))) > 1:
                dup += 1
    if dup:
        rep["errors"].append(f"{dup} 处元素含重复的 pPr/tcPr/tblPr/rPr")
    order = _order_problems(doc)
    if order:
        rep["warnings"].append(f"{len(order)} 处属性顺序不符合 schema，例：{order[0]}")

    body = doc.find(w("body"))
    tables = []
    for tbl in doc.iter(w("tbl")):
        grid = [int(g.get(wattr("w"), "0") or 0)
                for g in tbl.findall(f"{w('tblGrid')}/{w('gridCol')}")]
        t = {"rows": 0, "cols": len(grid), "gridSpan": 0, "vMergeRestart": 0,
             "vMergeContinue": 0, "headerRows": 0, "headerGray": True,
             "headerCentered": True, "colWidths": grid}
        tw = tbl.find(f"{w('tblPr')}/{w('tblW')}")
        t["tblW"] = f"{get_val(tw, 'w')}/{get_val(tw, 'type')}" if tw is not None else None
        for tr in tbl.findall(w("tr")):
            t["rows"] += 1
            hdr = is_header_row(tr)
            t["headerRows"] += hdr
            for tc in tr.findall(w("tc")):
                cont = is_vmerge_continue(tc)
                if grid_span(tc) > 1 and not cont:
                    t["gridSpan"] += 1
                vm = tc.find(f"{w('tcPr')}/{w('vMerge')}")
                if vm is not None:
                    t["vMergeContinue" if cont else "vMergeRestart"] += 1
                if hdr:
                    shd = tc.find(f"{w('tcPr')}/{w('shd')}")
                    if shd is None or (get_val(shd, "fill") or "").upper() in ("", "AUTO", "FFFFFF"):
                        t["headerGray"] = False
                    for p in tc.findall(w("p")):
                        jc = p.find(f"{w('pPr')}/{w('jc')}")
                        if get_val(jc) != "center":
                            t["headerCentered"] = False
        if not t["headerRows"]:
            t["headerGray"] = t["headerCentered"] = None
        tables.append(t)
    rep["tables"] = tables

    sects = []
    for s in doc.iter(w("sectPr")):
        sects.append(get_val(s.find(w("vAlign"))) or "top(default)")
    rep["sections"] = sects
    rep["toc"] = any((get_val(g) or "").lower() == "table of contents"
                     for g in doc.iter(w("docPartGallery")))
    rep["pageBreakBefore"] = sum(
        1 for e in doc.iter(w("pageBreakBefore")) if (get_val(e) or "1") not in ("0", "false"))
    rep["footnotes"] = sum(1 for _ in doc.iter(w("footnoteReference"))) if has_footnotes else 0
    rep["equations"] = sum(1 for _ in doc.iter(f"{{{M_NS}}}oMath"))
    rep["paragraphs"] = sum(1 for _ in body.iter(w("p"))) if body is not None else 0
    return rep


def summarize(rep: dict) -> str:
    lines = [f"文件：{rep['file']}"]
    lines.append(f"分节：{len(rep['sections'])}（vAlign：{', '.join(rep['sections'])}）；"
                 f"目录：{'有' if rep['toc'] else '无'}；脚注 {rep['footnotes']}；公式 {rep['equations']}")
    for i, t in enumerate(rep["tables"], 1):
        hdr = ("无表头行" if t["headerRows"] == 0 else
               f"表头 {t['headerRows']} 行 灰底{'✓' if t['headerGray'] else '✗'} "
               f"居中{'✓' if t['headerCentered'] else '✗'}")
        lines.append(f"  表{i}: {t['rows']}×{t['cols']} 宽={t['tblW']} "
                     f"colspan {t['gridSpan']} / rowspan {t['vMergeRestart']} "
                     f"(续 {t['vMergeContinue']})；{hdr}；列宽 {t['colWidths']}")
    for e in rep["errors"]:
        lines.append(f"ERROR {e}")
    for wn in rep["warnings"]:
        lines.append(f"WARN  {wn}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("docx", type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rep = inspect(a.docx)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else summarize(rep))
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())

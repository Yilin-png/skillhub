#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Post-process a pandoc DOCX: cover vAlign, TOC/body break, table header/width.

与旧版（正则改 XML）相比：
- 样式按 ``w:name`` 从 styles.xml 解析 styleId，不再硬编码 ``a6`` / ``11`` 等
  （换一份 reference.docx，ID 就会变；旧版把 Bibliography 当成了封面样式）。
- 基于 XML 树修改：不会再产生重复的 tcPr / pPr，元素按 schema 顺序写入。
- 目录 → 正文的分页用正文首段的 ``pageBreakBefore``，不再插一个只含分页符的
  空段（那会在正文页顶多出一个空行，并把首个标题的书签留在目录页）。
- 分节符直接写进封面最后一段的 pPr，不再额外插空段（空段会使"垂直居中"偏上）。
- 只给真正的表头行（``w:tblHeader``，来自 ``<thead>``）上灰底/居中；
  无表头的表不再把第一行数据误染成灰色。
- 幂等：重复执行不会叠加分节/分页。
"""
from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ooxml import (  # noqa: E402
    Docx, ensure_pr, get_val, normalize_order, set_prop, sort_children,
    style_ids_by_name,
    text_of, w, wattr,
)
from table_fit import fit_table, is_header_row, set_para_jc  # noqa: E402

HEADER_FILL = "D9D9D9"  # Word「灰色 25%」
DEFAULT_PAGE_W, DEFAULT_MARGIN = 11906, 1440  # A4, 1 inch

COVER_STYLE_NAMES = ("title", "subtitle", "author", "date", "abstract", "abstract title")
TOC_HEADING_NAMES = ("toc heading",)
BOOKMARK_TAGS = {w("bookmarkStart"), w("bookmarkEnd")}


def _ids(name_map: dict[str, str], names) -> set[str]:
    out = set()
    for n in names:
        if n in name_map:
            out.add(name_map[n])
        # pandoc 用英文名生成 id，样式缺失时 pandoc 会写入同名 id
        out.add(n.title().replace(" ", ""))
    return out


def p_style(p: ET.Element) -> str | None:
    ppr = p.find(w("pPr"))
    return get_val(ppr.find(w("pStyle"))) if ppr is not None else None


def _content_width(sect: ET.Element | None) -> int:
    page_w, ml, mr = DEFAULT_PAGE_W, DEFAULT_MARGIN, DEFAULT_MARGIN
    if sect is not None:
        pgsz, pgmar = sect.find(w("pgSz")), sect.find(w("pgMar"))
        try:
            if pgsz is not None and pgsz.get(wattr("w")):
                page_w = int(pgsz.get(wattr("w")))
            if pgmar is not None:
                ml = int(pgmar.get(wattr("left"), ml))
                mr = int(pgmar.get(wattr("right"), mr))
                ml += int(pgmar.get(wattr("gutter"), 0) or 0)
        except ValueError:
            pass
    width = page_w - ml - mr
    return width if width > 1000 else DEFAULT_PAGE_W - 2 * DEFAULT_MARGIN


def _is_toc_sdt(el: ET.Element) -> bool:
    if el.tag != w("sdt"):
        return False
    for g in el.iter(w("docPartGallery")):
        if (get_val(g) or "").lower() == "table of contents":
            return True
    return False


def _set_valign(sect: ET.Element, val: str | None) -> None:
    for old in sect.findall(w("vAlign")):
        sect.remove(old)
    if val:
        set_prop(sect, "vAlign", {"val": val})


def _page_break_para() -> ET.Element:
    p = ET.Element(w("p"))
    r = ET.SubElement(p, w("r"))
    ET.SubElement(r, w("br"), {wattr("type"): "page"})
    return p


def _style_header_rows(tbl: ET.Element, fill: str | None, center: bool) -> int:
    n = 0
    for tr in tbl.findall(w("tr")):
        if not is_header_row(tr):
            continue
        n += 1
        for tc in tr.findall(w("tc")):
            if fill:
                set_prop(ensure_pr(tc, "tcPr"), "shd",
                         {"val": "clear", "color": "auto", "fill": fill})
            if center:
                for p in tc.findall(w("p")):
                    set_para_jc(p, "center")
    return n


def apply_layout(
    docx_path: Path,
    *,
    cover_center: bool = True,
    center_headers: bool = True,
    shade_headers: bool = True,
    full_width_tables: bool = True,
    header_fill: str = HEADER_FILL,
) -> dict:
    """Mutate ``docx_path`` in place. Returns a small report dict."""
    doc = Docx(Path(docx_path))
    part = doc.xml("word/document.xml")
    if part is None:
        raise RuntimeError("word/document.xml 不存在")
    names = style_ids_by_name(doc.xml("word/styles.xml"))
    cover_ids = _ids(names, COVER_STYLE_NAMES)
    toc_heading_ids = _ids(names, TOC_HEADING_NAMES)

    root = part.root
    body = root.find(w("body"))
    if body is None:
        raise RuntimeError("document.xml 中没有 <w:body>")
    final_sect = body.find(w("sectPr"))
    if final_sect is None or list(body)[-1] is not final_sect:
        if final_sect is not None:
            body.remove(final_sect)
        else:
            final_sect = ET.Element(w("sectPr"))
        body.append(final_sect)
    report: dict = {"tables": 0, "header_rows": 0, "cover": False, "toc": False}

    # ---- tables
    parent = {c: p for p in root.iter() for c in p}
    width = _content_width(final_sect)
    for tbl in list(root.iter(w("tbl"))):
        report["tables"] += 1
        nested = False
        anc = parent.get(tbl)
        while anc is not None:
            if anc.tag == w("tc"):
                nested = True
                break
            anc = parent.get(anc)
        if full_width_tables and not nested:
            fit_table(tbl, width)
        report["header_rows"] += _style_header_rows(
            tbl, header_fill if shade_headers else None, center_headers)

    # ---- cover / TOC / body
    children = list(body)
    i, last_cover = 0, None
    while i < len(children):
        el = children[i]
        if el.tag in BOOKMARK_TAGS:
            i += 1
            continue
        if el.tag == w("p"):
            st = p_style(el)
            if st in cover_ids:
                last_cover = el
                i += 1
                continue
            if st is None and not text_of(el).strip() and last_cover is not None:
                i += 1  # blank spacer inside cover block
                continue
        break

    toc_idx = None
    for j in range(i, len(children)):
        if _is_toc_sdt(children[j]):
            toc_idx = j
            break
        if children[j].tag in BOOKMARK_TAGS:
            continue
        break  # TOC (if any) must directly follow the cover

    if last_cover is not None:
        report["cover"] = True
        ppr = ensure_pr(last_cover, "pPr")
        if ppr.find(w("sectPr")) is None:  # idempotent
            sect = copy.deepcopy(final_sect)
            for t in sect.findall(w("type")):
                sect.remove(t)  # default = nextPage
            _set_valign(sect, "center" if cover_center else None)
            ppr.append(sect)
            sort_children(ppr)
        if cover_center:
            _set_valign(final_sect, "top")

    if toc_idx is not None:
        report["toc"] = True
        sdt = children[toc_idx]
        if last_cover is not None:
            for p in sdt.iter(w("p")):
                if p_style(p) in toc_heading_ids:
                    set_prop(ensure_pr(p, "pPr"), "pageBreakBefore", {"val": "0"})
                    break
        # first block after the TOC → starts on a new page
        k = toc_idx + 1
        while k < len(children) and children[k].tag in BOOKMARK_TAGS:
            k += 1
        if k < len(children) and children[k] is not final_sect:
            nxt = children[k]
            if nxt.tag == w("p"):
                set_prop(ensure_pr(nxt, "pPr"), "pageBreakBefore", {})
            else:
                # 首个块是表格等：插入分页段（放在 sdt 之后、书签之前）
                prev = children[toc_idx + 1] if toc_idx + 1 < len(children) else None
                is_break = (prev is not None and prev.tag == w("p")
                            and prev.find(f".//{w('br')}[@{wattr('type')}='page']") is not None)
                if not is_break:
                    body.insert(list(body).index(sdt) + 1, _page_break_para())
            report["toc_break"] = True

    normalize_order(root)
    doc.parts["word/document.xml"] = part.tobytes()
    doc.save()
    return report


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="对已有 pandoc docx 单独执行版式后处理")
    ap.add_argument("docx", type=Path)
    ap.add_argument("--no-cover-center", action="store_true")
    a = ap.parse_args()
    print(apply_layout(a.docx, cover_center=not a.no_cover_center))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Content-aware table column widths and cell padding (HTML preview + OOXML).

列宽启发式（序号列收窄、长文本列加宽）与原版一致；OOXML 改写改为基于
ElementTree，并按 schema 顺序写入 tcPr / tblPr，避免重复 tcPr。
"""
from __future__ import annotations

import html as _html
import math
import re
import xml.etree.ElementTree as ET
from typing import Iterable

from ooxml import ensure_pr, get_val, is_on, set_prop, sort_children, text_of, w, wattr

KIND_INDEX = "index"
KIND_STATUS = "status"
KIND_SHORT = "short"
KIND_MEDIUM = "medium"
KIND_TEXT = "text"

# Header tokens → index / status (content length can still upgrade short→text)
INDEX_HEADERS = frozenset(
    {
        "序号",
        "编号",
        "项次",
        "号",
        "no",
        "no.",
        "#",
        "n",
        "seq",
        "index",
    }
)
STATUS_HEADERS = frozenset(
    {
        "状态",
        "口径",
        "是否",
        "结果",
        "处分结果",
        "处罚结果",
    }
)

# Relative weights before percent clamp
BASE_WEIGHT = {
    KIND_INDEX: 7.5,
    KIND_STATUS: 12.0,
    KIND_SHORT: 16.0,
    KIND_MEDIUM: 24.0,
    KIND_TEXT: 40.0,
}

# Cell margins in twips (top, right, bottom, left)
KIND_MARGINS: dict[str, tuple[int, int, int, int]] = {
    KIND_INDEX: (40, 40, 40, 40),
    KIND_STATUS: (50, 60, 50, 60),
    KIND_SHORT: (60, 80, 60, 80),
    KIND_MEDIUM: (70, 110, 70, 110),
    KIND_TEXT: (80, 140, 80, 140),
}

KIND_RANK = {
    KIND_INDEX: 0,
    KIND_STATUS: 1,
    KIND_SHORT: 2,
    KIND_MEDIUM: 3,
    KIND_TEXT: 4,
}



def display_len(text: str) -> int:
    """Visual width: CJK ≈ 2, ASCII ≈ 1."""
    n = 0
    for ch in text:
        o = ord(ch)
        n += 2 if o > 0x2E7F else 1
    return n


def norm_header(text: str) -> str:
    s = re.sub(r"\s+", "", text or "")
    s = s.replace("／", "/").replace("（", "(").replace("）", ")")
    return s.strip().lower()


def column_kind(header: str, body_texts: Iterable[str]) -> str:
    h = norm_header(header)
    texts = [t.strip() for t in body_texts if t and t.strip()]
    lens = [display_len(t) for t in texts]
    avg = sum(lens) / len(lens) if lens else display_len(header or "")
    mx = max(lens) if lens else display_len(header or "")

    if h in INDEX_HEADERS or "序号" in (header or ""):
        return KIND_INDEX
    if texts and avg <= 4 and mx <= 6:
        if all(re.fullmatch(r"\d{1,4}[.)、]?", t) for t in texts):
            return KIND_INDEX

    if avg <= 10 and mx <= 18:
        kind = KIND_SHORT
    elif avg <= 24 and mx <= 52:
        kind = KIND_MEDIUM
    else:
        kind = KIND_TEXT

    if h in STATUS_HEADERS and kind in (KIND_SHORT, KIND_MEDIUM, KIND_INDEX):
        return KIND_STATUS
    return kind


def column_weight(kind: str, header: str, body_texts: Iterable[str]) -> float:
    texts = [t.strip() for t in body_texts if t and t.strip()]
    lens = [display_len(t) for t in texts]
    avg = sum(lens) / len(lens) if lens else display_len(header or "")
    w = BASE_WEIGHT.get(kind, BASE_WEIGHT[KIND_MEDIUM])
    if kind == KIND_TEXT:
        w += min(18.0, math.log1p(avg) * 3.2)
    elif kind == KIND_MEDIUM:
        w += min(6.0, avg / 12.0)
    return w


def _finalize_percents(weights: list[float], kinds: list[str],
                       mins: list[float] | None = None) -> list[float]:
    n = len(weights)
    total = sum(weights) or 1.0
    pct = [100.0 * w / total for w in weights]

    caps = {
        KIND_INDEX: (6.5, 10.5),
        KIND_STATUS: (9.0, 16.0),
        KIND_SHORT: (8.0, 24.0),
        KIND_MEDIUM: (12.0, 34.0),
        KIND_TEXT: (16.0, 72.0),
    }
    if n == 2:
        caps[KIND_TEXT] = (20.0, 88.0)
        caps[KIND_SHORT] = (12.0, 40.0)
    if n >= 5:
        caps[KIND_TEXT] = (12.0, 55.0)
        caps[KIND_INDEX] = (5.5, 9.5)

    def apply_caps() -> None:
        for i, k in enumerate(kinds):
            lo, hi = caps.get(k, (8.0, 60.0))
            if mins:
                lo = min(hi, max(lo, mins[i]))
            pct[i] = min(hi, max(lo, pct[i]))

    apply_caps()
    for _ in range(10):
        diff = 100.0 - sum(pct)
        if abs(diff) < 0.08:
            break
        targets = [i for i, k in enumerate(kinds) if k == KIND_TEXT]
        if not targets:
            targets = [i for i, k in enumerate(kinds) if k != KIND_INDEX]
        if not targets:
            targets = list(range(n))
        each = diff / len(targets)
        for i in targets:
            pct[i] += each
        apply_caps()

    s = sum(pct) or 1.0
    return [p * 100.0 / s for p in pct]


def column_kinds_and_percents(
    headers: list[str],
    bodies: list[list[str]],
    target_dxa: int | None = None,
) -> tuple[list[str], list[float]]:
    n = len(headers)
    if n == 0:
        return [], []
    while len(bodies) < n:
        bodies.append([])
    kinds = [column_kind(headers[i], bodies[i]) for i in range(n)]
    weights = [column_weight(kinds[i], headers[i], bodies[i]) for i in range(n)]
    mins = [_label_min_pct(kinds[i], headers[i], bodies[i], target_dxa) for i in range(n)]
    return kinds, _finalize_percents(weights, kinds, mins)


# 正文 12pt ≈ 240 twips / 汉字；短标签列至少放得下最长标签（最多 8 个汉字）
CJK_CHAR_DXA = 240
NOMINAL_WIDTH_DXA = 8300


def _label_min_pct(kind: str, header: str, body: list[str], target_dxa: int | None) -> float:
    if kind not in (KIND_INDEX, KIND_STATUS, KIND_SHORT):
        return 0.0
    texts = [t.strip() for t in list(body) + [header or ""] if t and t.strip()]
    if not texts:
        return 0.0
    longest = min(16, max(display_len(t) for t in texts))  # display units (CJK=2)
    _, right, _, left = KIND_MARGINS[kind]
    need = longest / 2 * CJK_CHAR_DXA + left + right + 60
    return 100.0 * need / (target_dxa or NOMINAL_WIDTH_DXA)


def distribute_int(weights: list[int], target: int) -> list[int]:
    n = len(weights)
    if n == 0:
        return []
    total = sum(weights)
    if total <= 0:
        base, rem = divmod(target, n)
        return [base + (1 if i < rem else 0) for i in range(n)]
    raw = [w * target / total for w in weights]
    ints = [int(x) for x in raw]
    remainder = target - sum(ints)
    order = sorted(range(n), key=lambda i: (raw[i] - ints[i]), reverse=True)
    if remainder > 0:
        for i in range(remainder):
            ints[order[i % n]] += 1
    elif remainder < 0:
        for i in range(-remainder):
            j = order[-(i % n) - 1]
            if ints[j] > 1:
                ints[j] -= 1
    return ints


def percents_to_dxa(pcts: list[float], target_dxa: int) -> list[int]:
    weights = [max(1, int(round(p * 100))) for p in pcts]
    return distribute_int(weights, target_dxa)


def max_kind(kinds: list[str]) -> str:
    if not kinds:
        return KIND_MEDIUM
    return max(kinds, key=lambda k: KIND_RANK.get(k, 2))


# ----- HTML (intermediate preview + better pandoc first-pass grid) -----

_CELL_RE = re.compile(
    r"<(t[hd])(\s[^>]*)?>([\s\S]*?)</\1>",
    re.IGNORECASE,
)


def _strip_tags(html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


def _row_cells_expanded(row_html: str) -> list[str]:
    out: list[str] = []
    for m in _CELL_RE.finditer(row_html):
        attrs = m.group(2) or ""
        text = _strip_tags(m.group(3))
        span_m = re.search(r"colspan\s*=\s*[\"']?(\d+)", attrs, re.I)
        span = int(span_m.group(1)) if span_m else 1
        out.extend([text] * max(1, span))
    return out


def parse_html_table_columns(
    table_html: str,
) -> tuple[list[str], list[list[str]], int]:
    rows = re.findall(r"<tr\b[^>]*>([\s\S]*?)</tr>", table_html, flags=re.I)
    if not rows:
        return [], [], 0
    headers = _row_cells_expanded(rows[0])
    ncols = len(headers)
    if ncols == 0:
        return [], [], 0
    bodies: list[list[str]] = [[] for _ in range(ncols)]
    for row in rows[1:]:
        cells = _row_cells_expanded(row)
        if len(cells) != ncols:
            continue
        for i, text in enumerate(cells):
            bodies[i].append(text)
    return headers, bodies, ncols


def inject_html_colgroups(html: str) -> str:
    """Insert <colgroup> with content-aware widths into each HTML table."""

    def repl(m: re.Match[str]) -> str:
        tbl = m.group(0)
        if re.search(r"<colgroup\b", tbl, re.I):
            return tbl
        headers, bodies, ncols = parse_html_table_columns(tbl)
        if ncols < 2:
            return tbl
        kinds, pcts = column_kinds_and_percents(headers, bodies)
        cols = [
            f'<col class="col-{k}" style="width:{p:.1f}%" />'
            for k, p in zip(kinds, pcts)
        ]
        cg = "<colgroup>" + "".join(cols) + "</colgroup>"
        return re.sub(r"(<table\b[^>]*>)", r"\1" + cg, tbl, count=1, flags=re.I)

    return re.sub(r"<table\b[^>]*>[\s\S]*?</table>", repl, html, flags=re.I)


# ----- OOXML (ElementTree) -----

def grid_span(tc: ET.Element) -> int:
    tcpr = tc.find(w("tcPr"))
    v = get_val(tcpr.find(w("gridSpan"))) if tcpr is not None else None
    try:
        return max(1, int(v)) if v else 1
    except ValueError:
        return 1


def is_vmerge_continue(tc: ET.Element) -> bool:
    tcpr = tc.find(w("tcPr"))
    vm = tcpr.find(w("vMerge")) if tcpr is not None else None
    if vm is None:
        return False
    return (get_val(vm) or "continue") != "restart"


def is_header_row(tr: ET.Element) -> bool:
    trpr = tr.find(w("trPr"))
    return trpr is not None and is_on(trpr.find(w("tblHeader")))


def _grid_before(tr: ET.Element) -> int:
    trpr = tr.find(w("trPr"))
    v = get_val(trpr.find(w("gridBefore"))) if trpr is not None else None
    try:
        return int(v) if v else 0
    except ValueError:
        return 0


def iter_row_cells(tr: ET.Element, ncols: int):
    """Yield (col_index, span, tc) for each cell, honouring gridBefore/gridSpan."""
    col = _grid_before(tr)
    for tc in tr.findall(w("tc")):
        if col >= ncols:
            break
        span = min(grid_span(tc), ncols - col)
        yield col, span, tc
        col += span


def extract_docx_columns(tbl: ET.Element, ncols: int) -> tuple[list[str], list[list[str]]]:
    headers = [""] * ncols
    bodies: list[list[str]] = [[] for _ in range(ncols)]
    rows = tbl.findall(w("tr"))
    header_idx = {i for i, tr in enumerate(rows) if is_header_row(tr)}
    if not header_idx and rows:
        header_idx = {0}  # 仅用于判断列类型；不会据此上灰底
    for ri, tr in enumerate(rows):
        for col, span, tc in iter_row_cells(tr, ncols):
            if is_vmerge_continue(tc):
                continue
            text = text_of(tc)
            for c in range(col, col + span):
                if ri in header_idx:
                    if not headers[c]:
                        headers[c] = text
                else:
                    bodies[c].append(text)
    return headers, bodies


def _tc_mar(kind: str) -> list[ET.Element]:
    top, right, bottom, left = KIND_MARGINS.get(kind, KIND_MARGINS[KIND_MEDIUM])
    out = []
    for name, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        out.append(ET.Element(w(name), {wattr("w"): str(val), wattr("type"): "dxa"}))
    return out


def set_para_jc(p: ET.Element, val: str) -> None:
    set_prop(ensure_pr(p, "pPr"), "jc", {"val": val})


def _relax_spacing(p: ET.Element) -> None:
    ppr = ensure_pr(p, "pPr")
    if ppr.find(w("spacing")) is None:
        set_prop(ppr, "spacing", {"before": "40", "after": "80"})


def fit_table(tbl: ET.Element, target_dxa: int) -> dict:
    """Full-width + content-aware widths/padding for one table (in place)."""
    tblpr = ensure_pr(tbl, "tblPr")
    set_prop(tblpr, "tblW", {"w": "5000", "type": "pct"})
    set_prop(tblpr, "tblLayout", {"type": "fixed"})

    grid = tbl.find(w("tblGrid"))
    cols = grid.findall(w("gridCol")) if grid is not None else []
    ncols = len(cols)
    if ncols == 0:
        return {"cols": 0}
    headers, bodies = extract_docx_columns(tbl, ncols)
    kinds, pcts = column_kinds_and_percents(headers, bodies, target_dxa)
    if len(kinds) != ncols:
        kinds, pcts = [KIND_MEDIUM] * ncols, [100.0 / ncols] * ncols
    widths = percents_to_dxa(pcts, target_dxa)
    for gc, wd in zip(cols, widths):
        gc.set(wattr("w"), str(wd))

    for tr in tbl.findall(w("tr")):
        for col, span, tc in iter_row_cells(tr, ncols):
            kind = kinds[col] if span == 1 else max_kind(kinds[col:col + span])
            tcpr = ensure_pr(tc, "tcPr")
            set_prop(tcpr, "tcW", {"w": str(sum(widths[col:col + span])), "type": "dxa"})
            set_prop(tcpr, "tcMar", children=_tc_mar(kind))
            set_prop(tcpr, "vAlign",
                     {"val": "center" if kind in (KIND_INDEX, KIND_STATUS, KIND_SHORT) else "top"})
            paras = tc.findall(w("p"))
            if kind == KIND_INDEX:
                for p in paras:
                    set_para_jc(p, "center")
            elif kind == KIND_TEXT:
                for p in paras:
                    _relax_spacing(p)
    sort_children(tblpr)
    return {"cols": ncols, "kinds": kinds, "widths": widths}


def _self_check() -> None:
    headers = ["序号", "观察点", "公开信息摘要", "状态"]
    bodies = [
        ["1", "2", "3", "4"],
        ["主体身份", "上市状态", "控制权"],
        [
            "统一社会信用代码 91330108MA27YJ5H56；法定代表人王兴兴；住所杭州市滨江区。",
            "2026年8月19日科创板挂牌，代码 688836，发行价 150.80 元／股。",
        ],
        ["多源一致", "发行文件确认", "招股书转述"],
    ]
    kinds, pcts = column_kinds_and_percents(headers, bodies)
    assert kinds[0] == KIND_INDEX, kinds
    assert kinds[2] == KIND_TEXT, kinds
    assert pcts[0] < pcts[2], pcts
    assert pcts[0] <= 11.0, pcts
    assert abs(sum(pcts) - 100) < 0.2, pcts
    assert sum(percents_to_dxa(pcts, 9026)) == 9026
    print("table_fit self-check ok", kinds, [round(p, 1) for p in pcts])


if __name__ == "__main__":
    _self_check()

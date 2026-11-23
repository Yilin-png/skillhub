"""股权架构图 SVG 渲染器（纯标准库），PE/VC 法律尽调风格。

自上而下：上层股东（穿透）→ 直接股东 → 标的公司（灰底）→ 下属子公司。
连线左侧标「持股 xx%」「认缴 xx 单位」，表决权与持股不一致时另标「表决权 xx%」。
性质加括号放在主体名称下面。宋体、黑色细线、实际控制人与标的公司灰底。
方框尺寸与基金架构图同一套规则：按文字加小内边距，同层协调，穿透层不小于直接股东。
"""
from __future__ import annotations

import unicodedata
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from xml.sax.saxutils import escape

__all__ = [
    "render_svg",
    "normalize",
    "compute_ratios",
    "format_amount",
    "format_ratio",
    "check",
    "DEFAULTS",
]

SCALE = 72
GREY = "#d9d9d9"
LINE_W = 1.1
FONT_FAMILY = (
    "SimSun, 宋体, NSimSun, 'Songti SC', STSong, 'Noto Serif CJK SC', "
    "'Source Han Serif SC', 'Noto Serif SC', serif"
)
GP_ROLES = {"GP", "普通合伙人", "执行事务合伙人"}
ROLE_TEXT = {
    "GP": "普通合伙人",
    "LP": "有限合伙人",
    "实际控制人": "实际控制人",
    "控股股东": "控股股东",
}
HIGHLIGHT_ROLES = {"实际控制人", "普通合伙人", "执行事务合伙人"}

DEFAULTS = {
    "title": "股权架构图",
    "as_of": "",
    "unit": "万元",
    "show_ratio": True,
    "show_amount": True,
    "max_per_row": 6,
}

MARGIN = 0.4
PAD_X, PAD_Y = 0.16, 0.12
MIN_BOX_W = 1.0
LINE_SPACING = 1.35
HOLDER_MAX_W = 2.6
ROW_GAP = 0.35
LOOK_STEM = 0.15
TARGET_MAX_W = 4.4
SUB_MAX_W, SUB_MAX_W_MULTI = 4.4, 3.0
BOX_GAP = 0.4
LABEL_GAP = 0.08
BUS_TO_TARGET = 0.6
TITLE_GAP = 0.28


def _dec(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "").replace("，", "")
    for suffix in ("%", "％", "万元", "元"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"无法识别的数字：{value!r}") from exc


def format_amount(value) -> str:
    d = _dec(value)
    if d is None:
        return ""
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d:,.4f}".rstrip("0").rstrip(".")


def format_ratio(value) -> str:
    """至少两位小数；给定值更精确时保留原精度。"""
    d = _dec(value)
    if d is None:
        return ""
    if d.as_tuple().exponent < -2:
        return f"{d}%"
    return f"{d.quantize(Decimal('0.01')):.2f}%"


def compute_ratios(amounts):
    """按认缴金额计算百分比（两位小数），最大余数法保证合计恰为 100.00%。"""
    decs = [_dec(a) or Decimal(0) for a in amounts]
    total = sum(decs)
    if total <= 0:
        return [None] * len(decs)
    cent = Decimal("0.01")
    exact = [a * 100 / total for a in decs]
    floors = [e.quantize(cent, rounding=ROUND_DOWN) for e in exact]
    remaining = int(((Decimal(100) - sum(floors)) / cent).to_integral_value())
    order = sorted(range(len(decs)), key=lambda i: exact[i] - floors[i], reverse=True)
    for i in order[:remaining]:
        floors[i] += cent
    return floors


def _is_gp(role: str) -> bool:
    role = (role or "").strip()
    return role in GP_ROLES or role.upper().startswith("GP")


def _nature(role: str, form: str) -> str:
    """方框第二行：身份优先于组织形式。自然人不写「自然人」。"""
    if role:
        return ROLE_TEXT.get(role.upper(), ROLE_TEXT.get(role, role))
    return form


def _normalize_holders(items) -> list:
    holders = []
    for p in items or []:
        if isinstance(p, str):
            p = {"name": p}
        role = str(p.get("role") or "").strip()
        form = str(p.get("form") or "").strip()
        nested = _normalize_holders(p.get("shareholders"))
        highlight = p.get("highlight")
        nature = _nature(role, form)
        holders.append(
            {
                "name": str(p.get("name") or "").strip(),
                "role": ROLE_TEXT.get(role.upper(), role),
                "form": form,
                "nature": nature,
                "amount": _dec(p.get("amount")),
                "ratio": _dec(p.get("ratio")),
                "voting": _dec(p.get("voting")),
                "note": str(p.get("note") or "").strip(),
                "penetrate": bool(p.get("penetrate")) or bool(nested),
                "highlight": (nature in HIGHLIGHT_ROLES or _is_gp(role)) if highlight is None else bool(highlight),
                "shareholders": nested,
            }
        )
    if holders and all(p["amount"] is not None for p in holders):
        for p, r in zip(holders, compute_ratios([p["amount"] for p in holders])):
            if p["ratio"] is None:
                p["ratio"] = r
    return holders


def normalize(data: dict) -> dict:
    data = dict(data or {})
    out = {k: data.get(k, v) for k, v in DEFAULTS.items()}
    out["font_family"] = data.get("font_family") or FONT_FAMILY
    as_of = str(data.get("as_of") or "").strip()
    if as_of.startswith("截至"):
        as_of = as_of[2:].strip()
    out["as_of"] = as_of

    target = data.get("target") or {}
    if isinstance(target, str):
        target = {"name": target}
    out["target"] = {
        "name": str(target.get("name") or "标的公司").strip(),
        "form": str(target.get("form") or "").strip(),
        "capital": _dec(target.get("capital")),
    }
    out["shareholders"] = _normalize_holders(data.get("shareholders"))

    subs = []
    for p in data.get("subsidiaries") or []:
        if isinstance(p, str):
            p = {"name": p}
        if not str(p.get("name") or "").strip():
            continue
        subs.append(
            {
                "name": str(p["name"]).strip(),
                "form": str(p.get("form") or "").strip(),
                "ratio": _dec(p.get("ratio")),
                "note": str(p.get("note") or "").strip(),
            }
        )
    out["subsidiaries"] = subs
    return out


def _check_level(holders, owner, msgs) -> None:
    where = f"「{owner}」的股东" if owner else "直接股东"
    for i, p in enumerate(holders, 1):
        if not p["name"]:
            msgs.append(f"{where}第 {i} 位缺少名称。")
        if p["ratio"] is None and p["amount"] is None:
            msgs.append(f"「{p['name'] or i}」既无持股比例也无认缴金额。")
        if p["penetrate"] and not p["shareholders"]:
            msgs.append(f"「{p['name']}」需要向上穿透，但未列出其股东。")
        _check_level(p["shareholders"], p["name"], msgs)
    ratios = [p["ratio"] for p in holders if p["ratio"] is not None]
    if holders and len(ratios) == len(holders):
        total = sum(ratios)
        if abs(total - 100) > Decimal("0.01"):
            msgs.append(f"{where}持股比例合计为 {total:.2f}%，不等于 100%。")


def check(data: dict) -> list[str]:
    d = normalize(data)
    msgs = []
    if not d["target"]["name"]:
        msgs.append("未填写标的公司名称。")
    if not d["shareholders"]:
        msgs.append("未填写任何直接股东。")
    _check_level(d["shareholders"], "", msgs)
    capital = d["target"]["capital"]
    amounts = [p["amount"] for p in d["shareholders"]]
    if capital is not None and amounts and all(a is not None for a in amounts):
        total = sum(amounts)
        if abs(total - capital) > Decimal("0.01"):
            msgs.append(f"直接股东认缴合计 {format_amount(total)}，与标的公司注册资本 {format_amount(capital)} 不一致。")
    for s in d["subsidiaries"]:
        if s["ratio"] is None:
            msgs.append(f"子公司「{s['name']}」未填写持股比例。")
    return msgs


# ---------------------------------------------------------------- 文字度量

NO_LINE_START = set("）)】」』，,。.、；;：:！!？?%％")


def _char_em(ch: str) -> float:
    if ch == " ":
        return 0.3
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 1.0
    if ch in "ilI.,:;|!'`":
        return 0.3
    if ch.isupper() or ch in "mwMW%@":
        return 0.72
    return 0.55


def _text_em(text: str) -> float:
    return sum(_char_em(c) for c in text)


def _greedy(para: str, limit: float) -> list[str]:
    lines, cur, width = [], "", 0.0
    for ch in para:
        w = _char_em(ch)
        if cur and width + w > limit and ch not in NO_LINE_START:
            lines.append(cur)
            cur, width = "", 0.0
        cur += ch
        width += w
    lines.append(cur)
    return lines


def _wrap(text: str, max_em: float) -> list[str]:
    lines = []
    for para in str(text).split("\n"):
        n = len(_greedy(para, max_em)) or 1
        limit = _text_em(para) / n if n else max_em
        while limit < max_em and len(_greedy(para, limit)) > n:
            limit += 0.25
        lines.extend(_greedy(para, min(limit, max_em)))
    return lines


def _em(fs: float) -> float:
    return fs / SCALE


def _block_size(lines, fs):
    width = max((_text_em(s) for s in lines), default=0) * _em(fs)
    height = ((len(lines) - 1) * LINE_SPACING + 1) * _em(fs) if lines else 0
    return width, height


def _fit_box(text, fs, max_w):
    lines = _wrap(text, (max_w - 2 * PAD_X) / _em(fs))
    tw, th = _block_size(lines, fs)
    return lines, max(MIN_BOX_W, tw + 2 * PAD_X), th + 2 * PAD_Y


class _Canvas:
    def __init__(self, font_family):
        self.items = []
        self.font_family = font_family

    def rect(self, x, y, w, h, fill="white"):
        self.items.append(("rect", x, y, w, h, fill))

    def line(self, x1, y1, x2, y2, arrow=False):
        self.items.append(("line", x1, y1, x2, y2, arrow))

    def text(self, x, y, s, fs, anchor="middle", bold=False):
        self.items.append(("text", x, y, s, fs, anchor, bold))

    def lines_block(self, x, cy, lines, fs, anchor="middle"):
        lh = _em(fs) * LINE_SPACING
        first = cy - (len(lines) - 1) * lh / 2
        for i, s in enumerate(lines):
            self.text(x, first + i * lh + 0.35 * _em(fs), s, fs, anchor)

    def box(self, x, y, w, h, lines, fs=10, fill="white"):
        self.rect(x, y, w, h, fill)
        self.lines_block(x + w / 2, y + h / 2, lines, fs)
        return x + w / 2, y + h / 2

    def bbox(self):
        xs, ys = [], []
        for item in self.items:
            kind = item[0]
            if kind == "rect":
                _, x, y, w, h, _ = item
                xs += [x, x + w]
                ys += [y, y + h]
            elif kind == "line":
                _, x1, y1, x2, y2, _ = item
                xs += [x1, x2]
                ys += [y1, y2]
            else:
                _, x, y, txt, fs, anchor, _ = item
                w = _text_em(txt) * _em(fs)
                left = {"middle": x - w / 2, "end": x - w}.get(anchor, x)
                xs += [left, left + w]
                ys += [y - 0.9 * _em(fs), y + 0.2 * _em(fs)]
        return min(xs), min(ys), max(xs), max(ys)

    def to_svg(self, margin=MARGIN) -> str:
        s = SCALE
        x0, y0, x1, y1 = self.bbox()
        width, height = x1 - x0 + 2 * margin, y1 - y0 + 2 * margin
        dx, dy = margin - x0, margin - y0

        def n(v):
            return f"{v * s:.2f}".rstrip("0").rstrip(".")

        def nx(v):
            return n(v + dx)

        def ny(v):
            return n(v + dy)

        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(width)}" height="{n(height)}" '
            f'viewBox="0 0 {n(width)} {n(height)}" font-family="{escape(self.font_family, {chr(34): "&quot;"})}">',
            "<defs>",
            '<marker id="arrow" viewBox="0 0 10 8" refX="10" refY="4" markerWidth="8" markerHeight="6.4" '
            'markerUnits="userSpaceOnUse" orient="auto">',
            '<path d="M0,0 L10,4 L0,8 z" fill="black"/>',
            "</marker>",
            "</defs>",
            f'<rect x="0" y="0" width="{n(width)}" height="{n(height)}" fill="white"/>',
            f'<g stroke="black" stroke-width="{LINE_W}" fill="none">',
        ]
        texts = []
        for item in self.items:
            kind = item[0]
            if kind == "rect":
                _, x, y, w, h, fill = item
                out.append(f'<rect x="{nx(x)}" y="{ny(y)}" width="{n(w)}" height="{n(h)}" fill="{fill}"/>')
            elif kind == "line":
                _, lx1, ly1, lx2, ly2, arrow = item
                marker = ' marker-end="url(#arrow)"' if arrow else ""
                out.append(f'<line x1="{nx(lx1)}" y1="{ny(ly1)}" x2="{nx(lx2)}" y2="{ny(ly2)}"{marker}/>')
            else:
                _, x, y, txt, fs, anchor, bold = item
                weight = ' font-weight="bold"' if bold else ""
                texts.append(
                    f'<text x="{nx(x)}" y="{ny(y)}" font-size="{fs}" text-anchor="{anchor}"{weight}>'
                    f"{escape(txt)}</text>"
                )
        out.append("</g>")
        out.append('<g fill="black" stroke="none">')
        out.extend(texts)
        out.append("</g></svg>")
        return "\n".join(out) + "\n"


def render_svg(data: dict) -> str:
    d = normalize(data)
    c = _Canvas(d["font_family"])
    holders = d["shareholders"]
    unit = d["unit"]

    def connector_len(labels):
        _, h = _block_size(labels, 9)
        return max(0.45, h + 0.3)

    def walk(nodes):
        for p in nodes:
            yield p
            yield from walk(p["shareholders"])

    def node_label(p):
        label = []
        if d["show_ratio"] and p["ratio"] is not None:
            label.append("持股 " + format_ratio(p["ratio"]))
        if p["voting"] is not None and p["voting"] != p["ratio"]:
            label.append("表决权 " + format_ratio(p["voting"]))
        if d["show_amount"] and p["amount"] is not None:
            label.append(f"认缴 {format_amount(p['amount'])} {unit}".strip())
        if p["note"]:
            label.append(p["note"])
        return label

    def node_text(p):
        text = p["name"]
        if p["nature"]:
            text += f"\n（{p['nature']}）"
        return text

    all_nodes = list(walk(holders))
    for p in all_nodes:
        p["_lines"] = _fit_box(node_text(p), 10, HOLDER_MAX_W)[0]
        p["_label"] = node_label(p)
    base_w = max((_fit_box("\n".join(p["_lines"]), 10, HOLDER_MAX_W)[1] for p in all_nodes), default=MIN_BOX_W)
    base_h = max(
        (_fit_box("\n".join(p["_lines"]), 10, HOLDER_MAX_W)[2] for p in all_nodes),
        default=_fit_box("标的\n公司", 10, HOLDER_MAX_W)[2],
    )
    ph = base_h
    longest = max((p["_label"] for p in all_nodes), key=len, default=["持股"])
    conn = connector_len(longest)

    def label_w_of(p):
        return _block_size(p["_label"], 9)[0]

    def span(nodes):
        fps = [footprint(n) for n in nodes]
        cs = [0.0]
        for j in range(1, len(nodes)):
            step = max(fps[j - 1] / 2 + BOX_GAP + fps[j] / 2, label_w_of(nodes[j]) + LABEL_GAP + 0.2)
            cs.append(cs[-1] + step)
        return cs, cs[0] - fps[0] / 2, cs[-1] + fps[-1] / 2

    def footprint(node):
        if not node["shareholders"]:
            return base_w
        _, left, right = span(node["shareholders"])
        return max(base_w, right - left)

    def upper_height(node):
        if not node["shareholders"]:
            return 0.0
        return LOOK_STEM + conn + ph + max(upper_height(k) for k in node["shareholders"])

    def draw_uppers(node, cx, box_top):
        kids = node["shareholders"]
        if not kids:
            return
        cs, left, right = span(kids)
        cs = [x + cx - (left + right) / 2 for x in cs]
        bus = box_top - LOOK_STEM
        top = bus - conn - ph
        for k, x in zip(kids, cs):
            draw_uppers(k, x, top)
            c.box(x - base_w / 2, top, base_w, ph, k["_lines"], 10, GREY if k["highlight"] else "white")
            c.line(x, top + ph, x, bus)
            if k["_label"]:
                c.lines_block(x - LABEL_GAP, (top + ph + bus) / 2, k["_label"], 9, anchor="end")
        c.line(min(min(cs), cx), bus, max(max(cs), cx), bus)
        c.line(cx, bus, cx, box_top)

    n = len(holders)
    per_row = max(1, int(d["max_per_row"]))
    n_rows = -(-n // per_row) if n else 0
    rows, start = [], 0
    for r in range(n_rows):
        cnt = n // n_rows + (1 if r < n % n_rows else 0)
        rows.append(list(range(start, start + cnt)))
        start += cnt

    def row_centers(idx, trunk_through):
        cs = [0.0]
        widths = [footprint(holders[i]) for i in idx]
        for j in range(1, len(idx)):
            step = max(widths[j - 1] / 2 + BOX_GAP + widths[j] / 2, label_w_of(holders[idx[j]]) + LABEL_GAP + 0.2)
            cs.append(cs[-1] + step)
        if not trunk_through:
            left = cs[0] - widths[0] / 2
            right = cs[-1] + widths[-1] / 2
            return [x - (left + right) / 2 for x in cs]
        k = len(idx)
        a = k // 2 - 1 if k % 2 == 0 else k // 2
        wa = widths[a]
        if a + 1 < k:
            wb = widths[a + 1]
            gap_x = (cs[a] + wa / 2 + cs[a + 1] - wb / 2) / 2
        else:
            gap_x = cs[a] + wa / 2 + BOX_GAP / 2
        cs = [x - gap_x for x in cs]
        if a + 1 < k:
            need = label_w_of(holders[idx[a + 1]]) + LABEL_GAP + 0.15 - cs[a + 1]
            if need > 0:
                cs = cs[: a + 1] + [x + need for x in cs[a + 1:]]
        return cs

    row_y = 0.0
    trunk_top = bus_y = row_y
    for r, idx in enumerate(rows):
        above = max((upper_height(holders[i]) for i in idx), default=0.0)
        if r:
            row_y = bus_y + ROW_GAP + above
        cs = row_centers(idx, trunk_through=r > 0)
        bus_y = row_y + ph + conn
        for i, pcx in zip(idx, cs):
            draw_uppers(holders[i], pcx, row_y)
            c.box(pcx - base_w / 2, row_y, base_w, ph, holders[i]["_lines"], 10,
                  GREY if holders[i]["highlight"] else "white")
            c.line(pcx, row_y + ph, pcx, bus_y)
            if holders[i]["_label"]:
                c.lines_block(pcx - LABEL_GAP, (row_y + ph + bus_y) / 2, holders[i]["_label"], 9, anchor="end")
        if cs:
            c.line(min(cs[0], 0), bus_y, max(cs[-1], 0), bus_y)
        if r == 0:
            trunk_top = bus_y

    target = d["target"]
    target_text = target["name"] + (f"\n（{target['form']}）" if target["form"] else "")
    if target["capital"] is not None:
        target_text += f"\n注册资本 {format_amount(target['capital'])} {unit}".rstrip()
    t_lines, t_w, t_h = _fit_box(target_text, 11, TARGET_MAX_W)
    t_w = max(t_w, base_w)
    t_h = max(t_h, base_h)
    target_top = bus_y + BUS_TO_TARGET if rows else 0.0
    if rows:
        c.line(0, trunk_top, 0, target_top)
    c.box(-t_w / 2, target_top, t_w, t_h, t_lines, 11, GREY)
    target_bottom = target_top + t_h

    subs = d["subsidiaries"]
    k = len(subs)

    def sub_text(s):
        return s["name"] + (f"\n（{s['form']}）" if s["form"] else "")

    def sub_label(s):
        label = []
        if s["ratio"] is not None:
            label.append("持股 " + format_ratio(s["ratio"]))
        if s["note"]:
            label.append(s["note"])
        return label

    prmax = SUB_MAX_W if k <= 1 else SUB_MAX_W_MULTI
    sub_boxes = [_fit_box(sub_text(s), 10, prmax) for s in subs]
    sub_w = max([base_w] + [b[1] for b in sub_boxes]) if k else base_w
    sub_h = max([base_h] + [b[2] for b in sub_boxes]) if k else base_h
    if k == 1:
        labels = sub_label(subs[0])
        ptop = target_bottom + connector_len(labels)
        c.box(-sub_w / 2, ptop, sub_w, sub_h, sub_boxes[0][0], 10)
        c.line(0, target_bottom, 0, ptop, arrow=True)
        if labels:
            c.lines_block(LABEL_GAP + 0.04, (target_bottom + ptop) / 2, labels, 9, anchor="start")
    elif k > 1:
        labels = [sub_label(s) for s in subs]
        pbus = target_bottom + connector_len(["持股"])
        ptop = pbus + connector_len(max(labels, key=len) if labels else [])
        c.line(0, target_bottom, 0, pbus)
        pcs = [0.0]
        for i in range(1, k):
            lw = _block_size(labels[i - 1], 9)[0]
            step = max(sub_w + BOX_GAP, lw + LABEL_GAP + 0.3)
            pcs.append(pcs[-1] + step)
        shift = -((pcs[0] - sub_w / 2) + (pcs[-1] + sub_w / 2)) / 2
        pcs = [x + shift for x in pcs]
        for s, (lines, _, _), pcx, label in zip(subs, sub_boxes, pcs, labels):
            c.box(pcx - sub_w / 2, ptop, sub_w, sub_h, lines, 10)
            c.line(pcx, pbus, pcx, ptop, arrow=True)
            if label:
                c.lines_block(pcx + LABEL_GAP, (pbus + ptop) / 2, label, 9, anchor="start")
        c.line(min(pcs[0], 0), pbus, max(pcs[-1], 0), pbus)

    if c.items:
        x0, y0, x1, _ = c.bbox()
        cx = (x0 + x1) / 2
        cursor = y0 - TITLE_GAP
        if d["as_of"]:
            c.text(cx, cursor, f"截至{d['as_of']}", 10)
            cursor -= _em(10) * 1.6
        if d["title"]:
            c.text(cx, cursor, d["title"], 14, bold=True)
    return c.to_svg()

"""基金架构图 SVG 渲染器（纯标准库）。

版式复刻 matplotlib 参考稿：上排出资人方框 + 竖线汇入认缴主线，竖线左侧标认缴比例/金额；
中排基金主体（灰底），左侧管理人「受托管理」箭头、右侧托管银行「资金托管」箭头；
下排底层项目，「项目投资」箭头。宋体、黑色 1.1 线宽、GP 与基金灰底 #d9d9d9。

坐标以「英寸」为单位布局（与参考稿 figsize=(16, 8)、xlim 16 一致），输出时乘以 SCALE=72，
因此字号的 pt 值可直接作为 px 使用。
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
# 无宋体的环境（如 Linux 服务器）依次回退到思源宋体、再到任意中文字体
FONT_FAMILY = (
    "SimSun, 宋体, 'Songti SC', STSong, 'Noto Serif CJK SC', 'Source Han Serif SC', "
    "'Noto Sans CJK SC', 'Microsoft YaHei', 'WenQuanYi Micro Hei', serif"
)
GP_ROLES = {"GP", "普通合伙人", "执行事务合伙人", "普通合伙人（GP）"}

DEFAULTS = {
    "title": "中基协备案基金架构图（示例）",
    "unit": "万元",
    "manager_label": "受托管理",
    "custodian_label": "资金托管",
    "project_label": "项目投资",
    "show_ratio": True,
    "show_amount": True,
    "max_per_row": 6,  # 每排出资人上限，超出自动分排
}

# 版式常量（单位：英寸）。方框按文字自适应：尺寸 = 文字外接框 + PAD；*_MAX_W 只用于决定何时换行
MARGIN = 0.4
PAD_X, PAD_Y = 0.16, 0.12
MIN_BOX_W = 1.0
LINE_SPACING = 1.35
PARTNER_MAX_W = 2.6
ROW_GAP = 0.35         # 上一排认缴主线到下一排方框顶部
FUND_MAX_W = 4.4
SIDE_MAX_W = 3.3
PROJECT_MAX_W, PROJECT_MAX_W_MULTI = 4.4, 3.0
BOX_GAP = 0.4          # 同排相邻方框的最小间距
LABEL_GAP = 0.08       # 标注文字与连线的距离
BUS_TO_FUND = 0.6
TITLE_GAP = 0.45


# ---------------------------------------------------------------- 数据处理

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
    """500 → '500'；4500 → '4,500'；1234.5 → '1,234.5'。"""
    d = _dec(value)
    if d is None:
        return ""
    if d == d.to_integral_value():
        return f"{int(d):,}"
    text = f"{d:,.4f}".rstrip("0").rstrip(".")
    return text


def format_ratio(value) -> str:
    """至少两位小数；用户给定的比例更精确时（如 0.61069%）保留原精度。"""
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


def normalize(data: dict) -> dict:
    """补默认值、计算比例，返回渲染用的规范化结构。"""
    data = dict(data or {})
    out = {k: data.get(k, v) for k, v in DEFAULTS.items()}
    out["font_family"] = data.get("font_family") or FONT_FAMILY

    fund = data.get("fund") or {}
    if isinstance(fund, str):
        fund = {"name": fund}
    out["fund"] = {
        "name": str(fund.get("name") or "基金").strip(),
        "form": str(fund.get("form") or "").strip(),
    }

    partners = []
    for p in data.get("partners") or []:
        if isinstance(p, str):
            p = {"name": p}
        role = str(p.get("role") or "").strip()
        highlight = p.get("highlight")
        partners.append(
            {
                "name": str(p.get("name") or "").strip(),
                "role": role,
                "amount": _dec(p.get("amount")),
                "ratio": _dec(p.get("ratio")),
                "highlight": _is_gp(role) if highlight is None else bool(highlight),
            }
        )
    computed = compute_ratios([p["amount"] for p in partners])
    if all(p["amount"] is not None for p in partners):
        for p, r in zip(partners, computed):
            if p["ratio"] is None:
                p["ratio"] = r
    out["partners"] = partners

    def _side(key, title_word):
        side = data.get(key)
        if not side:
            return None
        if isinstance(side, str):
            side = {"name": side}
        if not str(side.get("name") or "").strip():
            return None
        return {
            "title": side.get("title", title_word),
            "name": str(side["name"]).strip(),
            "code": str(side.get("code") or "").strip(),
            "label": side.get("label"),
        }

    out["manager"] = _side("manager", "基金管理人")
    out["custodian"] = _side("custodian", "托管银行")
    if out["manager"] and out["manager"]["label"] is None:
        out["manager"]["label"] = out["manager_label"]
    if out["custodian"] and out["custodian"]["label"] is None:
        out["custodian"]["label"] = out["custodian_label"]

    projects = []
    for p in data.get("projects") if data.get("projects") is not None else [{"name": "底层项目"}]:
        if isinstance(p, str):
            p = {"name": p}
        if str(p.get("name") or "").strip():
            projects.append(
                {
                    "name": str(p["name"]).strip(),
                    "note": str(p.get("note") or "").strip(),
                    "label": str(p.get("label") or "").strip(),
                }
            )
    out["projects"] = projects
    return out


def check(data: dict) -> list[str]:
    """返回提示信息列表（不阻止出图）。"""
    d = normalize(data)
    msgs = []
    if not d["partners"]:
        msgs.append("未填写任何出资人。")
    for i, p in enumerate(d["partners"], 1):
        if not p["name"]:
            msgs.append(f"第 {i} 位出资人缺少名称。")
        if p["amount"] is None and p["ratio"] is None:
            msgs.append(f"「{p['name'] or i}」既无认缴金额也无比例。")
    ratios = [p["ratio"] for p in d["partners"] if p["ratio"] is not None]
    if ratios and len(ratios) == len(d["partners"]):
        total = sum(ratios)
        if abs(total - 100) > Decimal("0.01"):
            msgs.append(f"认缴比例合计为 {total:.2f}%，不等于 100%。")
    roles = [p["role"] for p in d["partners"]]
    if "合伙" in d["fund"]["form"] and not any(_is_gp(r) for r in roles):
        msgs.append("合伙型基金未标注 GP（普通合伙人）。")
    m = d["manager"]
    if m and m["code"] and not m["code"].upper().startswith("P"):
        msgs.append(f"管理人登记编码「{m['code']}」通常以 P 开头，请核对。")
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
    """均衡换行：行数取最少，各行长度尽量相等，避免末行只剩一两个字。"""
    lines = []
    for para in str(text).split("\n"):
        n = len(_greedy(para, max_em))
        limit = _text_em(para) / n
        while limit < max_em and len(_greedy(para, limit)) > n:
            limit += 0.25
        lines.extend(_greedy(para, min(limit, max_em)))
    return lines


def _em(fs: float) -> float:
    return fs / SCALE


def _block_size(lines, fs):
    """多行文字的外接框（宽, 高）。"""
    width = max((_text_em(s) for s in lines), default=0) * _em(fs)
    height = ((len(lines) - 1) * LINE_SPACING + 1) * _em(fs) if lines else 0
    return width, height


def _fit_box(text, fs, max_w):
    """按最大宽度换行，返回 (行列表, 方框宽, 方框高)。"""
    lines = _wrap(text, (max_w - 2 * PAD_X) / _em(fs))
    tw, th = _block_size(lines, fs)
    return lines, max(MIN_BOX_W, tw + 2 * PAD_X), th + 2 * PAD_Y


# ---------------------------------------------------------------- 图元

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
        """以 cy 为垂直中心排多行文字。"""
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
        """按内容外接框裁切画布，四周留 margin。"""
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
                out.append(
                    f'<rect x="{nx(x)}" y="{ny(y)}" width="{n(w)}" height="{n(h)}" fill="{fill}"/>'
                )
            elif kind == "line":
                _, lx1, ly1, lx2, ly2, arrow = item
                marker = ' marker-end="url(#arrow)"' if arrow else ""
                out.append(
                    f'<line x1="{nx(lx1)}" y1="{ny(ly1)}" x2="{nx(lx2)}" y2="{ny(ly2)}"{marker}/>'
                )
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
        out.append("</g>")
        out.append("</svg>")
        return "\n".join(out) + "\n"


# ---------------------------------------------------------------- 布局

def render_svg(data: dict) -> str:
    d = normalize(data)
    c = _Canvas(d["font_family"])
    partners, projects = d["partners"], d["projects"]
    manager, custodian = d["manager"], d["custodian"]
    unit = d["unit"]

    em9 = _em(9)

    def connector_len(labels):
        """竖向连线长度：放得下旁边的标注文字即可。"""
        _, h = _block_size(labels, 9)
        return max(0.45, h + 0.3)

    # 出资人：每个方框宽度按文字自适应，统一高度
    p_boxes, p_labels = [], []
    for p in partners:
        text = p["name"] + (f"\n（{p['role']}）" if p["role"] else "")
        p_boxes.append(_fit_box(text, 10, PARTNER_MAX_W))
        label = []
        if d["show_ratio"] and p["ratio"] is not None:
            label.append(format_ratio(p["ratio"]))
        if d["show_amount"] and p["amount"] is not None:
            label.append(f"{format_amount(p['amount'])} {unit}".strip())
        p_labels.append(label)
    ph = max((b[2] for b in p_boxes), default=0)

    def label_w(i):
        return _block_size(p_labels[i], 9)[0]

    # 超过 max_per_row 时均分为多排，每排各有一条认缴主线，由 x=0 处的竖线串起接入基金
    n = len(partners)
    per_row = max(1, int(d["max_per_row"]))
    n_rows = -(-n // per_row) if n else 0
    rows, start = [], 0
    for r in range(n_rows):
        cnt = n // n_rows + (1 if r < n % n_rows else 0)
        rows.append(list(range(start, start + cnt)))
        start += cnt

    def row_centers(idx, trunk_through):
        # 相邻竖线间距要同时容下两侧方框和竖线左侧的比例/金额标注
        cs = [0.0]
        for j in range(1, len(idx)):
            a, b = idx[j - 1], idx[j]
            step = max(p_boxes[a][1] / 2 + BOX_GAP + p_boxes[b][1] / 2, label_w(b) + LABEL_GAP + 0.2)
            cs.append(cs[-1] + step)
        if not trunk_through:
            left = cs[0] - p_boxes[idx[0]][1] / 2
            right = cs[-1] + p_boxes[idx[-1]][1] / 2
            return [x - (left + right) / 2 for x in cs]
        # 竖线要穿过本排：把中间的空隙对准 x=0，且右侧方框的标注不能压到竖线
        k = len(idx)
        a = k // 2 - 1 if k % 2 == 0 else k // 2
        wa = p_boxes[idx[a]][1]
        if a + 1 < k:
            wb = p_boxes[idx[a + 1]][1]
            gap_x = (cs[a] + wa / 2 + cs[a + 1] - wb / 2) / 2
        else:
            gap_x = cs[a] + wa / 2 + BOX_GAP / 2
        cs = [x - gap_x for x in cs]
        if a + 1 < k:
            need = label_w(idx[a + 1]) + LABEL_GAP + 0.15 - cs[a + 1]
            if need > 0:
                cs = cs[: a + 1] + [x + need for x in cs[a + 1:]]
        return cs

    row_y = 0.0
    trunk_top = bus_y = row_y
    conn = connector_len(["0", "0"])
    for r, idx in enumerate(rows):
        cs = row_centers(idx, trunk_through=r > 0)
        bus_y = row_y + ph + conn
        for i, pcx in zip(idx, cs):
            lines, w, _ = p_boxes[i]
            c.box(pcx - w / 2, row_y, w, ph, lines, 10, GREY if partners[i]["highlight"] else "white")
            c.line(pcx, row_y + ph, pcx, bus_y)
            if p_labels[i]:
                c.lines_block(pcx - LABEL_GAP, (row_y + ph + bus_y) / 2, p_labels[i], 9, anchor="end")
        c.line(min(cs[0], 0), bus_y, max(cs[-1], 0), bus_y)
        if r == 0:
            trunk_top = bus_y
        row_y = bus_y + ROW_GAP

    # 基金主体 + 管理人 / 托管人
    fund_text = d["fund"]["name"] + (f"\n{d['fund']['form']}" if d["fund"]["form"] else "")
    fund_lines, fund_w, fund_h = _fit_box(fund_text, 11, FUND_MAX_W)

    def side_box(side):
        text = f"{side['title']}\n{side['name']}" if side["title"] else side["name"]
        if side["code"]:
            text += f"\n登记编码：{side['code']}"
        return _fit_box(text, 10, SIDE_MAX_W)

    def side_gap(label):
        return max(0.9, _text_em(label or "") * em9 + 0.5)

    m_box = side_box(manager) if manager else None
    c_box = side_box(custodian) if custodian else None
    mid_h = max([fund_h] + [b[2] for b in (m_box, c_box) if b])
    fund_top = (bus_y + BUS_TO_FUND if rows else 0.0) + (mid_h - fund_h) / 2
    fcy = fund_top + fund_h / 2
    fund_x = -fund_w / 2
    if rows:
        c.line(0, trunk_top, 0, fund_top)
    c.box(fund_x, fund_top, fund_w, fund_h, fund_lines, 11, GREY)

    if manager:
        lines, w, h = m_box
        gap = side_gap(manager["label"])
        mx = fund_x - gap - w
        c.box(mx, fcy - h / 2, w, h, lines, 10)
        c.line(mx + w, fcy, fund_x, fcy, arrow=True)
        if manager["label"]:
            c.text(fund_x - gap / 2, fcy - 0.1, manager["label"], 9)
    if custodian:
        lines, w, h = c_box
        gap = side_gap(custodian["label"])
        rx = fund_x + fund_w + gap
        c.box(rx, fcy - h / 2, w, h, lines, 10)
        c.line(rx, fcy, fund_x + fund_w, fcy, arrow=True)
        if custodian["label"]:
            c.text(fund_x + fund_w + gap / 2, fcy - 0.1, custodian["label"], 9)

    fund_bottom = fund_top + fund_h
    mid_bottom = fcy + mid_h / 2

    # 底层项目
    k = len(projects)
    prmax = PROJECT_MAX_W if k <= 1 else PROJECT_MAX_W_MULTI
    pr_boxes = [_fit_box(p["name"] + (f"\n{p['note']}" if p["note"] else ""), 10, prmax) for p in projects]
    pr_h = max((b[2] for b in pr_boxes), default=0)
    if k == 1:
        p = projects[0]
        lines, w, _ = pr_boxes[0]
        labels = [s for s in (d["project_label"], p["label"]) if s]
        ptop = max(fund_bottom + connector_len(labels), mid_bottom + 0.3)
        c.box(-w / 2, ptop, w, pr_h, lines, 10)
        c.line(0, fund_bottom, 0, ptop, arrow=True)
        if labels:
            c.lines_block(LABEL_GAP + 0.04, (fund_bottom + ptop) / 2, labels, 9, anchor="start")
    elif k > 1:
        trunk = [d["project_label"]] if d["project_label"] else []
        pbus = max(fund_bottom + connector_len(trunk), mid_bottom + 0.3)
        ptop = pbus + connector_len([p["label"] for p in projects if p["label"]][:1])
        c.line(0, fund_bottom, 0, pbus)
        if trunk:
            c.lines_block(LABEL_GAP + 0.04, (fund_bottom + pbus) / 2, trunk, 9, anchor="start")
        pcs = []
        for i, (_, w, _) in enumerate(pr_boxes):
            if not pcs:
                pcs.append(0.0)
                continue
            prev_w = pr_boxes[i - 1][1]
            label_w = _text_em(projects[i - 1]["label"]) * em9
            step = max(prev_w / 2 + BOX_GAP + w / 2, label_w + LABEL_GAP + 0.3)
            pcs.append(pcs[-1] + step)
        shift = -((pcs[0] - pr_boxes[0][1] / 2) + (pcs[-1] + pr_boxes[-1][1] / 2)) / 2
        pcs = [x + shift for x in pcs]
        for p, (lines, w, _), pcx in zip(projects, pr_boxes, pcs):
            c.box(pcx - w / 2, ptop, w, pr_h, lines, 10)
            c.line(pcx, pbus, pcx, ptop, arrow=True)
            if p["label"]:
                c.lines_block(pcx + LABEL_GAP, (pbus + ptop) / 2, [p["label"]], 9, anchor="start")
        c.line(min(pcs[0], 0), pbus, max(pcs[-1], 0), pbus)

    # 标题居中于整幅内容之上
    if d["title"]:
        x0, y0, x1, _ = c.bbox()
        c.text((x0 + x1) / 2, y0 - TITLE_GAP, d["title"], 14, bold=True)

    return c.to_svg()

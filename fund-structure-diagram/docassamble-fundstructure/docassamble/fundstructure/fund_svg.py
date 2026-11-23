"""基金架构图 SVG 渲染器（纯标准库，可在 docassamble 内外共用）。

版式复刻 matplotlib 参考稿：上排出资人方框 + 竖线汇入认缴主线，竖线左侧标认缴比例/金额；
中排基金主体（灰底），左侧管理人「受托管理」箭头、右侧托管银行「资金托管」箭头；
下排底层项目，「项目投资」箭头。宋体、黑色 1.1 线宽、GP 与基金灰底 #d9d9d9。

坐标以「英寸」为单位布局（与参考稿 figsize=(16, 8)、xlim 16 一致），输出时乘以 SCALE=72，
因此字号的 pt 值可直接作为 px 使用。
"""
from __future__ import annotations

import json
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
    "interview_to_data",
    "to_json",
    "DEFAULTS",
]

SCALE = 72
GREY = "#d9d9d9"
LINE_W = 1.1
# 无宋体的环境（Linux 服务器、docassamble 容器）依次回退到思源宋体、再到任意中文字体
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
}

# 版式常量（单位：英寸），取自参考稿
MARGIN = 0.5
PARTNER_W, PARTNER_H, PARTNER_GAP = 2.6, 1.35, 0.5
PARTNER_W_DENSE, PARTNER_GAP_DENSE = 2.2, 0.4
BOX_TO_BUS = 1.05
BUS_TO_FUND = 1.1
FUND_W, FUND_H = 4.4, 1.2
SIDE_W, MANAGER_H, CUSTODIAN_H = 3.3, 1.35, 1.1
SIDE_GAP = 1.6
FUND_TO_PROJECT = 1.65
PROJECT_W, PROJECT_H = 4.4, 1.15
PROJECT_W_MULTI, PROJECT_GAP = 3.0, 0.5
PAD_X, PAD_Y = 0.12, 0.18
LINE_SPACING = 1.35


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
    d = _dec(value)
    if d is None:
        return ""
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


def interview_to_data(**kw) -> dict:
    """把 docassamble 问答变量组装成渲染用 dict（列表元素为 DAObject）。"""
    partners = []
    for p in kw.get("partners") or []:
        partners.append(
            {
                "name": p.name,
                "role": getattr(p, "role", ""),
                "amount": getattr(p, "amount", None),
            }
        )
    projects = []
    for p in kw.get("projects") or []:
        projects.append(
            {
                "name": p.name,
                "note": getattr(p, "note", "") or "",
                "label": getattr(p, "label", "") or "",
            }
        )
    data = {
        "title": kw.get("title", DEFAULTS["title"]),
        "unit": kw.get("unit", DEFAULTS["unit"]),
        "fund": {"name": kw.get("fund_name", ""), "form": kw.get("fund_form_text", "")},
        "partners": partners,
        "projects": projects,
        "project_label": kw.get("project_label", DEFAULTS["project_label"]),
        "show_ratio": kw.get("show_ratio", True),
        "show_amount": kw.get("show_amount", True),
    }
    if kw.get("has_manager"):
        data["manager"] = {
            "name": kw.get("manager_name", ""),
            "code": kw.get("manager_code", "") or "",
            "label": kw.get("manager_label") or DEFAULTS["manager_label"],
        }
    if kw.get("has_custodian"):
        data["custodian"] = {
            "name": kw.get("custodian_name", ""),
            "label": kw.get("custodian_label") or DEFAULTS["custodian_label"],
        }
    return data


def to_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


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


def _wrap(text: str, max_em: float) -> list[str]:
    lines = []
    for para in str(text).split("\n"):
        cur, width = "", 0.0
        for ch in para:
            w = _char_em(ch)
            if cur and width + w > max_em and ch not in NO_LINE_START:
                lines.append(cur)
                cur, width = "", 0.0
            cur += ch
            width += w
        lines.append(cur)
    return lines


def _em(fs: float) -> float:
    return fs / SCALE


def _box_height(lines, fs, min_h):
    return max(min_h, len(lines) * _em(fs) * LINE_SPACING + 2 * PAD_Y)


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

    def to_svg(self, width, height) -> str:
        s = SCALE

        def n(v):
            return f"{v * s:.2f}".rstrip("0").rstrip(".")

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
                    f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" fill="{fill}"/>'
                )
            elif kind == "line":
                _, x1, y1, x2, y2, arrow = item
                marker = ' marker-end="url(#arrow)"' if arrow else ""
                out.append(
                    f'<line x1="{n(x1)}" y1="{n(y1)}" x2="{n(x2)}" y2="{n(y2)}"{marker}/>'
                )
            else:
                _, x, y, txt, fs, anchor, bold = item
                weight = ' font-weight="bold"' if bold else ""
                texts.append(
                    f'<text x="{n(x)}" y="{n(y)}" font-size="{fs}" text-anchor="{anchor}"{weight}>'
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

    n = len(partners)
    dense = n > 6
    pw = PARTNER_W_DENSE if dense else PARTNER_W
    pgap = PARTNER_GAP_DENSE if dense else PARTNER_GAP

    # 文字换行与方框高度
    p_lines = []
    for p in partners:
        label = p["name"] + (f"\n（{p['role']}）" if p["role"] else "")
        p_lines.append(_wrap(label, (pw - 2 * PAD_X) / _em(10)))
    ph = max([_box_height(ls, 10, PARTNER_H) for ls in p_lines] or [PARTNER_H])

    fund_text = d["fund"]["name"] + (f"\n{d['fund']['form']}" if d["fund"]["form"] else "")
    fund_lines = _wrap(fund_text, (FUND_W - 2 * PAD_X) / _em(11))
    fund_h = _box_height(fund_lines, 11, FUND_H)

    def side_lines(side):
        text = f"{side['title']}\n{side['name']}" if side["title"] else side["name"]
        if side["code"]:
            text += f"\n登记编码：{side['code']}"
        return _wrap(text, (SIDE_W - 2 * PAD_X) / _em(10))

    m_lines = side_lines(manager) if manager else None
    c_lines = side_lines(custodian) if custodian else None
    m_h = _box_height(m_lines, 10, MANAGER_H) if manager else 0
    c_h = _box_height(c_lines, 10, CUSTODIAN_H) if custodian else 0

    k = len(projects)
    prw = PROJECT_W if k <= 1 else PROJECT_W_MULTI
    pr_lines = []
    for p in projects:
        text = p["name"] + (f"\n{p['note']}" if p["note"] else "")
        pr_lines.append(_wrap(text, (prw - 2 * PAD_X) / _em(10)))
    pr_h = max([_box_height(ls, 10, PROJECT_H) for ls in pr_lines] or [PROJECT_H])

    # 画布宽度
    partners_row = n * pw + max(n - 1, 0) * pgap
    side_need = max(
        (SIDE_GAP + SIDE_W) if manager else 0,
        (SIDE_GAP + SIDE_W) if custodian else 0,
    )
    mid_row = FUND_W + 2 * side_need
    projects_row = k * prw + max(k - 1, 0) * PROJECT_GAP
    width = max(16.0, partners_row + 2 * MARGIN, mid_row + 2 * MARGIN, projects_row + 2 * MARGIN)
    cx = width / 2

    # 标题
    y = 0.35
    if d["title"]:
        c.text(cx, y + _em(14), d["title"], 14, bold=True)
        y += _em(14) + 0.5
    top_y = y

    # 出资人
    bus_y = top_y + ph + BOX_TO_BUS
    start_x = cx - partners_row / 2
    centers = []
    for i, (p, lines) in enumerate(zip(partners, p_lines)):
        x = start_x + i * (pw + pgap)
        pcx, _ = c.box(x, top_y, pw, ph, lines, 10, GREY if p["highlight"] else "white")
        centers.append(pcx)
        c.line(pcx, top_y + ph, pcx, bus_y)
        label = []
        if d["show_ratio"] and p["ratio"] is not None:
            label.append(format_ratio(p["ratio"]))
        if d["show_amount"] and p["amount"] is not None:
            label.append(f"{format_amount(p['amount'])} {unit}".strip())
        if label:
            lh = _em(9) * LINE_SPACING
            last = bus_y - 0.27
            for j, s in enumerate(label):
                c.text(pcx - 0.1, last - (len(label) - 1 - j) * lh, s, 9, anchor="end")
    if centers:
        c.line(min(centers[0], cx), bus_y, max(centers[-1], cx), bus_y)

    # 基金主体 + 管理人 / 托管人
    mid_h = max(fund_h, m_h, c_h)
    fund_x = cx - FUND_W / 2
    fund_top = bus_y + BUS_TO_FUND + (mid_h - fund_h) / 2
    fcy = fund_top + fund_h / 2
    if centers:
        c.line(cx, bus_y, cx, fund_top)
    c.box(fund_x, fund_top, FUND_W, fund_h, fund_lines, 11, GREY)

    if manager:
        mx = fund_x - SIDE_GAP - SIDE_W
        c.box(mx, fcy - m_h / 2, SIDE_W, m_h, m_lines, 10)
        c.line(mx + SIDE_W, fcy, fund_x, fcy, arrow=True)
        if manager["label"]:
            c.text(fund_x - SIDE_GAP / 2, fcy - 0.12, manager["label"], 9)
    if custodian:
        rx = fund_x + FUND_W + SIDE_GAP
        c.box(rx, fcy - c_h / 2, SIDE_W, c_h, c_lines, 10)
        c.line(rx, fcy, fund_x + FUND_W, fcy, arrow=True)
        if custodian["label"]:
            c.text(fund_x + FUND_W + SIDE_GAP / 2, fcy - 0.12, custodian["label"], 9)

    bottom = fcy + mid_h / 2
    fund_bottom = fund_top + fund_h

    # 底层项目
    if k == 1:
        p = projects[0]
        ptop = bottom + FUND_TO_PROJECT
        c.box(cx - prw / 2, ptop, prw, pr_h, pr_lines[0], 10)
        c.line(cx, fund_bottom, cx, ptop, arrow=True)
        labels = [s for s in (d["project_label"], p["label"]) if s]
        if labels:
            c.lines_block(cx + 0.2, (fund_bottom + ptop) / 2, labels, 9, anchor="start")
        bottom = ptop + pr_h
    elif k > 1:
        pbus = bottom + 0.75
        ptop = pbus + 0.9
        c.line(cx, fund_bottom, cx, pbus)
        if d["project_label"]:
            c.lines_block(cx + 0.2, (fund_bottom + pbus) / 2, [d["project_label"]], 9, anchor="start")
        start = cx - projects_row / 2
        pcs = []
        for i, (p, lines) in enumerate(zip(projects, pr_lines)):
            x = start + i * (prw + PROJECT_GAP)
            pcx, _ = c.box(x, ptop, prw, pr_h, lines, 10)
            pcs.append(pcx)
            c.line(pcx, pbus, pcx, ptop, arrow=True)
            if p["label"]:
                c.lines_block(pcx + 0.12, (pbus + ptop) / 2, [p["label"]], 9, anchor="start")
        c.line(min(pcs[0], cx), pbus, max(pcs[-1], cx), pbus)
        bottom = ptop + pr_h

    height = bottom + 0.45
    return c.to_svg(width, height)

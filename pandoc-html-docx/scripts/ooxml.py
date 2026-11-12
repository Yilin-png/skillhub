#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal, dependency-free OOXML helpers (stdlib ElementTree).

为什么不用正则：pandoc 3.x 会输出自闭合的 ``<w:tcPr/>`` / ``<w:pPr/>``，
正则式「找 <w:tcPr>…</w:tcPr>，找不到就新插一个」会产生重复的 tcPr/pPr，
Word 可能报「无法读取的内容」。这里用真正的 XML 树来改，并按 ECMA-376
规定的子元素顺序插入属性，保证产物符合 schema。

ElementTree 序列化时会丢掉「未使用」的命名空间声明，而 ``mc:Ignorable``
引用的前缀必须声明，所以保存时会把原始根标签上的声明全部补回去。
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def wattr(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------- schema order
# ECMA-376 Part 1 (transitional) sequence order of property children.
PPR_ORDER = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
    "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
    "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
    "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
    "suppressOverlap", "jc", "textDirection", "textAlignment",
    "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr",
    "pPrChange",
]
TCPR_ORDER = [
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
    "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
    "headers", "cellIns", "cellDel", "cellMerge", "tcPrChange",
]
TBLPR_ORDER = [
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
    "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
    "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption",
    "tblDescription", "tblPrChange",
]
SECTPR_ORDER = [
    "headerReference", "footerReference", "footnotePr", "endnotePr", "type",
    "pgSz", "pgMar", "paperSrc", "pgBorders", "lnNumType", "pgNumType",
    "cols", "formProt", "vAlign", "noEndnote", "titlePg", "textDirection",
    "bidi", "rtlGutter", "docGrid", "printerSettings", "sectPrChange",
]
TCMAR_ORDER = ["top", "start", "left", "bottom", "end", "right"]

ORDERS = {
    "pPr": PPR_ORDER,
    "tcPr": TCPR_ORDER,
    "tblPr": TBLPR_ORDER,
    "sectPr": SECTPR_ORDER,
    "tcMar": TCMAR_ORDER,
}


def sort_children(el: ET.Element) -> None:
    """Stable-sort children of a property element into schema order.

    Elements from other namespaces / unknown names keep their relative order
    and go last (they are extension elements in practice)."""
    order = ORDERS.get(local(el.tag))
    if not order or len(el) < 2:
        return
    idx = {name: i for i, name in enumerate(order)}
    big = len(order)

    def key(child: ET.Element) -> int:
        if not child.tag.startswith(f"{{{W_NS}}}"):
            return big
        return idx.get(local(child.tag), big)

    children = list(el)
    children.sort(key=key)  # list.sort is stable
    for c in list(el):
        el.remove(c)
    el.extend(children)


REPEATABLE = {"headerReference", "footerReference"}


def dedupe_children(el: ET.Element) -> int:
    """Drop duplicate single-occurrence children (keep the last one).

    pandoc 3.1.x 会给嵌套表格单元格的段落写两个 <w:jc>，违反 schema。"""
    seen: dict[str, ET.Element] = {}
    removed = 0
    for c in list(el):
        if not c.tag.startswith(f"{{{W_NS}}}") or local(c.tag) in REPEATABLE:
            continue
        if c.tag in seen:
            el.remove(seen[c.tag])
            removed += 1
        seen[c.tag] = c
    return removed


def normalize_order(root: ET.Element) -> int:
    """De-duplicate and sort every pPr/tcPr/tblPr/sectPr/tcMar. Returns #fixed dups."""
    n = 0
    for el in root.iter():
        if el.tag.startswith(f"{{{W_NS}}}") and local(el.tag) in ORDERS:
            n += dedupe_children(el)
            sort_children(el)
    return n


def ensure_pr(parent: ET.Element, pr_name: str) -> ET.Element:
    """Return the (single) property child (pPr/tcPr/tblPr/rPr), creating it as
    the first child if missing. Extra duplicates are merged into the first."""
    found = parent.findall(w(pr_name))
    if found:
        first = found[0]
        for dup in found[1:]:
            for c in list(dup):
                if first.find(c.tag) is None:
                    first.append(c)
            parent.remove(dup)
        return first
    pr = ET.Element(w(pr_name))
    parent.insert(0, pr)
    return pr


def set_prop(pr: ET.Element, name: str, attrs: dict[str, str] | None = None,
             children: list[ET.Element] | None = None) -> ET.Element:
    """Replace/insert child ``w:<name>`` of property element ``pr`` in schema order."""
    for old in pr.findall(w(name)):
        pr.remove(old)
    el = ET.Element(w(name), {wattr(k): v for k, v in (attrs or {}).items()})
    for c in children or []:
        el.append(c)
    pr.append(el)
    sort_children(pr)
    return el


def get_val(el: ET.Element | None, attr: str = "val") -> str | None:
    if el is None:
        return None
    return el.get(wattr(attr))


def is_on(el: ET.Element | None) -> bool:
    """OOXML on/off property: present and not val=0/false/off."""
    if el is None:
        return False
    v = get_val(el)
    return v is None or v.lower() not in ("0", "false", "off")


def text_of(el: ET.Element) -> str:
    return "".join(t.text or "" for t in el.iter(w("t")))


# ---------------------------------------------------------------- part I/O
_ROOT_TAG_RE = re.compile(r"<(?![?!])[^>]+>")
_XMLNS_RE = re.compile(r'\sxmlns(?::([\w.-]+))?\s*=\s*("[^"]*"|\'[^\']*\')')


def _register_namespaces(data: bytes) -> None:
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
        if not prefix:
            continue
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass  # reserved prefixes such as ns0


class XmlPart:
    """Parsed XML part that round-trips namespace declarations."""

    def __init__(self, data: bytes):
        _register_namespaces(data)
        self.root = ET.fromstring(data)
        text = data.decode("utf-8", errors="replace")
        m = _ROOT_TAG_RE.search(text)
        self._orig_root_tag = m.group(0) if m else None

    def tobytes(self) -> bytes:
        out = ET.tostring(self.root, encoding="unicode")
        m = _ROOT_TAG_RE.search(out)
        if m and self._orig_root_tag:
            new_tag = m.group(0)
            orig = self._orig_root_tag
            declared = {p or "" for p, _ in _XMLNS_RE.findall(orig)}
            extra = [
                f' xmlns{":" + p if p else ""}={v}'
                for p, v in _XMLNS_RE.findall(new_tag)
                if (p or "") not in declared
            ]
            if extra:
                close = "/>" if orig.endswith("/>") else ">"
                orig = orig[: -len(close)] + "".join(extra) + close
            out = out[: m.start()] + orig + out[m.end():]
        return (XML_DECL + out).encode("utf-8")


class Docx:
    """Read all parts of a .docx into memory; write back atomically."""

    def __init__(self, path: Path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as z:
            self.infos = z.infolist()
            self.parts = {i.filename: z.read(i.filename) for i in self.infos}

    def xml(self, name: str) -> XmlPart | None:
        data = self.parts.get(name)
        return XmlPart(data) if data is not None else None

    def save(self, path: Path | None = None) -> None:
        dst = Path(path or self.path)
        tmp = dst.with_name(dst.name + ".tmp")
        names = [i.filename for i in self.infos]
        # [Content_Types].xml first, as Word / OPC readers expect
        names.sort(key=lambda n: n != "[Content_Types].xml")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for n in names:
                z.writestr(n, self.parts[n])
        tmp.replace(dst)


def style_ids_by_name(styles: XmlPart | None) -> dict[str, str]:
    """Map lower-cased w:name → w:styleId (pandoc matches by name, writes ids)."""
    out: dict[str, str] = {}
    if styles is None:
        return out
    for st in styles.root.iter(w("style")):
        sid = st.get(wattr("styleId"))
        name = get_val(st.find(w("name")))
        if sid and name:
            out.setdefault(name.strip().lower(), sid)
    return out


def check_zip_names(path: Path) -> list[str]:
    """Return problems with zip entry names (e.g. Windows backslashes)."""
    problems = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    if any("\\" in n for n in names):
        problems.append("zip 内路径使用了反斜杠 \\（Windows 打包工具常见），"
                        "pandoc 在 macOS/Linux 上会读不到模板而静默回退默认样式")
    if "word/document.xml" not in names and not any(
        n.replace("\\", "/") == "word/document.xml" for n in names
    ):
        problems.append("缺少 word/document.xml")
    if not any(n.replace("\\", "/") == "word/styles.xml" for n in names):
        problems.append("缺少 word/styles.xml")
    return problems


def repack_forward_slashes(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(src) as zin:
        names = [i.filename for i in zin.infolist()]
        names.sort(key=lambda n: n != "[Content_Types].xml")
        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for n in names:
                if n.endswith("/") or n.endswith("\\"):
                    continue
                z.writestr(n.replace("\\", "/"), zin.read(n))

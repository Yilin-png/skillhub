#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建前检查 source.md：HTML 表格结构、写法陷阱、禁用套话。

ERROR 会阻止构建（可用 build.py --force 跳过），WARN 只提示。

检查项：
- 每张 <table> 按 rowspan/colspan 展开后，各行占位数必须等于表宽；
  rowspan 不得越出所在 thead/tbody；colspan/rowspan 必须是正整数。
- <table> 前一行不是空行 / 顶层缩进 ≥ 1 空格 → WARN（构建会兜底恢复，但应修正）。
- ```html 围栏里的表格 → WARN（会成为代码块而不是表格）。
- 「结构化对照如下」等表前套话 → WARN。
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

BANNED_PHRASES = ("结构化对照如下", "要点汇总如下", "如下表所示")


@dataclass
class Issue:
    level: str  # "ERROR" | "WARN"
    line: int
    msg: str

    def __str__(self) -> str:
        return f"{self.level} 第 {self.line} 行：{self.msg}"


@dataclass
class TableInfo:
    line: int
    rows: int = 0
    cols: int = 0
    colspans: int = 0
    rowspans: int = 0
    issues: list[Issue] = field(default_factory=list)


def _span(attrs: dict[str, str | None], name: str, line: int, issues: list[Issue]) -> int:
    raw = attrs.get(name)
    if raw is None:
        return 1
    raw = raw.strip()
    if not raw.isdigit() or int(raw) < 1:
        issues.append(Issue("ERROR", line, f"{name}=\"{raw}\" 不是正整数"))
        return 1
    return int(raw)


class _TableParser(HTMLParser):
    """Collects the top-level table's rows: list of sections → rows → cells."""

    def __init__(self, base_line: int):
        super().__init__(convert_charrefs=True)
        self.base_line = base_line
        self.depth = 0
        self.sections: list[list[list[tuple[int, int, int]]]] = []
        self.cur_section: list[list[tuple[int, int, int]]] | None = None
        self.cur_row: list[tuple[int, int, int]] | None = None
        self.issues: list[Issue] = []

    def _line(self) -> int:
        return self.base_line + self.getpos()[0] - 1

    def _ensure_section(self) -> None:
        if self.cur_section is None:
            self.cur_section = []
            self.sections.append(self.cur_section)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = {k.lower(): v for k, v in attrs}
        if tag == "table":
            self.depth += 1
            return
        if self.depth != 1:
            return
        if tag in ("thead", "tbody", "tfoot"):
            self.cur_section = []
            self.sections.append(self.cur_section)
        elif tag == "tr":
            self._ensure_section()
            self.cur_row = []
            self.cur_section.append(self.cur_row)
        elif tag in ("td", "th"):
            if self.cur_row is None:  # tolerate missing <tr>
                self._ensure_section()
                self.cur_row = []
                self.cur_section.append(self.cur_row)
            line = self._line()
            cs = _span(a, "colspan", line, self.issues)
            rs = _span(a, "rowspan", line, self.issues)
            self.cur_row.append((cs, rs, line))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "table":
            self.depth -= 1
        elif self.depth == 1 and tag in ("thead", "tbody", "tfoot"):
            self.cur_section = None
            self.cur_row = None
        elif self.depth == 1 and tag == "tr":
            self.cur_row = None


def analyze_table(html: str, line: int) -> TableInfo:
    info = TableInfo(line=line)
    p = _TableParser(line)
    p.feed(html)
    p.close()
    info.issues.extend(p.issues)

    widths: list[tuple[int, int]] = []  # (row_width, line)
    for section in p.sections:
        occupied: dict[int, set[int]] = {}
        for r, row in enumerate(section):
            taken = occupied.setdefault(r, set())
            col = 0
            row_line = row[0][2] if row else line
            for cs, rs, cl in row:
                while col in taken:
                    col += 1
                if cs > 1:
                    info.colspans += 1
                if rs > 1:
                    info.rowspans += 1
                    if r + rs > len(section):
                        info.issues.append(Issue(
                            "ERROR", cl,
                            f"rowspan={rs} 越出所在 thead/tbody（该区只剩 {len(section) - r} 行）"))
                for dr in range(rs):
                    for dc in range(cs):
                        occupied.setdefault(r + dr, set()).add(col + dc)
                col += cs
            widths.append((len(occupied.get(r, set())), row_line))
        info.rows += len(section)

    if widths:
        from collections import Counter
        info.cols = max(w for w, _ in widths)
        common = Counter(w for w, _ in widths).most_common(1)[0][0]
        for wd, ln in widths:
            if wd != info.cols:
                info.issues.append(Issue(
                    "ERROR", ln,
                    f"该行展开后占 {wd} 列，但表宽为 {info.cols} 列（最常见 {common} 列）；"
                    "请检查 colspan/rowspan，勿用空单元格凑数"))
    else:
        info.issues.append(Issue("WARN", line, "<table> 内没有找到任何行/单元格"))
    return info


_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
_TABLE_OPEN_RE = re.compile(r"<table\b", re.I)
_TABLE_TAG_RE = re.compile(r"<(/?)table\b[^>]*>", re.I)


def _blank_out(text: str, start: int, end: int) -> str:
    seg = re.sub(r"[^\n]", " ", text[start:end])
    return text[:start] + seg + text[end:]


def lint_text(text: str) -> tuple[list[Issue], list[TableInfo]]:
    issues: list[Issue] = []
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    # 1) find fenced code blocks; blank them out (keep line numbers)
    masked_lines = list(lines)
    in_fence, fence_char, fence_len, fence_info, fence_start = False, "", 0, "", 0
    for idx, ln in enumerate(lines):
        m = _FENCE_RE.match(ln)
        if not in_fence and m:
            in_fence, fence_char, fence_len = True, m.group(2)[0], len(m.group(2))
            fence_info, fence_start = m.group(3).strip(), idx
            masked_lines[idx] = ""
            continue
        if in_fence:
            closing = m and m.group(2)[0] == fence_char and len(m.group(2)) >= fence_len \
                and not m.group(3).strip()
            if closing:
                in_fence = False
                masked_lines[idx] = ""
                continue
            if "<table" in ln.lower() and fence_info.lstrip("{").lower().startswith("html") \
                    and not fence_info.startswith("{="):
                issues.append(Issue("WARN", idx + 1,
                                    "```html 围栏中的表格会被当作代码块，不会成为 Word 表格；"
                                    "请直接写 HTML 或用 ```{=html}"))
            if fence_info.replace(" ", "").startswith("{=html"):
                continue  # raw html fence: keep for table analysis
            masked_lines[idx] = ""
    masked = "\n".join(masked_lines)

    # 2) blank out HTML comments
    for m in re.finditer(r"<!--[\s\S]*?-->", masked):
        masked = _blank_out(masked, m.start(), m.end())

    # 3) top-level tables (nesting aware)
    tables: list[TableInfo] = []
    depth, start = 0, None
    for m in _TABLE_TAG_RE.finditer(masked):
        if m.group(1) == "":
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0 and start is not None:
                line_no = masked.count("\n", 0, start) + 1
                info = analyze_table(masked[start:m.end()], line_no)
                tables.append(info)
                issues.extend(info.issues)
                # blank-line / indentation check
                line_start = masked.rfind("\n", 0, start) + 1
                prefix = masked[line_start:start]
                prev = lines[line_no - 2] if line_no >= 2 else ""
                if prefix.strip():
                    issues.append(Issue("WARN", line_no,
                                        "<table> 与文字写在同一行；请让 <table> 独占一行并在前面空一行"))
                elif prev.strip():
                    issues.append(Issue("WARN", line_no,
                                        "<table> 前一行不是空行；pandoc 会把它当成段落内联 HTML"
                                        "（构建会自动恢复，但请补空行）"))
                start = None
            if depth < 0:
                issues.append(Issue("ERROR", masked.count("\n", 0, m.start()) + 1,
                                    "多余的 </table>"))
                depth = 0
    if depth > 0 and start is not None:
        issues.append(Issue("ERROR", masked.count("\n", 0, start) + 1, "<table> 未闭合"))

    # 4) banned phrases
    for idx, ln in enumerate(masked.split("\n")):
        for ph in BANNED_PHRASES:
            if ph in ln:
                issues.append(Issue("WARN", idx + 1, f"出现表前套话「{ph}」，按规范应删除"))

    issues.sort(key=lambda x: (x.line, x.level))
    return issues, tables


def lint_file(path: Path) -> tuple[list[Issue], list[TableInfo]]:
    return lint_text(Path(path).read_text(encoding="utf-8-sig"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="检查 Markdown 中的 HTML 表格与写法")
    ap.add_argument("source", type=Path)
    a = ap.parse_args(argv)
    issues, tables = lint_file(a.source)
    for t in tables:
        print(f"表（第 {t.line} 行）：{t.rows} 行 × {t.cols} 列，"
              f"colspan {t.colspans} 处，rowspan {t.rowspans} 处")
    for i in issues:
        print(i)
    errors = sum(1 for i in issues if i.level == "ERROR")
    print(f"共 {len(tables)} 张 HTML 表；{errors} 个错误，{len(issues) - errors} 个警告")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

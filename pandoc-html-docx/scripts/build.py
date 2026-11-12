#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown（含 HTML 合并表）→ DOCX，一键构建。

流程：
  0. 预检：pandoc 版本；reference.docx 完整性（反斜杠路径自动修复）；lint 源文件
  1. pandoc 单次转换 MD→DOCX：filters/html_tables.lua 把 <table> 交给 pandoc 的
     HTML reader 解析成原生表格（保留 colspan/rowspan）；脚注、公式、custom-style、
     交叉引用、citeproc 均按 Markdown 原生处理
  2. docx_layout 后处理：封面垂直居中、目录/正文分页、表格通栏 + 智能列宽、灰表头居中
  3. inspect_docx 校验：XML 良构、无重复属性、合并单元格数量与源文件一致
  4. （默认）同时输出 HTML 预览稿，便于浏览器里核对表格
  5. 原子写入目标文件（失败不会留下半成品；Word 占用文件时给出提示）

退出码：0 成功；1 失败（lint 错误 / pandoc 失败 / 校验失败）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from docx_layout import apply_layout  # noqa: E402
from inspect_docx import inspect, summarize  # noqa: E402
from lint_md import lint_file  # noqa: E402
from ooxml import check_zip_names, repack_forward_slashes  # noqa: E402
from table_fit import inject_html_colgroups  # noqa: E402

SKILL_ROOT = SCRIPTS.parent
DEFAULT_REF = SKILL_ROOT / "reference.docx"
DEFAULT_CSS = SKILL_ROOT / "assets" / "print.css"
LUA_FILTER = SKILL_ROOT / "filters" / "html_tables.lua"

READER = "markdown-markdown_in_html_blocks+east_asian_line_breaks"
MIN_PANDOC = (2, 17)  # Lua pandoc.write / pandoc.read 及复杂表格 AST
MERGE_PANDOC = (3, 0)  # docx writer 写出 gridSpan/vMerge（低于此版本由校验兜底报错）


# ------------------------------------------------------------------ console
def _setup_console() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")  # Windows 管道/GBK 控制台不因中文崩溃
        except (AttributeError, ValueError):
            pass


def info(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    print(f"error: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ------------------------------------------------------------------ pandoc
def find_pandoc(explicit: str | None) -> str:
    p = explicit or os.environ.get("PANDOC") or shutil.which("pandoc")
    if not p:
        fail("找不到 pandoc。请安装 pandoc ≥ 3.0（https://pandoc.org/installing.html）"
             "或用 --pandoc / 环境变量 PANDOC 指定路径")
    return p


def pandoc_version(pandoc: str) -> tuple[int, ...]:
    try:
        out = subprocess.run([pandoc, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        fail(f"无法运行 pandoc：{e}")
    m = re.search(r"pandoc(?:\.exe)?\s+(\d+(?:\.\d+)*)", out)
    if not m:
        fail(f"无法识别 pandoc 版本：{out[:200]!r}")
    return tuple(int(x) for x in m.group(1).split("."))


def run_pandoc(cmd: list[str], cwd: Path, verbose: bool) -> list[str]:
    if verbose:
        info("+ " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
    except subprocess.TimeoutExpired:
        fail("pandoc 超时（>600s）")
    msgs = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
    if r.returncode != 0:
        for ln in msgs:
            print("  pandoc: " + ln, file=sys.stderr)
        fail(f"pandoc 退出码 {r.returncode}")
    return msgs


# ------------------------------------------------------------------ helpers
def prepare_reference(ref: Path, tmpdir: Path) -> Path:
    if not ref.is_file():
        fail(f"reference.docx 不存在：{ref}")
    try:
        probs = check_zip_names(ref)
    except Exception as e:  # noqa: BLE001
        fail(f"reference.docx 不是有效的 docx/zip：{e}")
    if any("反斜杠" in p for p in probs):
        fixed = tmpdir / "reference.fixed.docx"
        repack_forward_slashes(ref, fixed)
        info(f"WARN  {ref.name}: {probs[0]}；已在临时副本中修复。"
             "建议运行 scripts/fix_reference.py 永久修复")
        probs = check_zip_names(fixed)
        ref = fixed
    if probs:
        fail(f"reference.docx 有问题：{'；'.join(probs)}")
    return ref


def write_meta_defaults(path: Path, toc_title: str, abstract_title: str, stem: str) -> None:
    # metadata-file 的优先级低于文档自身 YAML：文档里写了就以文档为准
    lines = [
        f"toc-title: {json.dumps(toc_title, ensure_ascii=False)}",
        f"abstract-title: {json.dumps(abstract_title, ensure_ascii=False)}",
        f"pagetitle: {json.dumps(stem, ensure_ascii=False)}",
        "lang: zh-CN",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def move_into_place(src: Path, dst: Path) -> None:
    try:
        os.replace(src, dst)
    except PermissionError:
        keep = dst.with_name(dst.stem + ".new" + dst.suffix)
        shutil.move(str(src), str(keep))
        fail(f"无法覆盖 {dst}（是否正在 Word 中打开？）。新文件已另存为 {keep}")
    except OSError:
        shutil.move(str(src), str(dst))


def build_preview_html(pandoc: str, source: Path, out_html: Path, css: Path,
                       meta: Path, tmpdir: Path, verbose: bool) -> None:
    style = tmpdir / "style.html"
    style.write_text("<style>\n" + css.read_text(encoding="utf-8") + "\n</style>\n",
                     encoding="utf-8")
    tmp_html = tmpdir / "preview.html"
    cmd = [pandoc, source.name, "-f", READER, "-t", "html5", "--standalone",
           "--mathml", f"--include-in-header={style}", f"--metadata-file={meta}",
           "-o", str(tmp_html)]
    run_pandoc(cmd, source.parent, verbose)
    text = tmp_html.read_text(encoding="utf-8")
    tmp_html.write_text(inject_html_colgroups(text), encoding="utf-8")
    move_into_place(tmp_html, out_html)


# ------------------------------------------------------------------ build
def build(source: Path, output: Path, *, reference: Path = DEFAULT_REF,
          css: Path = DEFAULT_CSS, html: bool = True, toc: bool = True,
          toc_depth: int = 2, toc_title: str = "目录", abstract_title: str = "摘要",
          cover_center: bool = True, force: bool = False, pandoc: str | None = None,
          extra_args: list[str] | None = None, verbose: bool = False) -> dict:
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        fail(f"源文件不存在：{source}")
    if source.suffix.lower() == ".docx" or source == output:
        fail("输入应为 .md，且不能与输出同名")
    if output.suffix.lower() != ".docx":
        fail(f"输出文件应以 .docx 结尾：{output}")
    if not css.is_file():
        fail(f"CSS 不存在：{css}")
    if not LUA_FILTER.is_file():
        fail(f"Lua 过滤器缺失：{LUA_FILTER}")

    pandoc = find_pandoc(pandoc)
    ver = pandoc_version(pandoc)
    vs = ".".join(map(str, ver))
    if ver < MIN_PANDOC:
        fail(f"pandoc {vs} 过旧，需要 ≥ {'.'.join(map(str, MIN_PANDOC))}（推荐 ≥ 3.1）")
    if ver < MERGE_PANDOC:
        info(f"WARN  pandoc {vs} 可能不支持在 docx 中写合并单元格；构建后会校验")

    # 0) lint
    issues, tables = lint_file(source)
    for it in issues:
        info(f"{it.level:5} {source.name}:{it.line} {it.msg[0:200]}")
    errors = [i for i in issues if i.level == "ERROR"]
    if errors and not force:
        fail(f"源文件有 {len(errors)} 个错误（见上）。修正后重试，或加 --force 强制构建")
    exp_colspan = sum(t.colspans for t in tables)
    exp_rowspan = sum(t.rowspans for t in tables)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix=".build-", dir=str(output.parent)))
    try:
        ref = prepare_reference(Path(reference).resolve(), tmpdir)
        meta = tmpdir / "defaults.yaml"
        write_meta_defaults(meta, toc_title, abstract_title, source.stem)

        # 1) MD → DOCX（单次）
        tmp_docx = tmpdir / "out.docx"
        cmd = [pandoc, source.name, "-f", READER, "-t", "docx", "-o", str(tmp_docx),
               f"--reference-doc={ref}", f"--lua-filter={LUA_FILTER}",
               f"--metadata-file={meta}",
               f"--resource-path={source.parent}{os.pathsep}."]
        if toc:
            cmd += ["--toc", f"--toc-depth={toc_depth}"]
        cmd += list(extra_args or [])
        info(f"[1/4] pandoc {vs}: {source.name} → docx")
        msgs = run_pandoc(cmd, source.parent, verbose)
        for ln in msgs:
            info("      pandoc: " + ln)

        # 2) 版式后处理
        info("[2/4] 版式后处理（封面居中 / 目录分页 / 表格通栏+列宽 / 灰表头居中）")
        layout = apply_layout(tmp_docx, cover_center=cover_center)

        # 3) 校验
        info("[3/4] 校验 docx")
        rep = inspect(tmp_docx)
        rep["file"] = str(output)
        got_col = sum(t["gridSpan"] for t in rep["tables"])
        got_row = sum(t["vMergeRestart"] for t in rep["tables"])
        if exp_colspan + exp_rowspan and got_col + got_row == 0:
            rep["errors"].append(
                f"源文件有 {exp_colspan} 处 colspan、{exp_rowspan} 处 rowspan，"
                f"但 docx 中没有任何合并单元格（pandoc {vs} 过旧？请升级到 ≥ 3.1）")
        elif (got_col, got_row) != (exp_colspan, exp_rowspan):
            rep["warnings"].append(
                f"合并单元格数量与源文件不一致：源 colspan {exp_colspan}/rowspan {exp_rowspan}，"
                f"docx gridSpan {got_col}/vMerge {got_row}")
        if len(rep["tables"]) < len(tables):
            rep["errors"].append(
                f"源文件有 {len(tables)} 张 HTML 表，docx 只有 {len(rep['tables'])} 张（有表格丢失）")
        if toc and not rep["toc"]:
            rep["warnings"].append("未找到目录域")
        info(summarize(rep))
        if rep["errors"]:
            bad = output.with_name(output.stem + ".failed.docx")
            shutil.move(str(tmp_docx), str(bad))
            fail(f"校验失败，问题文件保留在 {bad}")

        move_into_place(tmp_docx, output)
        info(f"[4/4] 已写入 {output}")

        if html:
            out_html = output.with_suffix(".html")
            build_preview_html(pandoc, source, out_html, css, meta, tmpdir, verbose)
            info(f"      HTML 预览：{out_html}")
        rep["layout"] = layout
        return rep
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main(argv: list[str] | None = None) -> None:
    _setup_console()
    ap = argparse.ArgumentParser(
        description="Markdown（含 HTML 合并表）→ DOCX。未识别的参数会原样传给 pandoc，"
                    "例如 --citeproc --bibliography refs.bib",
    )
    ap.add_argument("source", type=Path, help="输入 .md")
    ap.add_argument("-o", "--output", type=Path, help="输出 .docx（默认与源同名）")
    ap.add_argument("--reference-doc", type=Path, default=DEFAULT_REF)
    ap.add_argument("--css", type=Path, default=DEFAULT_CSS, help="HTML 预览用 CSS")
    ap.add_argument("--no-html", "--no-keep-html", dest="html", action="store_false",
                    help="不生成 HTML 预览稿")
    ap.add_argument("--keep-html", dest="html", action="store_true",
                    help="生成 HTML 预览稿（默认）")
    ap.add_argument("--no-toc", action="store_true", help="不生成目录")
    ap.add_argument("--toc-depth", type=int, default=2)
    ap.add_argument("--toc-title", default="目录")
    ap.add_argument("--abstract-title", default="摘要")
    ap.add_argument("--no-cover-center", action="store_true", help="首页不垂直居中")
    ap.add_argument("--force", action="store_true", help="lint 有错误也继续构建")
    ap.add_argument("--pandoc", help="pandoc 可执行文件路径")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印 pandoc 命令")
    ap.set_defaults(html=True)
    args, extra = ap.parse_known_args(argv)
    bad = [a for a in extra if a.startswith("-o") or a.startswith("--output")]
    if bad:
        fail(f"不支持的参数：{bad}")

    out = args.output or args.source.with_suffix(".docx")
    build(args.source, out, reference=args.reference_doc, css=args.css, html=args.html,
          toc=not args.no_toc, toc_depth=args.toc_depth, toc_title=args.toc_title,
          abstract_title=args.abstract_title, cover_center=not args.no_cover_center,
          force=args.force, pandoc=args.pandoc, extra_args=extra, verbose=args.verbose)


if __name__ == "__main__":
    main()

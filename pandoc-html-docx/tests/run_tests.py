#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：python tests/run_tests.py   （需要 pandoc ≥ 3.0）

覆盖原版出过问题的场景：BOM + CRLF、复杂 YAML（引号/列表/折叠块）、无 YAML、
脚注与公式不丢失、custom-style、子目录图片 + 从其他目录调用、缺空行的表、无表头表、
colspan+rowspan 组合、嵌套表、```html 代码块、HTML 注释、中文文件名、
重复 tcPr/pPr、schema 顺序、后处理幂等、反斜杠路径的 reference.docx、lint 报错。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
FIX = HERE / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from docx_layout import apply_layout  # noqa: E402
from inspect_docx import inspect  # noqa: E402
from lint_md import lint_file  # noqa: E402


def run_build(src: Path, out: Path, *extra: str, cwd: Path | None = None):
    cmd = [sys.executable, str(SCRIPTS / "build.py"), str(src), "-o", str(out), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(cwd or HERE))


def doc_xml(p: Path) -> str:
    return zipfile.ZipFile(p).read("word/document.xml").decode("utf-8")


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="phd-test-"))
        # 中文文件名 + BOM + CRLF 版本的 edge.md，放在另一个目录（图片相对源文件解析）
        src_dir = cls.tmp / "源文件"
        src_dir.mkdir()
        shutil.copytree(FIX / "img", src_dir / "img")
        text = (FIX / "edge.md").read_text(encoding="utf-8")
        (src_dir / "边界用例.md").write_bytes(
            b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
        cls.edge_src = src_dir / "边界用例.md"
        cls.edge_out = cls.tmp / "输出" / "边界用例.docx"
        cls.edge_run = run_build(cls.edge_src, cls.edge_out, cwd=cls.tmp)
        cls.rep = inspect(cls.edge_out) if cls.edge_out.exists() else None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_edge_build_ok(self):
        self.assertEqual(self.edge_run.returncode, 0,
                         self.edge_run.stdout + self.edge_run.stderr)
        self.assertEqual(self.rep["errors"], [])
        self.assertEqual(self.rep["warnings"], [])
        self.assertTrue(self.edge_out.with_suffix(".html").exists())
        leftovers = [p.name for p in self.edge_out.parent.iterdir() if p.name.startswith(".build-")]
        self.assertEqual(leftovers, [])

    def test_footnote_and_math_survive(self):
        self.assertEqual(self.rep["footnotes"], 1)
        self.assertGreaterEqual(self.rep["equations"], 2)

    def test_metadata(self):
        from ooxml import Docx, text_of, w
        root = Docx(self.edge_out).xml("word/document.xml").root
        x = "\n".join(text_of(p) for p in root.iter(w("p")))
        for s in ("边界用例：冒号「：」与", "引号", "张三", "李四", "YAML 单引号", "折叠摘要"):
            self.assertIn(s, x)

    def test_custom_style_and_image(self):
        x = doc_xml(self.edge_out)
        self.assertIn('w:val="Quote-Block"', x)
        self.assertIn('w:val="Term"', x)
        names = zipfile.ZipFile(self.edge_out).namelist()
        self.assertTrue(any(n.startswith("word/media/") for n in names), names)

    def test_tables(self):
        tbls = self.rep["tables"]
        # 管道表、恢复的缺空行表、无表头表、合并表、嵌套内表
        self.assertEqual(len(tbls), 5, tbls)
        self.assertNotIn("这是代码", "".join(str(t) for t in tbls))
        no_head = [t for t in tbls if t["headerRows"] == 0]
        self.assertTrue(no_head, "无表头表不应被染灰")
        for t in tbls:
            if t["headerRows"]:
                self.assertTrue(t["headerGray"], t)
                self.assertTrue(t["headerCentered"], t)
        merged = max(tbls, key=lambda t: t["gridSpan"] + t["vMergeRestart"])
        self.assertGreaterEqual(merged["gridSpan"], 3)
        self.assertGreaterEqual(merged["vMergeRestart"], 2)
        x = doc_xml(self.edge_out)
        self.assertIn("**公司", x)
        self.assertIn("y &amp; z", x)

    def test_layout(self):
        self.assertEqual(self.rep["sections"], ["center", "top"])
        self.assertTrue(self.rep["toc"])
        x = doc_xml(self.edge_out)
        self.assertIn('<w:pageBreakBefore w:val="0"', x)

    def test_idempotent(self):
        copy = self.tmp / "again.docx"
        shutil.copy(self.edge_out, copy)
        apply_layout(copy)
        rep = inspect(copy)
        self.assertEqual(rep["sections"], self.rep["sections"])
        self.assertEqual(rep["pageBreakBefore"], self.rep["pageBreakBefore"])
        self.assertEqual(rep["errors"], [])

    def test_plain_no_yaml_no_toc(self):
        out = self.tmp / "plain.docx"
        r = run_build(FIX / "plain.md", out, "--no-toc", "--no-html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = inspect(out)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(len(rep["sections"]), 1)
        self.assertFalse(out.with_suffix(".html").exists())

    def test_no_cover_center(self):
        out = self.tmp / "nocenter.docx"
        r = run_build(ROOT / "examples" / "sample.md", out, "--no-cover-center", "--no-html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = inspect(out)
        self.assertEqual(len(rep["sections"]), 2)
        self.assertNotIn("center", rep["sections"])

    def test_backslash_reference_is_repaired(self):
        bad = self.tmp / "bad-ref.docx"
        with zipfile.ZipFile(ROOT / "reference.docx") as zin, \
                zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as zout:
            for n in zin.namelist():
                zout.writestr(n.replace("/", "\\"), zin.read(n))
        out = self.tmp / "badref.docx"
        r = run_build(ROOT / "examples" / "sample.md", out, "--reference-doc", str(bad), "--no-html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("反斜杠", r.stdout)
        x = doc_xml(out)
        self.assertIn('w:val="a6"', x)  # 用上了模板里的 Title 样式 id，而不是 pandoc 默认

    def test_lint_blocks_bad_table(self):
        out = self.tmp / "bad.docx"
        r = run_build(FIX / "bad.md", out, "--no-html")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(out.exists())
        issues, tables = lint_file(FIX / "bad.md")
        msgs = "\n".join(str(i) for i in issues)
        self.assertIn("占 2 列", msgs)
        self.assertIn("rowspan=3 越出", msgs)
        self.assertIn("colspan=\"abc\"", msgs)
        self.assertIn("结构化对照如下", msgs)

    def test_lint_edge_warnings(self):
        issues, tables = lint_file(FIX / "edge.md")
        self.assertEqual([i for i in issues if i.level == "ERROR"], [])
        msgs = "\n".join(str(i) for i in issues)
        self.assertIn("前一行不是空行", msgs)
        self.assertIn("```html", msgs)
        self.assertEqual(len(tables), 3)  # 代码块与注释里的表不计


if __name__ == "__main__":
    if not shutil.which(os.environ.get("PANDOC", "pandoc")):
        sys.exit("pandoc not found")
    unittest.main(verbosity=2)

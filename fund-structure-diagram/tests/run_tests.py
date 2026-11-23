#!/usr/bin/env python3
"""回归测试：python tests/run_tests.py

1. 渲染器：比例计算、金额格式、SVG 良构、布局分支（多项目 / 无管理人 / 多出资人）。
2. 命令行：render_svg.py 出图与 --check 校验。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import yaml  # noqa: E402

import fund_svg  # noqa: E402

SVG_NS = "{http://www.w3.org/2000/svg}"


def load_example(name):
    return yaml.safe_load((ROOT / "examples" / name).read_text(encoding="utf-8"))


def svg_texts(svg):
    root = ET.fromstring(svg.encode("utf-8"))
    return [t.text for t in root.iter(f"{SVG_NS}text")], root


class RendererTests(unittest.TestCase):
    def test_ratios_sum_to_100(self):
        r = fund_svg.compute_ratios([1, 1, 1])
        self.assertEqual(sum(r), Decimal("100.00"))
        self.assertEqual([str(x) for x in r], ["33.34", "33.33", "33.33"])
        self.assertEqual(fund_svg.compute_ratios([0, 0]), [None, None])

    def test_format(self):
        self.assertEqual(fund_svg.format_amount(4500), "4,500")
        self.assertEqual(fund_svg.format_amount(4500.0), "4,500")
        self.assertEqual(fund_svg.format_amount("1,234.50"), "1,234.5")
        self.assertEqual(fund_svg.format_ratio(1), "1.00%")
        self.assertEqual(fund_svg.format_ratio("9%"), "9.00%")

    def test_reference_sample(self):
        data = load_example("amac_sample.yaml")
        self.assertEqual(fund_svg.check(data), [])
        texts, root = svg_texts(fund_svg.render_svg(data))
        for expected in ["中基协备案基金架构图（示例）", "1.00%", "500 万元", "40.00%", "20,000 万元",
                         "（GP）", "受托管理", "资金托管", "项目投资", "登记编码：P1000000", "底层项目"]:
            self.assertIn(expected, texts)
        greys = [r for r in root.iter(f"{SVG_NS}rect") if r.get("fill") == fund_svg.GREY]
        self.assertEqual(len(greys), 2, "GP 与基金主体灰底")
        arrows = [l for l in root.iter(f"{SVG_NS}line") if l.get("marker-end")]
        self.assertEqual(len(arrows), 3)
        self.assertEqual(root.get("width"), "1152")

    def test_multi_project_and_dense_partners(self):
        data = load_example("multi_project.yaml")
        texts, root = svg_texts(fund_svg.render_svg(data))
        arrows = [l for l in root.iter(f"{SVG_NS}line") if l.get("marker-end")]
        self.assertEqual(len(arrows), 4)  # 管理人 1 + 项目 3
        self.assertIn("持股 5.5%", texts)
        self.assertNotIn("托管银行", texts)

    def test_minimal_and_escaping(self):
        svg = fund_svg.render_svg({"fund": "A&B <基金>", "partners": [{"name": "甲", "amount": 1}],
                                   "projects": []})
        texts, _ = svg_texts(svg)
        self.assertIn("A&B <基金>", texts)
        self.assertIn("100.00%", texts)

    def test_check_messages(self):
        msgs = fund_svg.check({"fund": {"name": "F", "form": "合伙企业（有限合伙）"},
                               "partners": [{"name": "A", "role": "LP", "ratio": 50}],
                               "manager": {"name": "G", "code": "X1"}})
        self.assertTrue(any("100%" in m for m in msgs))
        self.assertTrue(any("GP" in m for m in msgs))
        self.assertTrue(any("P 开头" in m for m in msgs))

    def test_long_names_wrap_inside_box(self):
        data = {"fund": {"name": "某" * 30, "form": "合伙企业（有限合伙）"},
                "partners": [{"name": "某某某某某某某某某某某某某某某某有限公司", "role": "GP", "amount": 1}]}
        texts, root = svg_texts(fund_svg.render_svg(data))
        for t in texts:
            self.assertLessEqual(fund_svg._text_em(t), 31)


class CliTests(unittest.TestCase):
    def test_render_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.svg"
            subprocess.run([sys.executable, str(SCRIPTS / "render_svg.py"),
                            str(ROOT / "examples" / "amac_sample.yaml"), "-o", str(out)], check=True)
            texts, _ = svg_texts(out.read_text(encoding="utf-8"))
            self.assertIn("F 基金", texts)

            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"fund": "F", "partners": [{"name": "A", "ratio": 60}]}), encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPTS / "render_svg.py"), str(bad), "--check"],
                               capture_output=True, text=True, check=True)
            self.assertIn("不等于 100%", r.stderr)
            self.assertFalse(bad.with_suffix(".svg").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

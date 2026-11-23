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
        self.assertEqual(root.get("viewBox"), f"0 0 {root.get('width')} {root.get('height')}")

    def test_boxes_hug_text(self):
        """方框四周只留 PAD：框宽 = 最长文字行 + 2×PAD_X（不小于 MIN_BOX_W）。"""
        texts, root = svg_texts(fund_svg.render_svg(load_example("amac_sample.yaml")))
        rects = list(root.iter(f"{SVG_NS}rect"))[1:]
        text_els = list(root.iter(f"{SVG_NS}text"))
        s = fund_svg.SCALE
        for r in rects:
            x, y, w, h = (float(r.get(k)) for k in ("x", "y", "width", "height"))
            inside = [t for t in text_els
                      if x < float(t.get("x")) < x + w and y < float(t.get("y")) < y + h]
            self.assertTrue(inside)
            fs = float(inside[0].get("font-size"))
            text_w = max(fund_svg._text_em(t.text) for t in inside) * fs
            expected = max(fund_svg.MIN_BOX_W * s, text_w + 2 * fund_svg.PAD_X * s)
            self.assertAlmostEqual(w, expected, delta=1.0)
            n = len(inside)
            expected_h = ((n - 1) * fund_svg.LINE_SPACING + 1) * fs + 2 * fund_svg.PAD_Y * s
            self.assertLessEqual(h, expected_h + 1.0)

    def test_given_ratio_precision_kept(self):
        self.assertEqual(fund_svg.format_ratio("0.61069%"), "0.61069%")
        self.assertEqual(fund_svg.format_ratio("6.1"), "6.10%")

    def test_many_partners_split_rows_and_trunk_clear(self):
        partners = [{"name": f"第{i}号有限公司", "role": "LP", "amount": 100} for i in range(13)]
        texts, root = svg_texts(fund_svg.render_svg({"fund": "F", "partners": partners, "projects": []}))
        rects = list(root.iter(f"{SVG_NS}rect"))[1:]
        rows = sorted({r.get("y") for r in rects[:-1]}, key=float)
        self.assertEqual(len(rows), 3)  # 13 位、每排至多 6 位 → 5/4/4
        # 竖向主干（x = 基金中心）不得穿过任何出资人方框
        fund = rects[-1]
        trunk_x = float(fund.get("x")) + float(fund.get("width")) / 2
        for r in rects[:-1]:
            x, w = float(r.get("x")), float(r.get("width"))
            if r.get("y") != rows[0]:
                self.assertFalse(x < trunk_x < x + w, "主干穿过了方框")

    def test_balanced_wrap(self):
        lines = fund_svg._wrap("上海某某私募基金管理有限公司", 13)
        self.assertEqual(lines, ["上海某某私募基", "金管理有限公司"])

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

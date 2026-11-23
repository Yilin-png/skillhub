#!/usr/bin/env python3
"""回归测试：python tests/run_tests.py"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

import equity_svg  # noqa: E402

SVG_NS = "{http://www.w3.org/2000/svg}"


def load_example(name):
    return yaml.safe_load((ROOT / "examples" / name).read_text(encoding="utf-8"))


def svg_texts(svg):
    root = ET.fromstring(svg.encode("utf-8"))
    return [t.text for t in root.iter(f"{SVG_NS}text")], root


class RendererTests(unittest.TestCase):
    def test_ratios_and_format(self):
        self.assertEqual(sum(equity_svg.compute_ratios([1, 1, 1])), Decimal("100.00"))
        self.assertEqual(equity_svg.format_ratio("80"), "80.00%")
        self.assertEqual(equity_svg.format_amount(1000), "1,000")

    def test_sample_due_diligence_chart(self):
        data = load_example("sample.yaml")
        self.assertEqual(equity_svg.check(data), [])
        texts, root = svg_texts(equity_svg.render_svg(data))
        for expected in [
            "星澜科技股权架构图", "截至2026年9月30日", "（实际控制人）", "持股 55.00%",
            "认缴 550 万元", "表决权 100.00%", "所持股权已质押", "注册资本 1,000 万元",
            "（普通合伙人）", "（有限合伙）", "全资子公司", "持股 70.00%",
        ]:
            self.assertIn(expected, texts)
        self.assertTrue(root.get("font-family").startswith("SimSun"))
        for sans in ("Sans", "Hei", "YaHei"):
            self.assertNotIn(sans, root.get("font-family"))

        rects = list(root.iter(f"{SVG_NS}rect"))[1:]
        text_els = list(root.iter(f"{SVG_NS}text"))

        def boxes(first_line):
            found = []
            for r in rects:
                x, y, w, h = (float(r.get(k)) for k in ("x", "y", "width", "height"))
                inside = [t.text for t in text_els if x < float(t.get("x")) < x + w and y < float(t.get("y")) < y + h]
                if inside and inside[0] == first_line:
                    found.append((y, w, h, r.get("fill")))
            return found

        holdco = boxes("星澜控股有限公司")[0]
        upper = boxes("李四")[0]
        person = boxes("张三")[0]
        self.assertLess(upper[0], holdco[0], "穿透层在被穿透主体上方")
        self.assertEqual(upper[1:3], holdco[1:3])
        self.assertEqual(person[1:3], holdco[1:3])
        self.assertEqual(person[3], equity_svg.GREY)
        greys = [r for r in rects if r.get("fill") == equity_svg.GREY]
        self.assertGreaterEqual(len(greys), 2)

    def test_check_messages(self):
        msgs = equity_svg.check({
            "target": {"name": "标的", "form": "有限责任公司", "capital": 100},
            "shareholders": [
                {"name": "甲", "ratio": 40, "amount": 40},
                {"name": "乙公司", "penetrate": True, "ratio": 40, "amount": 30},
            ],
            "subsidiaries": [{"name": "子"}],
        })
        self.assertTrue(any("100%" in m for m in msgs))
        self.assertTrue(any("向上穿透" in m for m in msgs))
        self.assertTrue(any("注册资本" in m for m in msgs))
        self.assertTrue(any("子公司" in m for m in msgs))


class CliTests(unittest.TestCase):
    def test_render_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.svg"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "render_svg.py"),
                 str(ROOT / "examples" / "sample.yaml"), "-o", str(out)],
                check=True,
            )
            texts, _ = svg_texts(out.read_text(encoding="utf-8"))
            self.assertIn("星澜科技有限公司", texts)


if __name__ == "__main__":
    unittest.main(verbosity=2)

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
                         "（普通合伙人）", "受托管理", "资金托管", "项目投资", "登记编码：P1000000", "底层项目"]:
            self.assertIn(expected, texts)
        greys = [r for r in root.iter(f"{SVG_NS}rect") if r.get("fill") == fund_svg.GREY]
        self.assertEqual(len(greys), 2, "GP 与基金主体灰底")
        arrows = [l for l in root.iter(f"{SVG_NS}line") if l.get("marker-end")]
        self.assertEqual(len(arrows), 3)
        self.assertEqual(root.get("viewBox"), f"0 0 {root.get('width')} {root.get('height')}")

    def test_boxes_harmonized(self):
        """出资人方框同宽同高、以最长文字 + PAD 为准；其余方框不小于它；中排三框同高。"""
        texts, root = svg_texts(fund_svg.render_svg(load_example("amac_sample.yaml")))
        rects = [tuple(float(r.get(k)) for k in ("x", "y", "width", "height"))
                 for r in list(root.iter(f"{SVG_NS}rect"))[1:]]
        partners, (fund, manager, custodian, project) = rects[:5], rects[5:]
        self.assertEqual({(w, h) for _, _, w, h in partners}, {partners[0][2:]})
        base_w, base_h = partners[0][2:]

        s = fund_svg.SCALE
        widest = max(fund_svg._text_em(t) for t in texts if t in ("A 合伙企业", "（普通合伙人）", "（有限合伙人）"))
        self.assertAlmostEqual(base_w, widest * 10 + 2 * fund_svg.PAD_X * s, delta=1.0)

        for _, _, w, h in (fund, manager, custodian, project):
            self.assertGreaterEqual(w, base_w - 0.01)
            self.assertGreaterEqual(h, base_h - 0.01)
        self.assertEqual(fund[3], manager[3])
        self.assertEqual(fund[3], custodian[3])

    def test_role_text_and_songti_only(self):
        texts, root = svg_texts(fund_svg.render_svg(load_example("amac_sample.yaml")))
        self.assertIn("（普通合伙人）", texts)
        self.assertIn("（有限合伙人）", texts)
        self.assertNotIn("（GP）", texts)
        # 管理人 / 托管人：名称在上，性质加括号放在名称下方
        i = texts.index("G 公司")
        self.assertEqual(texts[i + 1:i + 3], ["（基金管理人）", "登记编码：P1000000"])
        j = texts.index("H 银行")
        self.assertEqual(texts[j + 1], "（托管银行）")
        self.assertNotIn("基金管理人", texts)
        family = root.get("font-family")
        for sans in ("Sans", "Hei", "YaHei"):
            self.assertNotIn(sans, family)
        self.assertTrue(family.startswith("SimSun"))

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

    def test_look_through_unregistered_partnership(self):
        """未备案有限合伙在本层方框上方再挂一层上层出资人，方框与本层同大。"""
        data = {
            "fund": {"name": "F 基金", "form": "合伙企业（有限合伙）"},
            "partners": [
                {"name": "甲公司", "role": "GP", "amount": 100},
                {
                    "name": "未备案合伙企业", "role": "LP", "amount": 900, "unregistered": True,
                    "partners": [
                        {"name": "上层普通合伙人", "role": "GP", "amount": 90},
                        {"name": "上层有限合伙人", "role": "LP", "amount": 810},
                    ],
                },
            ],
            "projects": [],
        }
        self.assertEqual(fund_svg.check(data), [])
        texts, root = svg_texts(fund_svg.render_svg(data))
        self.assertIn("上层普通合伙人", texts)
        self.assertIn("10.00%", texts)   # 90 / 900
        self.assertIn("90.00%", texts)
        rects = list(root.iter(f"{SVG_NS}rect"))[1:]
        by_text = {}
        text_els = list(root.iter(f"{SVG_NS}text"))
        for r in rects:
            x, y, w, h = (float(r.get(k)) for k in ("x", "y", "width", "height"))
            inside = [t.text for t in text_els if x < float(t.get("x")) < x + w and y < float(t.get("y")) < y + h]
            by_text.setdefault(inside[0], []).append((y, w, h))
        upper = by_text["上层普通合伙人"][0]
        host = by_text["未备案合伙企业"][0]
        peer = by_text["甲公司"][0]
        self.assertLess(upper[0], host[0], "穿透层在被穿透方框上方")
        self.assertEqual(upper[1:], host[1:])
        self.assertEqual(host[1:], peer[1:])

        missing = fund_svg.check({"fund": "F", "partners": [
            {"name": "甲", "role": "GP", "amount": 1},
            {"name": "某合伙企业", "role": "LP", "amount": 1, "unregistered": True},
        ], "projects": []})
        self.assertTrue(any("上层出资人" in m for m in missing))

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
        self.assertTrue(any("普通合伙人" in m for m in msgs))
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

#!/usr/bin/env python3
"""回归测试：python tests/run_tests.py

1. 渲染器：比例计算、金额格式、SVG 良构、布局分支（多项目 / 无管理人 / 多出资人）。
2. 问答 YAML：多文档解析、块类型白名单、code 块可编译、Mako 模板可编译（装了 mako 时）。
3. 用模拟的 DAList / DAObject / DAFile 执行问答里的出图代码块。
"""
from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "docassamble-fundstructure" / "docassamble" / "fundstructure"
INTERVIEW = PKG / "data" / "questions" / "fund_structure.yml"
sys.path.insert(0, str(PKG))

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


KNOWN_KEYS = {
    "metadata", "features", "sections", "modules", "objects", "mandatory", "code", "reconsider",
    "question", "subquestion", "field", "fields", "yesno", "continue button label",
    "continue button field", "section", "if", "validation code", "table", "rows", "columns",
    "edit", "delete buttons", "event", "need", "review",
}


class InterviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks = [b for b in yaml.safe_load_all(INTERVIEW.read_text(encoding="utf-8")) if b]

    def test_block_keys(self):
        for b in self.blocks:
            self.assertTrue(set(b) <= KNOWN_KEYS, f"未知键：{set(b) - KNOWN_KEYS}")

    def test_code_compiles(self):
        for b in self.blocks:
            for key in ("code", "validation code"):
                if key in b:
                    compile(b[key], "<interview>", "exec")
            if "if" in b:
                compile(str(b["if"]), "<if>", "eval")

    def test_mako_compiles(self):
        try:
            from mako.template import Template
        except ImportError:
            self.skipTest("未安装 mako")

        def walk(node):
            if isinstance(node, str):
                if "${" in node or node.lstrip().startswith("%"):
                    Template(node)
            elif isinstance(node, dict):
                for k, v in node.items():
                    walk(k)
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        for b in self.blocks:
            walk({k: v for k, v in b.items() if k not in ("code", "validation code")})

    def test_module_exports(self):
        names = set()
        for b in self.blocks:
            for key in ("code", "subquestion", "columns"):
                if key in b:
                    names |= set(re.findall(r"\b([a-z_]+)\(", str(b[key])))
        da_builtins = {"validation_error", "action_button_html", "url_action", "sum", "str", "format",
                       "show", "url_for", "add_action", "initialize", "write", "commit", "gather",
                       "set_section", "clear", "number", "join", "upper", "startswith", "strip"}
        missing = names - set(fund_svg.__all__) - da_builtins
        self.assertEqual(missing, set(), "问答里调用了模块未导出的函数")


class FakeObj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeFile:
    def initialize(self, filename):
        self.filename = filename

    def write(self, content):
        self.content = content

    def commit(self):
        pass


class SimulatedRunTests(unittest.TestCase):
    def test_generation_block(self):
        blocks = [b for b in yaml.safe_load_all(INTERVIEW.read_text(encoding="utf-8")) if b]
        gen = next(b["code"] for b in blocks if "files_ready = True" in str(b.get("code", "")))
        ns = {name: getattr(fund_svg, name) for name in fund_svg.__all__}
        ns.update(
            diagram_title="测试架构图", unit="万元", fund_name="F 基金", fund_form_text="合伙企业（有限合伙）",
            partners=[FakeObj(name="A", role="GP", amount=500.0), FakeObj(name="B", role="LP", amount=4500.0)],
            projects=[FakeObj(name="底层项目", note="", label="")], has_projects=True, project_label="项目投资",
            has_manager=True, manager_name="G 公司", manager_code="P1000000", manager_label="受托管理",
            has_custodian=False, svg_file=FakeFile(), json_file=FakeFile(),
        )
        exec(gen, ns)
        self.assertTrue(ns["files_ready"])
        self.assertEqual(ns["diagram_warnings"], [])
        texts, _ = svg_texts(ns["svg_file"].content)
        self.assertIn("90.00%", texts)
        self.assertIn("4,500 万元", texts)
        self.assertNotIn("托管银行", texts)
        self.assertIn('"name": "G 公司"', ns["json_file"].content)
        # 导出的 JSON 可直接再交给 render_svg
        import json
        fund_svg.render_svg(json.loads(ns["json_file"].content))


if __name__ == "__main__":
    unittest.main(verbosity=2)

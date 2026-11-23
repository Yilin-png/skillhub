#!/usr/bin/env python3
"""由 JSON/YAML 描述文件生成基金架构图 SVG（可选 PNG）。

用法：
  python scripts/render_svg.py examples/amac_sample.yaml -o out.svg
  python scripts/render_svg.py data.json -o out.svg --png out.png   # 需 cairosvg 或 rsvg-convert
  python scripts/render_svg.py data.yaml --check                    # 只做数据校验
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fund_svg  # noqa: E402


def load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(text)
    return json.loads(text)


def to_png(svg_path: Path, png_path: Path, dpi: int) -> None:
    try:
        import cairosvg

        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), dpi=dpi, scale=dpi / 72)
        return
    except ImportError:
        pass
    exe = shutil.which("rsvg-convert")
    if not exe:
        sys.exit("导出 PNG 需要 `pip install cairosvg` 或安装 rsvg-convert（librsvg）。")
    subprocess.run([exe, "-z", str(dpi / 72), "-o", str(png_path), str(svg_path)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", type=Path, help="JSON 或 YAML 数据文件")
    ap.add_argument("-o", "--output", type=Path, help="输出 SVG 路径（默认与数据文件同名 .svg）")
    ap.add_argument("--png", type=Path, help="同时导出 PNG")
    ap.add_argument("--dpi", type=int, default=300, help="PNG 分辨率，默认 300")
    ap.add_argument("--check", action="store_true", help="只校验数据，不出图")
    args = ap.parse_args()

    data = load(args.data)
    for msg in fund_svg.check(data):
        print(f"提示：{msg}", file=sys.stderr)
    if args.check:
        return

    out = args.output or args.data.with_suffix(".svg")
    out.write_text(fund_svg.render_svg(data), encoding="utf-8")
    print(f"SVG → {out}")
    if args.png:
        to_png(out, args.png, args.dpi)
        print(f"PNG → {args.png}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""永久修复 reference.docx 的 zip 路径（Windows 反斜杠 → /）。

用法：python scripts/fix_reference.py [reference.docx]   （原文件备份为 .bak.docx）
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ooxml import check_zip_names, repack_forward_slashes  # noqa: E402


def main() -> int:
    ref = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "reference.docx"
    probs = check_zip_names(ref)
    if not probs:
        print(f"{ref}: OK，无需修复")
        return 0
    print(f"{ref}: " + "；".join(probs))
    bak = ref.with_name(ref.stem + ".bak.docx")
    shutil.copy2(ref, bak)
    tmp = ref.with_name(ref.stem + ".fixed.docx")
    repack_forward_slashes(ref, tmp)
    tmp.replace(ref)
    left = check_zip_names(ref)
    print("已修复" if not left else "仍有问题：" + "；".join(left), f"（备份：{bak}）")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())

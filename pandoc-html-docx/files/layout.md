# 版式：首页垂直居中 + 目录/正文分页

分页与首页垂直居中由 `scripts/build.py` 在生成 docx 后自动注入（`scripts/docx_layout.py`），不要在 Markdown 里手写 `{=openxml}` 分页块（会与后处理叠加出空白页）。

## 目标版式（三页区）

| 页区 | 内容 | 实现 |
|------|------|------|
| 首页（封面元数据） | Title / Subtitle / Author / Date / Abstract | 独立节：分节符写在封面最后一段的 `w:pPr/w:sectPr`（不额外插空段），`w:vAlign=center`；水平对齐仍按样式 |
| 目录页 | 「目录」+ TOC 域 | 封面节后自动换页；TOC Heading 设 `pageBreakBefore=0`，避免空白页 |
| 正文区 | 各章连续 | 目录后的正文首段设 `pageBreakBefore`（首块是表格时才插分页段）；正文节 `w:vAlign=top`；**不按 H1 分页** |

```text
[首页·垂直居中]  →  分节下一页  →  [目录]  →  段前分页  →  [正文…]
```

## 构建时做了什么

1. lint 源文件（表格结构、缺空行、套话）
2. pandoc 单次 MD→DOCX（YAML 由 pandoc 原生解析；`<table>` 由 Lua 过滤器转为原生表格；含 `--toc`）
3. `apply_layout()`：封面分节居中 + 目录→正文分页 + 表格通栏 + 智能列宽／内边距 + 表头灰底居中；样式按名称解析 styleId，属性按 schema 顺序写入
4. `inspect_docx` 校验后原子写入

## Markdown 写法

```markdown
---
title: "文档标题"
subtitle: "副标题"
author: "作者"
date: "2026年8月7日"
abstract: |
  摘要（首页展示，左对齐）。
---

# 第一章

正文……
```

- **不要**再写正文前的 `{=openxml}` 分页块（会与后处理叠加）。  
- 关闭首页垂直居中：`build.py --no-cover-center`  
- 关闭目录：`build.py --no-toc`（仍可保留封面居中）

## 验收

打开 docx：

1. 首页标题/副标题/作者/日期/摘要在页面**上下居中**（整块位于版心中部）  
2. 目录单独一页（接在首页之后）  
3. 正文在目录之后**另页**开始；各章之间无硬分页  
4. 目录标题为中文「目录」  
5. 各表**通栏**；**序号列窄、文句列宽**；**表头灰底居中**（与 M&T 已发出备忘录一致）  
6. 正文无「结构化对照如下：」等空衔接句  

抽查 OOXML（可选）：

```bash
python scripts/inspect_docx.py out.docx
# 期望：分节：2（vAlign：center, top）；目录：有
```

对外备忘录字段与表格观感补充见 [delivery-format.md](delivery-format.md)。
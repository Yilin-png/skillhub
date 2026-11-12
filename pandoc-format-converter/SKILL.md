---
name: pandoc-format-converter
description: >-
  将中文法律/商务文书转为 Pandoc Markdown 并映射到 Word (.docx)
  样式。用户提到格式转换、中文编号转标题、reference.docx、pandoc 格式化、样式映射、脚注/引用/法条引文排版时使用；也适用于检查或修复
  reference.docx。
---
# Pandoc 格式转换器

配套文件（与本 skill 同目录）：`mapping-rules.md`（完整映射细则）、`reference.docx`（样式模板）。转换前先 Read 这两份。

## 目标

1. **正向**：中文文档 → Pandoc Markdown（基础 + 扩展语法）
2. **反向**：检查/修复 `reference.docx`（28 个官方样式 + 6 个自定义样式）
3. **扩展**：公式、脚注、文献引用、定义列表、交叉引用等
4. **自定义样式**：`custom-style` 映射引文块、落款、术语、修订标记等

## 强制规则（最高优先级）

- **A** 正文最高层编号 → `#`（H1）；YAML `title:` 不占层级；禁止全文从 `##` 起步
- **B** 标题去掉原始编号：`一、研究背景` → `# 研究背景`（编号是语义一部分时例外，如「第一次世界大战」）
- **C** 脚注默认行内 `^[内容]`；仅多处引用同一条时用 `[^id]`
- **D** 中文语境全角标点：「」『』（）：；，。？！

## 工作流 A：中文 → Pandoc Markdown

1. 分析结构：编号层级、标题/列表/定义列表、元数据、扩展语法、自定义样式场景（细则见 `mapping-rules.md`）
2. 建立映射并执行（详见同目录 mapping-rules）
3. 常用映射：
   - 章节/「一、」等标题 → `#`~`######`（去编号）
   - 普通段 → Body Text；短引用/按语 → `>`（Block Text）
   - 长段法条/合同原文 → `::: {custom-style="Quote-Block"}`
   - 落款 → `::: {custom-style="Signature-Block"}`
   - 首现术语 → `[词]{custom-style="Term"}`；外文 → `Foreign`；重点 → `Emphasis-Strong`；谈判新增 → `Redline`
4. 输出 Markdown；需要 docx 时用用户的 `reference.docx`：
   `pandoc input.md -o out.docx --reference-doc=reference.docx`

## 工作流 B：reference.docx 检查

必查：28 个英文官方样式齐全；First Paragraph / Definition / Definition Term / Compact 取消首行缩进；Verbatim Char basedOn Body Text Char；标题黑体；Block Text/Caption 无斜体；Date/TOC Heading/Bibliography 等勿用中文名；6 个自定义样式齐全。

### 自定义样式

| 名称 | 用途 |
|---|---|
| Quote-Block | 长段引文（法条、合同条款） |
| Signature-Block | 落款 |
| Emphasis-Strong | 暗红加粗强调 |
| Term | 首现术语下划线 |
| Foreign | 外文斜体 |
| Redline | 红字下划线（视觉修订，非 Track Changes） |

## 中文法律商务文书注意

- Quote-Block vs `>`：≥2 句长引文用 Quote-Block
- Redline 仅视觉标记，不开启 Word 修订模式
- 文献引用需 `.bib` + `--citeproc`
- 完整对照与边界案例见 `mapping-rules.md`

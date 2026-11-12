---
name: pandoc-html-docx
description: "Markdown（含 HTML 合并单元格表格）一键导出 Word：表格用 HTML colspan/rowspan 书写，build.py 经 Lua 过滤器交给 pandoc HTML reader 解析为原生表格，再单次转 docx（复用 reference.docx），脚注/公式/custom-style/交叉引用不丢失。默认首页元数据垂直居中、目录与正文分页、表头灰底居中、表格通栏、列宽按内容自适应；构建前自动 lint 表格结构，构建后自动校验 docx。半自动将局部文字结构化为合并表（原文保留、可重复；表前不加「结构化对照如下」套话）。适用于私募基金月刊、M&T 问题梳理备忘录、含跨行/跨列表格的中文报告。触发词：pandoc-html-docx、md转html转docx、HTML中间稿、合并单元格、colspan、rowspan、复杂表格导Word、首页居中、目录分页、结构化为表格、整理成表、表头居中、灰表头、表格通栏、智能列宽。简单无表/无合并文档仍用 pandoc-format-converter；可编辑 PPT 用 pandoc-powerpoint-convert；HTML/PDF 幻灯片用 marp。"
---

# Pandoc HTML→DOCX（合并单元格优先）

> 配套说明：本仓库/生态里，简单无合并表的中文→Markdown→docx 映射 skill 当前已保存为 [`pandoc-format-converter`](sand-workflow:pandoc-format-converter)（文中所称 `pandoc-word-convert` 与之对应）。标题层级、去编号、全角标点、custom-style 等映射细则以该 skill 的 `mapping-rules.md` 为准；冲突时以本 skill 的 `files/layout.md`、`files/delivery-format.md` 与 `scripts/build.py` 行为为准。

## 与 `pandoc-word-convert` 的分工

| 场景 | 用哪个 |
|------|--------|
| 正文为主、表格简单（无合并） | `pandoc-word-convert`（MD→DOCX 直出） |
| **表格需跨行/跨列**、月刊处分/新规表、结构化呈现优先 | **本 skill** |
| 局部文字要收成表，且有分组/对照/横幅层级 | **本 skill** 半自动 HTML 合并表（见 `files/text-to-table.md`） |
| 局部文字要收成表，仅扁平二维 | word-convert 半自动 pipe-table |
| 可编辑 PPT | `pandoc-powerpoint-convert` |
| HTML/PDF 幻灯片、Marp 主题 | `marp` |

标题层级、去编号前缀、全角标点等中文规则与 `pandoc-word-convert` **相同**（映射细则见该 skill 的 `files/mapping-rules.md`；冲突时以本 skill 的 `files/layout.md`、`files/delivery-format.md` 与 build 行为为准）。本 skill 增量：

1. **表格写 HTML**（`<table>` + `colspan`/`rowspan`），由 build 转成 Word 合并单元格
2. **版式由 build 后处理保证**：首页垂直居中；目录↔正文分页；**表格通栏**；**列宽／单元格内边距按内容自适应**（序号列收窄、短标签列至少放下最长标签、长文本列加宽加衬）；**表头灰底 `#D9D9D9` 且文字水平居中**
3. **半自动结构化制表（合并优先）**：结构明显时提议（须含合并草图），确认后写入；**原文保留、表为附加视图**（宁可重复不删源文）。表前**不加**「结构化对照如下：」等套话。细则见 [`files/text-to-table.md`](files/text-to-table.md)
4. **对外备忘录观感**：对齐 M&T 已发出稿（封面字段习惯、表头居中、无空衔接句）。见 [`files/delivery-format.md`](files/delivery-format.md)
5. **稳定性护栏**：构建前 lint（表格行列对不齐、rowspan 越界、缺空行、套话）；构建后校验（XML 良构、无重复属性、合并单元格数量与源文件一致）；失败不覆盖旧文件

## 管线

```text
source.md ─lint─► pandoc（单次）───────────────────► out.docx ─post─► 校验 ─► 原子写入
                  │ filters/html_tables.lua：              (封面居中/目录分页/
                  │ <table> → pandoc HTML reader → 原生表格  通栏+列宽/灰表头居中)
                  └► 同时输出 out.html 预览稿（仅供浏览器核对，不参与 docx 生成）
```

> 旧版是 MD→HTML→DOCX 两次转换：脚注会变成文末链接列表、`$公式$` 变成普通斜体字、
> YAML 需要手写解析器转交（遇到引号/列表/CRLF 就出错）。现在 HTML 只用来**表达表格**，
> 由 Lua 过滤器在同一次 pandoc 转换中解析，其余内容全部按 Markdown 原生处理。

**禁止**把含合并单元格的表写成 pipe-table（合并信息会丢）；一律写 HTML `<table>`。

一键构建：

```bash
python "<本 skill>/scripts/build.py" source.md -o output.docx
python "<本 skill>/scripts/build.py" --help        # 全部参数
# 未识别的参数原样传给 pandoc，例如文献引用：
python "<本 skill>/scripts/build.py" paper.md --citeproc --bibliography refs.bib
```

Windows PowerShell 也可用同目录 `scripts/build.ps1`。

默认参数：

| 项 | 默认 | 关闭/修改 |
|----|------|------|
| reference.docx | 本 skill 目录下 `reference.docx` | `--reference-doc` |
| 目录 | 开；深度 2；标题「目录」 | `--no-toc` / `--toc-depth` / `--toc-title` |
| 首页垂直居中 | 开 | `--no-cover-center` |
| HTML 预览稿 | 与输出同目录 `*.html` | `--no-html` |
| lint 错误 | 阻止构建 | `--force` |
| pandoc | PATH 中的 pandoc（需 ≥ 2.17，**推荐 ≥ 3.1**） | `--pandoc` 或环境变量 `PANDOC` |

## 工作流

```text
- [ ] 1. 按继承规则写好 source.md（标题从 # 起；编号前缀已删；YAML 齐全；备忘录元数据见 delivery-format）
- [ ] 1b. （可选）半自动制表：结构明显则提议合并草图 → 确认 → 原文后直接附 HTML 表（无套话）
- [ ] 2. 凡需合并的表格：用原生 HTML <table>，前后各空一行，不用 pipe-table；表头用 thead/th
- [ ] 3. （可选）python scripts/lint_md.py source.md   先单独检查表格结构
- [ ] 4. build.py 生成 docx（+ html 预览）；看终端里的校验摘要：colspan/rowspan 数、表头 灰底✓ 居中✓
- [ ] 5. 打开 Word：首页垂直居中、目录另页、正文另页、表格通栏、灰表头居中；无「结构化对照如下：」
```

### 步骤 1 — Markdown 正文

继承 `pandoc-word-convert` 规则 **A–F**（摘要），其中 **E / F** 在本管线的落地方式见 [files/layout.md](files/layout.md)：

- **A** 正文最高层 → `#`（H1），YAML `title` 不占层级
- **B** 标题去掉「一、」「（一）」「1.」等编号前缀
- **C** 脚注用行内 `^[…]`（本管线会生成真正的 Word 脚注）
- **D** 中文全角标点；双引号用 `“”`
- **E** 仅元数据↔目录↔正文入口分页；正文 H1 之间不分页（**由 build 后处理注入，勿在 MD 内写 `{=openxml}` 分页**）
- **F** Title/Subtitle/Author/Date 水平居中；Abstract 左对齐；**整页元数据块垂直居中（页面中心）**
- **G′（本 skill）** 局部文本→**HTML 合并表**：半自动提议（须含 rowspan/colspan 草图）；确认后写入；**原文必须保留**，表接其后，允许重复；**禁止**表前批量写「结构化对照如下：」。见 [files/text-to-table.md](files/text-to-table.md)、[files/delivery-format.md](files/delivery-format.md)

脱敏星号：正文里的 `**公司`、`李*`、`杨**` 会被 Markdown 当成加粗/斜体标记，**正文中写成 `\*\*公司`、`李\*`**；HTML 表格单元格内不需要转义（单元格按 HTML 解析）。

```markdown
---
title: "文档标题"
subtitle: "副标题"
author: "作者"
date: "2026年8月7日"
abstract: |
  摘要。
---

# 第一章

正文……
```

### 步骤 2 — HTML 表格（核心）

在 `.md` 中直接嵌入 HTML：

```markdown
## 某通知

导语……主要内容如下：

<table class="mt-reg">
  <thead>
    <tr>
      <th>事项</th>
      <th colspan="2">具体要求</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>定义</th>
      <td colspan="2">……</td>
    </tr>
    <tr>
      <th rowspan="2">子基金设立</th>
      <td>基金类型</td>
      <td>……</td>
    </tr>
    <tr>
      <td>出资限制</td>
      <td>……</td>
    </tr>
  </tbody>
</table>
```

约定：

1. **合并只用** `colspan` / `rowspan`；不要用空单元格假装合并。lint 会把「展开后列数对不上」的行报为错误。
2. **`<table>` 前后各空一行**，`<table>` 顶格写（不缩进）。否则 pandoc 会把它当成段落里的内联 HTML——build 会自动恢复并给出 WARN，但请修正源文件。
3. **表头行**用 `<thead>` + `<th>`；只有 thead 行会上灰底 `#D9D9D9` 并居中（无 thead 的表不上灰）。`mt-*` class 只区分栏目语义。表格宽度统一为版心 100%。列宽与单元格内边距由 `table_fit` 按文本自动分配；表头写「序号」的列自动收窄居中。
4. **跨列表题行**（如处分文号横幅）：`<td colspan="3">《纪律处分决定书》(中基协处分〔2024〕78号)</td>`。
5. 单元格内多段：用 `<p>` 或 `<br>`；单元格内格式用 HTML（`<strong>`、`<em>`），**不要**写 Markdown 语法，也放不了脚注/公式。
6. 不要用 ```` ```html ```` 围栏包表格（会变成代码块）；需要隔离时用 ```` ```{=html} ````。
7. **表前不加**「结构化对照如下：」；有实质引导语时可用「主要内容如下：」等一句。
8. 完整模式见 [files/html-tables.md](files/html-tables.md)；月刊三类表见 [files/monthly-patterns.md](files/monthly-patterns.md)；对外备忘录见 [files/delivery-format.md](files/delivery-format.md)；从叙述半自动抽表见 [files/text-to-table.md](files/text-to-table.md)。

### 步骤 3 — 构建

```bash
python scripts/build.py issue.md -o issue.docx
```

脚本内部（任何一步失败都不会覆盖已有的 `issue.docx`）：

1. **预检**：pandoc 版本；`reference.docx` zip 结构（Windows 反斜杠路径会在临时副本中自动修复，可用 `scripts/fix_reference.py` 永久修复）；`lint_md` 检查源文件
2. **pandoc 单次转换**：`-f markdown-markdown_in_html_blocks+east_asian_line_breaks --lua-filter filters/html_tables.lua --reference-doc … --toc`；在源文件所在目录运行，图片相对路径总能找到；`toc-title`/`abstract-title` 以低优先级默认值传入，文档 YAML 里写了以文档为准
3. **`docx_layout.apply_layout`**：封面最后一段写入分节符（`vAlign=center`）；目录后正文首段 `pageBreakBefore`；各表通栏 + 列宽/边距；表头灰底 + 居中；所有属性按 OOXML schema 顺序写入并去重
4. **`inspect_docx` 校验**：XML 良构、无重复 pPr/tcPr、合并单元格数与源文件一致、HTML 表数量不少于源文件。失败时问题文件保存为 `*.failed.docx`
5. 原子写入输出；若 Word 正占用该文件，新文件另存为 `*.new.docx` 并提示

### 步骤 4 — 验收

构建结束时终端会打印校验摘要，例如：

```text
分节：2（vAlign：center, top）；目录：有；脚注 1；公式 2
  表1: 5×3 宽=5000/pct colspan 3 / rowspan 1 (续 1)；表头 1 行 灰底✓ 居中✓；列宽 [1420, 3395, 3485]
```

随时可单独检查任意 docx（不依赖 officecli）：

```bash
python scripts/inspect_docx.py output.docx          # 摘要
python scripts/inspect_docx.py output.docx --json   # 完整报告
```

（装了 officecli 也可以继续用 `officecli get output.docx "/body/tbl[1]" --depth 2` 看 colspan / vmerge。）

目视（Word 中打开；首次打开如提示「更新域」请选「是」以生成目录）：

- 首页元数据位于页面**垂直中心**（LibreOffice 不支持节的垂直对齐，须用 Word 看）
- 目录中文「目录」，且目录与正文**分页**
- 表格**通栏**；**序号列窄、文句列宽**；表头文字**居中**、底色灰 `#D9D9D9`；正文不按章硬分页
- 正文中**无**「结构化对照如下：」一类空衔接句

### 回归测试（修改脚本后必跑）

```bash
python tests/run_tests.py
```

## 继承规则（指针）

不在此重复 28 样式清单。导出样式依赖本目录 `reference.docx`。后处理**按样式名**（Title、Date、TOC Heading…）解析 styleId，换用其他 reference.docx 无需改脚本。若需修模板、自定义 `Emphasis-Strong` / `Quote-Block` 等，按 `pandoc-word-convert` 的 reference 检修流程，改完可同步覆盖本 skill 的 `reference.docx`；**用 Word「另存为」或 `scripts/fix_reference.py` 打包，不要用会写出反斜杠路径的压缩工具重新打 zip**。

版式细则：[files/layout.md](files/layout.md)。对外备忘录观感：[files/delivery-format.md](files/delivery-format.md)。

## 示例

最小样例：[examples/sample.md](examples/sample.md) → `python scripts/build.py examples/sample.md`

## 常见失败

| 现象 | 原因 | 处理 |
|------|------|------|
| Word 里合并消失 | 用了 pipe-table；或 pandoc 过旧 | 改 HTML 表；升级 pandoc ≥ 3.1（build 校验会直接报错） |
| 某张表整张消失 | `<table>` 前没空行 / 被缩进 / 包在 ```` ```html ```` 里 | build 已自动恢复前两种并 WARN；补空行、顶格；不要用 ```` ```html ```` |
| lint 报「该行展开后占 N 列」 | colspan/rowspan 算错 | 按报错行号修正；确需强行出稿用 `--force` |
| 表头 `<th rowspan colspan>` 写在 tbody 里错位 | pandoc HTML reader 已知问题 | 过滤器已自动把 tbody 内 `<th>` 当 `<td>` 处理，无需手动改 |
| 样式全不对（像 pandoc 默认模板） | reference.docx 的 zip 用了反斜杠路径，macOS/Linux 的 pandoc 读不到 | build 会自动在副本中修复并提示；`python scripts/fix_reference.py` 永久修复 |
| 打开报「无法读取的内容」 | 旧版后处理写出重复 tcPr / 属性乱序 | 用当前 `build.py`；`inspect_docx.py` 可检出 |
| 表头文字未居中 / 无灰底 | 绕过 build；或表没有 `<thead>` | 用 `build.py`；表头放进 `<thead>` |
| 脚注变成文末链接、公式变普通文字 | 旧版两段式 HTML 中转 | 用当前 `build.py`（单次转换） |
| 正文里 `**公司` 变成加粗 | Markdown 把星号当强调 | 正文写 `\*\*公司`；表格单元格内无需转义 |
| 图片丢失 | 相对路径基准不对 | 当前 build 在源文件目录运行并设 `--resource-path`；仍丢失时看 pandoc WARN |
| 目录为空 | Word 未更新域 | 打开时选「更新域」，或右键目录 →「更新域」 |
| 目录英文 / 摘要标题英文 | 文档 YAML 覆盖了，或绕过 build | 用 build 默认值；或 YAML 写 `toc-title` / `abstract-title` |
| 无法覆盖输出文件 | 文件在 Word 中打开 | 关闭后重跑；新文件已另存为 `*.new.docx` |
| 首页与目录之间多一空白页 | TOC Heading 样式带 pageBreakBefore | build 已在有封面时关闭该段的 pageBreakBefore |
| 制表删了原文 / 未先确认 | 未按半自动规则 G′ | 见 `files/text-to-table.md`：确认后写；原文保留可重复 |
| 合并无语义、表更难读 | 为合并而合并 | 无层级时改用 word-convert 扁平表 |

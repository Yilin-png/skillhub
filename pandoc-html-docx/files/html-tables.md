# HTML 表格规则（合并单元格）

> 从叙述文字半自动抽表（何时提议、原文保留、合并草图）：见 [text-to-table.md](text-to-table.md)。

## 原则

1. 需要合并时 **只用** HTML `<table>`，不用 Pandoc pipe-table / grid-table。  
2. `colspan` = 跨列；`rowspan` = 跨行；二者可组合。  
3. 每一逻辑行的「单元格占位总数」必须等于表宽（含合并占用）。  
4. build 时 `filters/html_tables.lua` 用 pandoc 的 HTML reader 解析每张 `<table>`：跨列成为 `w:gridSpan`，跨行成为 `w:vMerge restart/continue`。`<table>` 前后须空行、顶格书写。  
5. **表头灰底居中、表格通栏、列宽自适应**：写 `<thead><th>`；`table_fit` 按表头与单元格文本分配列宽和内边距；`docx_layout` 在 OOXML 层强制 `w:shd`、`w:jc=center`、表格拉满版心（`print.css` 只影响 HTML 预览稿）。  
6. 单元格内容按 HTML 解析：格式用 `<strong>`/`<em>`/`<br>`/`<p>`，不写 Markdown 语法；脱敏星号 `**公司` 原样保留。  
7. 表直接接在叙述后；**不要**为制表插入「结构化对照如下：」。

## 最小合法示例

### 仅跨列

```html
<table class="mt-reg">
  <thead>
    <tr><th>事项</th><th colspan="2">具体要求</th></tr>
  </thead>
  <tbody>
    <tr><th>定义</th><td colspan="2">……长文本……</td></tr>
  </tbody>
</table>
```

### 仅跨行

```html
<table class="mt-reg">
  <thead>
    <tr><th>分类</th><th>细项</th><th>内容</th></tr>
  </thead>
  <tbody>
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

### 横幅行（全宽标题行）

用于协会处分「一文号一块」：

```html
<table class="mt-discipline">
  <thead>
    <tr>
      <th>违法违规情况</th>
      <th>违法违规依据</th>
      <th>处分结果</th>
    </tr>
  </thead>
  <tbody>
    <tr class="banner">
      <td colspan="3">《纪律处分决定书》(中基协处分〔2024〕78号)</td>
    </tr>
    <tr>
      <td>……</td>
      <td>……</td>
      <td>……</td>
    </tr>
  </tbody>
</table>
```

## Class 约定（配合 `assets/print.css`）

`mt-*` **只区分栏目语义**，不再区分颜色或列宽套餐。所有表（含 `mt-plain`）统一：

| 项 | 约定 |
|----|------|
| 表格宽度 | 版心 **100%** 通栏（build 后处理强制；勿在 HTML 写像素宽） |
| 表头底色 | **`#D9D9D9`**（Word 灰色 25%；含 `mt-plain`） |
| 表头文字 | 水平居中、加粗 |
| 列宽与间距 | **按内容自适应**（`table_fit`）：「序号／编号」列约 7%–10% 且居中、内边距小；短标签列中等；长文本列加宽、左右边距更大、顶端对齐。勿按 class 写死 30/45/25 等套餐 |

| class | 用途 |
|-------|------|
| `mt-reg` | 新规「事项 / 具体要求」 |
| `mt-discipline` | 协会处分三列表 |
| `mt-penalty` | 证监局处罚三列表 |
| `mt-plain` | 普通表（无栏目特指） |

`tr.banner td`：居中、可加粗、白底（CSS 已写）。

## 嵌入 Markdown 的方式

**推荐**：在 `.md` 正文中直接写 HTML 块（前后空行）：

```markdown
导语。主要内容如下：

<table class="mt-reg">
  ...
</table>

下一段正文。
```

少用 `` ```html `` 围栏（会变成代码块而非表格）。需要隔离原始 HTML 时再用 pandoc raw：

````markdown
```{=html}
<table class="mt-reg">...</table>
```
````

## 验收

写完先跑 lint（build 也会自动跑）：

```bash
python scripts/lint_md.py source.md
# 表（第 25 行）：5 行 × 3 列，colspan 3 处，rowspan 1 处
```

构建后（build 自动打印，也可单独运行）：

```bash
python scripts/inspect_docx.py out.docx
#   表1: 5×3 宽=5000/pct colspan 3 / rowspan 1 (续 1)；表头 1 行 灰底✓ 居中✓；列宽 [...]
```

| 期望 | 含义 |
|----------|------|
| docx 的 colspan / rowspan 数 = lint 统计数 | 合并全部生效（不一致时 build 会 WARN/ERROR） |
| `宽=5000/pct` | 通栏 |
| `灰底✓ 居中✓` | 表头灰底 `D9D9D9` 且居中 |

（officecli 仍可用：`officecli get out.docx "/body/tbl[N]" --depth 2` 看 `colspan` / `vmerge`。）

## 反模式

- 用空 `<td></td>` 对齐视觉但不写 `rowspan`  
- 表头与数据列数不一致  
- 在 HTML 表内再写 Markdown `| ... |`  
- 把合并表写成 pipe-table / grid-table  
- `<table>` 前不空行、缩进书写，或包在 ```` ```html ```` 围栏里  
- 在单元格里写 Markdown（`**粗**`、`^[脚注]`）——单元格按 HTML 解析  
- 每张表前写「结构化对照如下：」「要点汇总如下：」等空衔接句  
- 表头文字左对齐或粉底/无底色（应用 `thead/th` + build 后处理居中与灰底）
- 在 `<table>` 上写死像素宽，或按 class 分套列宽百分比（应通栏，由 build 统一）

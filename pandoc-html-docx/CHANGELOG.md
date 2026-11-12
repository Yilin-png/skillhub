# 更新记录

## 2026-11 稳定性重构

### 发现并修复的问题

| # | 问题 | 后果 | 修复 |
|---|------|------|------|
| 1 | `reference.docx` 的 zip 内路径是 Windows 反斜杠（`word\document.xml`） | macOS/Linux 上 pandoc 读不到模板，**静默回退默认样式**；后处理随后报 `trailing sectPr not found`，连自带 sample 都构建失败 | 重新打包；build 预检自动在临时副本中修复；新增 `scripts/fix_reference.py` |
| 2 | 两段式 MD→HTML→DOCX | 行内脚注 `^[…]` 变成文末超链接列表（非 Word 脚注）；`$E=mc^2$` 变成普通斜体字（非 OMML 公式） | 改为单次 MD→DOCX：`filters/html_tables.lua` 把 `<table>` 交给 pandoc HTML reader 解析成原生表格（保留 colspan/rowspan），其余按 Markdown 原生处理 |
| 3 | 手写 YAML 解析器 + 重新拼 YAML | 标题含 `\"`、`author` 为列表、`>-` 折叠块、BOM/CRLF 时构建失败或丢元数据 | 不再解析 YAML，由 pandoc 原生读取 |
| 4 | 正则改 XML：只认 `<w:tcPr>…</w:tcPr>`，不认 pandoc 3.x 的自闭合 `<w:tcPr/>` | 每个表格单元格产生**重复 tcPr**（sample 中 19 处），属性还按非 schema 顺序插入（35 处）——Word 可能报「无法读取的内容」 | 改用 ElementTree（`scripts/ooxml.py`），按 ECMA-376 顺序写入并去重；保留根节点全部命名空间声明 |
| 5 | 封面样式 ID 硬编码（`a6`/`a7`/`11`） | 当前模板中 Date 是 `10`、`11` 是 **Bibliography**；换模板即失效 | 按样式名从 styles.xml 解析 ID |
| 6 | 无 `<thead>` 的表也把第一行当表头上灰 | 数据行被误染灰 | 只处理 `w:tblHeader` 行 |
| 7 | 目录后插入「只含分页符的段落」 | 正文页顶多一个空行；首个标题的书签留在目录页 | 改为正文首段 `pageBreakBefore` |
| 8 | 封面后额外插入空的分节段 | 垂直居中整体偏上 | 分节符写进封面最后一段的 pPr |
| 9 | `<table>` 前缺空行 / 被缩进 | 表格被当成内联 HTML，**整张表静默消失** | Lua 过滤器自动恢复 + lint 警告 |
| 10 | pandoc HTML reader：`<tbody>` 中同时带 rowspan+colspan 的 `<th>` 丢 colspan | 表格错位并多出空单元格 | 过滤器解析前把 tbody 内 `<th>` 视为 `<td>` |
| 11 | pandoc 给嵌套表格段落写两个 `<w:jc>` | schema 违规 | 后处理统一去重 |
| 12 | 图片相对路径以当前工作目录为基准 | 从别的目录调用时图片丢失 | 在源文件目录运行 pandoc 并设 `--resource-path` |
| 13 | 失败时留下半成品 / 临时 `.meta.yaml`；Word 占用文件时直接崩溃 | — | 临时目录 + 原子替换；占用时另存 `*.new.docx` |
| 14 | 短标签列（如「子基金设立」）被压到 12% 宽而折行 | 观感差 | 短标签列最小宽度按最长标签计算 |

### 新增

- `scripts/lint_md.py`：构建前检查 HTML 表格（逐行展开 rowspan/colspan 核对列数、rowspan 越界、非法 span 值）、缺空行、```` ```html ```` 围栏、禁用套话
- `scripts/inspect_docx.py`：构建后校验（XML 良构、重复属性、schema 顺序、合并单元格数、表头灰底/居中、分节、目录、脚注、公式），替代 officecli
- `tests/run_tests.py`：12 项回归测试
- build 支持把未识别参数透传给 pandoc（如 `--citeproc --bibliography refs.bib`）；`--force`、`--pandoc`、`-v`
- 默认 `east_asian_line_breaks`：中文硬换行不再在 Word 中变成空格

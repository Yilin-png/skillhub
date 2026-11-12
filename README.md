# skillhub

Yilin 的 Agent Skills 仓库：从 Grok Bot 各助手收集、可复用的技能包。

## Skills

| Skill | 用途 |
|-------|------|
| [legal-redact-jinja](./legal-redact-jinja/) | 中文法律文书脱敏为 Jinja2 模板 + 私有变量文件 |
| [pandoc-format-converter](./pandoc-format-converter/) | 中文法律/商务文书 → Pandoc Markdown → Word 样式映射 |
| [pandoc-html-docx](./pandoc-html-docx/) | Markdown（含 HTML 合并单元格表格）一键导出 Word |

每个子目录是一个独立 skill，入口为 `SKILL.md`。

## 来源

同步自 Grok Bot 共享技能库（`agent-data/workflows`），供版本管理与跨环境复用。

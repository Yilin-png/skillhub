# 问答清单

agent 在对话中按此顺序提问，答案写成 YAML 后用 `scripts/render_svg.py` 出图。
用户已经给了股权表、章程、工商信息或穿透说明的，先从材料里提取，缺什么再问。

| 步 | 问题 | 数据字段 | 默认 / 规则 |
|----|------|----------|-------------|
| 1 | 图题 | `title` | 「公司简称 + 股权架构图」 |
| 1 | 截至日期 | `as_of` | 尽调基准日；图上写成「截至某年某月某日」 |
| 1 | 金额单位 | `unit` | 万元 |
| 2 | 标的公司名称、组织形式、注册资本 | `target.name / form / capital` | 有限责任公司 |
| 3…n | 第 i 位直接股东：名称、类型（自然人 / 公司 / 合伙企业）、持股比例或认缴金额、是否实际控制人 | `shareholders[i]` | 自左向右；只给金额时比例自动算 |
| 3…n | 该股东是否向上穿透（控股公司、员工持股平台、未代持还原的主体）？是则继续问它的股东，合伙企业要区分 GP / LP | 嵌套 `shareholders`，或 `penetrate: true` | 穿透层比例按该层金额单独计算 |
| 3…n | 表决权是否与持股比例不同？股权是否质押、代持？ | `voting`、`note` | 相同则不写；备注原样标在连线旁 |
| 4 | 还有其他直接股东吗？ | — | 展示已录入表，核对合计是否 100%、认缴是否等于注册资本 |
| 5…m | 下属子公司：名称、组织形式、标的公司持股比例、备注（如全资） | `subsidiaries` | 没有就写 `subsidiaries: []` |

规则：

- 自然人只写姓名。实际控制人写 `role: 实际控制人`，方框灰底，下面一行是「（实际控制人）」。
- 公司写 `form: 有限责任公司`（或股份有限公司），方框下面一行是组织形式。
- 合伙企业写 `form: 有限合伙`。它的上层出资人用 `role: GP` / `LP`，图上显示「（普通合伙人）」「（有限合伙人）」，普通合伙人灰底。
- 持股比例至少两位小数；用户给得更精确时原样保留。
- 同一人在标的公司和控股公司里各持有股份时，两处都写，各画一个方框。
- 用户只贴了一张股权表时，先出直接股东这一层，再问哪些主体要穿透、有没有子公司。

```yaml
title: 星澜科技股权架构图
as_of: 2026年9月30日
unit: 万元
target: {name: 星澜科技有限公司, form: 有限责任公司, capital: 1000}
shareholders:
  - {name: 张三, role: 实际控制人, ratio: 15, amount: 150}
  - name: 星澜控股有限公司
    form: 有限责任公司
    ratio: 55
    amount: 550
    shareholders:
      - {name: 张三, role: 实际控制人, ratio: 80, amount: 800, voting: 100}
      - {name: 李四, ratio: 20, amount: 200, note: 所持股权已质押}
  - name: 星澜员工持股平台
    form: 有限合伙
    ratio: 20
    amount: 200
    shareholders:
      - {name: 张三, role: GP, amount: 2}
      - {name: 王某, role: LP, amount: 80}
      - {name: 其他员工, role: LP, amount: 118}
subsidiaries:
  - {name: 星澜北京科技有限公司, form: 有限责任公司, ratio: 100, note: 全资子公司}
```

可选键：`show_ratio` / `show_amount`（默认 true）、`max_per_row`（默认 6）、`highlight: true`（把任意方框涂灰）。

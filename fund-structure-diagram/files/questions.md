# 问答清单

agent 在对话中按此顺序提问，答案写成 YAML/JSON 后用 `scripts/render_svg.py` 出图。
可一次性把整张清单发给用户，也可逐步追问；用户已在材料里给出的信息不要重复问。

| 步 | 问题 | 数据字段 | 默认值 / 规则 |
|----|------|----------|---------------|
| 1 | 架构图标题 | `title` | 中基协备案基金架构图 |
| 1 | 基金组织形式：合伙型 / 公司型 / 契约型 | 决定出资人称谓与身份选项 | 合伙型 |
| 1 | 金额单位 | `unit` | 万元 |
| 2 | 基金名称 | `fund.name` | 必填 |
| 2 | 组织形式（方框第二行） | `fund.form` | 合伙型→合伙企业（有限合伙）；公司型→有限责任公司；契约型→契约型私募基金 |
| 3…n | 第 i 位出资人：名称、身份（仅合伙型：GP / LP）、认缴金额 | `partners[i].name / role / amount` | 首位默认 GP；按录入顺序自左向右；图上显示为「普通合伙人」「有限合伙人」 |
| 3…n | 还有其他出资人吗？ | — | 每次展示已录入表与合计金额 |
| 3…n | 该出资人是否为未在中基协备案的有限合伙企业？是则继续问它的上层出资人（名称、身份、认缴金额），上层里还有未备案有限合伙就再往上问一层 | `partners[i].unregistered` 与嵌套的 `partners` | 否；穿透层比例按该层金额单独计算 |
| 4 | 是否画基金管理人；名称；登记编码；连线标注 | `manager.name / code / label` | 是；编码以 P 开头；受托管理 |
| 5 | 是否画托管银行；名称；连线标注 | `custodian.name / label` | 是；资金托管 |
| 6 | 是否画底层项目；项目连线标注 | `project_label` | 是；项目投资 |
| 7…m | 第 j 个项目：名称、方框内补充说明、箭头旁标注 | `projects[j].name / note / label` | 首个默认「底层项目」 |
| 7…m | 还有其他项目吗？ | — | — |

规则：

- 认缴比例**不要问**，按金额自动算（两位小数，最大余数法保证合计 100.00%）。只有用户坚持给定比例、或只知道比例不知道金额时，才写 `partners[i].ratio`；用户给的比例更精确（如 0.61069%）时原样保留小数位。
- 用户直接贴出资表（名称 / 金额 / 比例）时，先据此出图，缺的基金名称、管理人、托管、项目用占位或省略，出图后再请用户补充。
- 公司型 / 契约型的出资人不写 `role`（方框里不显示括号身份）；需要灰底强调时写 `highlight: true`。
- 不画托管人 / 管理人：删掉对应键；不画项目：`projects: []`。
- 用户说「同参考稿」「示例」时直接用 `examples/amac_sample.yaml`。
- 出资人是未备案有限合伙企业时必须穿透：在该出资人下嵌套 `partners`，并写 `unregistered: true`。只写了上层出资人、没写标记，也会画出穿透层。上层出资人的比例按他们自己的金额计算，不并入基金本层。

穿透一层的写法：

```yaml
- name: 某某投资合伙企业（有限合伙）
  role: LP
  amount: 3000
  unregistered: true
  partners:
    - {name: 甲公司, role: GP, amount: 30}
    - {name: 乙公司, role: LP, amount: 2970}
```

最终数据形如：

```yaml
title: 中基协备案基金架构图
unit: 万元
fund: {name: F 基金, form: 合伙企业（有限合伙）}
partners:
  - {name: A 合伙企业, role: GP, amount: 500}
  - {name: B 合伙企业, role: LP, amount: 4500}
manager: {name: G 公司, code: P1000000, label: 受托管理}
custodian: {name: H 银行, label: 资金托管}
project_label: 项目投资
projects:
  - {name: 底层项目}
  # - {name: 甲公司, note: （拟投）, label: 持股 10%}
```

可选键：`show_ratio` / `show_amount`（默认 true）、`max_per_row`（每排出资人上限，默认 6）、`font_family`（默认宋体优先的字体栈）。

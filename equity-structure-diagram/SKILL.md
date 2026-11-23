---
name: equity-structure-diagram
description: >-
  在对话中收集标的公司、直接股东、向上穿透的控股公司和员工持股平台、下属子公司，
  生成 PE/VC 法律尽调风格的股权架构图 SVG（宋体、截至日期、持股比例与认缴金额、
  表决权不一致时单独标注、实际控制人与标的公司灰底、性质加括号放在名称下面）。
  触发词：股权架构图、股权结构图、穿透图、cap table 图、法律尽调股权、PE 股权图、VC 股权图。
---

# 股权架构图（法律尽调 → SVG）

以 [fund-structure-diagram](../fund-structure-diagram/SKILL.md) 为模板：对话里按问题清单收集，写成 YAML，再由命令行出 SVG。版式规则相同（宋体、方框按文字自适应且整体协调、性质加括号放在主体下面、向上穿透），内容换成尽调报告里的股权架构。

## 组成

```text
equity-structure-diagram/
├── scripts/equity_svg.py          # 渲染器（纯标准库）
├── scripts/render_svg.py          # YAML/JSON → SVG（可选 PNG）
├── files/questions.md             # 问答清单 + 数据格式
├── examples/sample.yaml / .svg    # 实际控制人 + 控股公司穿透 + 员工持股平台 + 子公司
└── tests/run_tests.py
```

## 版式

自上而下四层：

1. **穿透层**：控股公司、员工持股平台等的股东，画在该主体正上方。普通合伙人、实际控制人灰底。比例按这一层自己的认缴计算。
2. **直接股东**：自左向右。竖线汇入一条持股主线，竖线左侧标「持股 xx.xx%」「认缴 xx 万元」。表决权与持股不一致时加一行「表决权 xx%」；质押、代持等写在备注里。
3. **标的公司**：灰底。方框内为「名称 /（有限责任公司）/ 注册资本 xx 万元」。
4. **下属子公司**：箭头向下，旁注「持股 xx%」。多家时经分支线分开，方框同宽同高，且不小于直接股东方框。

其他规则与基金架构图一致：

- 全部文字用宋体，不回退到黑体。
- 方框 = 文字外接框 + 小内边距；直接股东（含穿透层）同宽同高；标的公司、子公司都不小于这个尺寸。
- 名称超过 2.6 英寸才均衡换行。直接股东超过 6 位自动分排。
- 画布按内容裁切。标题 14 号加粗，其下为「截至某年某月某日」。

## 工作流

```text
- [ ] 1. 按 files/questions.md 提问（材料里已有的股权表、章程、穿透说明先提取）
- [ ] 2. 写成 YAML（见 files/questions.md 或 examples/sample.yaml）
- [ ] 3. 出图，并把「提示」逐条交给用户确认
- [ ] 4. 交付 SVG 和 YAML
```

```bash
python scripts/render_svg.py equity.yaml -o equity.svg
python scripts/render_svg.py equity.yaml -o equity.svg --png equity.png --dpi 300
python scripts/render_svg.py equity.yaml --check
```

## 校验规则（`equity_svg.check`）

| 提示 | 含义 |
|------|------|
| 直接股东（或某主体的股东）持股比例合计不等于 100% | 该层比例没有配平。按金额自动算的合计一定是 100.00% |
| 需要向上穿透，但未列出其股东 | 写了 `penetrate: true` 却没有嵌套 `shareholders` |
| 认缴合计与注册资本不一致 | 直接股东认缴之和不等于标的公司注册资本 |
| 子公司未填写持股比例 | 箭头旁不会出现持股数字 |
| 既无持股比例也无认缴金额 | 连线旁没有数字 |

## 修改与测试

- 版式常量在 `scripts/equity_svg.py` 顶部。改完运行 `python tests/run_tests.py`，并重新生成 `examples/sample.svg` 目视核对。
- 同一自然人出现在多个主体下时，各画一个方框，不把同一人合并成一个节点。

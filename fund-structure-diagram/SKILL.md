---
name: fund-structure-diagram
description: >-
  在对话中按固定问题清单收集基金主体、GP/LP 认缴金额、管理人登记编码、托管银行、底层项目，
  生成中基协备案风格的基金架构图 SVG（全部宋体、黑色细线、普通合伙人与基金灰底、方框大小整体协调、
  认缴比例自动计算且合计 100%）。
  触发词：基金架构图、基金结构图、私募基金架构、备案架构图、GP/LP 出资结构图、fund structure diagram。
---

# 基金架构图（对话问答 → SVG）

## 组成

```text
fund-structure-diagram/
├── scripts/fund_svg.py                 # 渲染器（纯标准库）
├── scripts/render_svg.py               # 命令行：YAML/JSON → SVG（可选 PNG）
├── files/questions.md                  # 问答清单 + 数据格式
├── examples/amac_sample.yaml / .svg    # 复刻参考稿
├── examples/multi_project.yaml / .svg  # 7 位出资人、3 个项目、无托管
└── tests/run_tests.py
```

## 版式（复刻 matplotlib 参考稿）

- **整体协调原则**：全图方框大小要协调，不能有的很大、有的很小。出资人方框统一同宽同高，以最长的文字 + 内边距（左右 0.16、上下 0.12 英寸）为准，作为基准框；基金、管理人、托管人、项目方框都不小于基准框；中排三个方框同高；多个项目方框同宽同高。
- 超过最大宽度（出资人 2.6、基金 4.4、管理人与托管人 3.3、项目 4.4 / 多项目 3.0）才换行，且均衡换行，不会末行只剩一个字。
- 出资人超过 `max_per_row`（默认 6）时均分为多排：每排各有一条认缴主线，由中间一根竖线串起接入基金；第 2 排起把中间空隙对准这根竖线，不压方框和标注。
- 连线长度、方框间距按旁边标注文字的大小计算；画布按内容外接框裁切，四周留 0.4 英寸。1 英寸 = 72 px，字号 pt 直接作 px；SVG 带 `viewBox`，可任意缩放。
- 上排：出资人方框自左向右按录入顺序；普通合伙人灰底 `#d9d9d9`，有限合伙人白底；方框内「名称 /（普通合伙人）」或「名称 /（有限合伙人）」。数据里写 `role: GP` / `LP` 即可，图上自动显示中文全称。
- 每个方框竖线下接认缴主线；竖线左侧两行小字「认缴比例 / 金额 单位」（9 号）。
- 中排：基金主体灰底（名称 / 组织形式，11 号）；主线中点竖线接入基金顶部。
- 左侧「基金管理人 / 名称 / 登记编码：Pxxxxxxx」→ 箭头「受托管理」；右侧「托管银行 / 名称」→ 箭头「资金托管」。
- 下排：单个项目直连箭头「项目投资」；多个项目经横向分支线逐个箭头，箭头旁可标「持股 x%」。
- 标题 14 号加粗居中；线宽 1.1；箭头为实心三角（`-|>`）。
- **所有文字用宋体**：字体栈只含宋体系（SimSun / 宋体 / NSimSun / Songti SC / STSong / 思源宋体 Noto Serif CJK SC / Source Han Serif SC），不回退到黑体、雅黑等无衬线字体。Linux 上预览或导出 PNG 前先装思源宋体（`apt install fonts-noto-cjk`）。

## 工作流

```text
- [ ] 1. 按 files/questions.md 在对话中提问（用户已给的材料先提取，不重复问；比例不问，自动算）
- [ ] 2. 把答案写成 YAML（格式见 files/questions.md 或 examples/amac_sample.yaml）
- [ ] 3. 出图：SVG（需要时加 PNG）
- [ ] 4. 终端里的「提示：…」逐条转告用户确认（不阻止出图）
- [ ] 5. 交付 SVG（+ YAML 数据，便于以后改图）
```

用户说「用示例」时直接用 `examples/amac_sample.yaml`；要「随机示例」时按同一格式编造虚构名称与金额。

```bash
python scripts/render_svg.py fund.yaml -o fund.svg
python scripts/render_svg.py fund.yaml -o fund.svg --png fund.png --dpi 300   # PNG 需 cairosvg 或 rsvg-convert
python scripts/render_svg.py fund.yaml --check                               # 只校验
```

## 校验规则（`fund_svg.check`）

| 提示 | 含义 |
|------|------|
| 认缴比例合计不等于 100% | 只在手工给定比例时可能出现；按金额自动算的永远是 100.00% |
| 合伙型基金未标注 GP | 组织形式含「合伙」但没有普通合伙人 |
| 登记编码通常以 P 开头 | 私募基金管理人登记编码格式 |
| 既无认缴金额也无比例 | 该出资人竖线旁将不显示数字 |

## 修改与测试

- 版式常量集中在 `scripts/fund_svg.py` 顶部（内边距 `PAD_X/PAD_Y`、换行宽度 `*_MAX_W`、间距、灰度、线宽、字体栈）；改动后重新生成两个示例 SVG 并目视比对。
- 回归测试：`python tests/run_tests.py`（比例算法、金额格式、SVG 结构与布局分支、命令行出图与校验）。

## 常见问题

| 现象 | 处理 |
|------|------|
| 中文显示为方块 | 本机没有任何宋体：Windows / macOS 自带宋体，Linux 装 `fonts-noto-cjk`（思源宋体）。cairosvg 不支持字体回退列表，导出 PNG 时用 `rsvg-convert` 或在 YAML 写 `font_family: 'Noto Serif CJK SC'` |
| 需要插入 Word | Word 2016+ 可直接插入 SVG；旧版本用 `--png` 导出 300 dpi PNG |
| 出资人很多导致图很宽 | SVG 会自动加宽；放进文档时按页宽缩放即可 |
| 想去掉金额只留比例 | YAML 写 `show_amount: false`（`show_ratio` 同理） |

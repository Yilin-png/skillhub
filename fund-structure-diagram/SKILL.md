---
name: fund-structure-diagram
description: >-
  通过 docassamble 问答（或对话中的同一套问题）收集基金主体、GP/LP 认缴金额、管理人登记编码、
  托管银行、底层项目，生成中基协备案风格的基金架构图 SVG（宋体、黑色细线、GP 与基金灰底、
  认缴比例自动计算且合计 100%）。触发词：基金架构图、基金结构图、私募基金架构、备案架构图、
  GP/LP 出资结构图、docassamble 基金问答、fund structure diagram。
---

# 基金架构图（docassamble 问答 → SVG）

## 组成

```text
fund-structure-diagram/
├── docassamble-fundstructure/          # 可直接安装到 docassamble 的包
│   ├── setup.py
│   └── docassamble/fundstructure/
│       ├── fund_svg.py                 # 渲染器（纯标准库；问答与命令行共用，唯一实现）
│       └── data/questions/fund_structure.yml   # 问答
├── scripts/render_svg.py               # 命令行：YAML/JSON → SVG（可选 PNG）
├── files/questions.md                  # 问答清单 + 数据格式（对话模式用）
├── examples/amac_sample.yaml / .svg    # 复刻参考稿
├── examples/multi_project.yaml / .svg  # 7 位出资人、3 个项目、无托管
└── tests/run_tests.py
```

## 版式（复刻 matplotlib 参考稿）

- 画布 16×≈9 英寸（1 英寸 = 72 px，字号 pt 直接作 px），出资人多时自动加宽；SVG 带 `viewBox`，可任意缩放。
- 上排：出资人方框 2.6×1.35，自左向右按录入顺序；GP 灰底 `#d9d9d9`，LP 白底；方框内「名称 /（GP）」。
- 每个方框竖线下接认缴主线；竖线左侧两行小字「认缴比例 / 金额 单位」（9 号）。
- 中排：基金主体 4.4×1.2 灰底（名称 / 组织形式，11 号）；主线中点竖线接入基金顶部。
- 左侧「基金管理人 / 名称 / 登记编码：Pxxxxxxx」→ 箭头「受托管理」；右侧「托管银行 / 名称」→ 箭头「资金托管」。
- 下排：单个项目直连箭头「项目投资」；多个项目经横向分支线逐个箭头，箭头旁可标「持股 x%」。
- 标题 14 号加粗居中；线宽 1.1；箭头为实心三角（`-|>`）。
- 字体栈：宋体优先，无宋体时回退思源宋体 / 雅黑 / 文泉驿，避免 Linux 服务器上出现方块字。
- 名称过长自动换行并撑高同排方框；超过 6 位出资人时方框收窄到 2.2。

## 工作流

```text
- [ ] 1. 判断模式：用户有 docassamble 服务器 → 模式 A；否则 → 模式 B
- [ ] 2. 收集答案（问答清单见 files/questions.md）
- [ ] 3. 出图：SVG（需要时加 PNG）
- [ ] 4. 核对提示：比例合计、GP 是否缺失、登记编码格式
- [ ] 5. 交付 SVG（+ JSON 数据，便于以后改图）
```

### 模式 A：docassamble 问答

1. 安装包（任选其一）：
   - **Playground**：把 `fund_svg.py` 放到 Modules，把 `fund_structure.yml` 放到 Questions，直接运行；
   - **Package Management**：上传 `docassamble-fundstructure` 的 zip（`cd fund-structure-diagram && zip -r docassamble-fundstructure.zip docassamble-fundstructure`），或填 GitHub 地址 + 子目录安装。
2. 打开：`https://<服务器>/interview?i=docassamble.fundstructure:data/questions/fund_structure.yml`
3. 问答流程：基金类型/标题/单位 → 基金名称与组织形式 → 逐个出资人（合伙型选 GP/LP，其他类型不问身份）→ 管理人（登记编码不以 P 开头会拦截）→ 托管人 → 底层项目 → 结果页。
4. 结果页：内嵌预览、「下载 SVG」「下载 JSON 数据」「修改答案」（复查页可改任一屏，出资人/项目表格可编辑、删除、追加，返回后自动重新出图）。
5. 用户下载的 JSON 可用模式 B 的命令重新出图、导出 PNG 或手工微调。

### 模式 B：对话问答 + 命令行

1. 按 `files/questions.md` 的顺序在对话中提问（已知信息不重复问；比例不问，自动算）。
2. 把答案写成 YAML（格式见 `files/questions.md` 或 `examples/amac_sample.yaml`）。
3. 出图：

```bash
python scripts/render_svg.py fund.yaml -o fund.svg
python scripts/render_svg.py fund.yaml -o fund.svg --png fund.png --dpi 300   # PNG 需 cairosvg 或 rsvg-convert
python scripts/render_svg.py fund_structure.json --check                     # 只校验
```

4. 终端里的「提示：…」逐条转告用户确认（不阻止出图）。

## 校验规则（`fund_svg.check`）

| 提示 | 含义 |
|------|------|
| 认缴比例合计不等于 100% | 只在手工给定比例时可能出现；按金额自动算的永远是 100.00% |
| 合伙型基金未标注 GP | 组织形式含「合伙」但没有 GP |
| 登记编码通常以 P 开头 | 私募基金管理人登记编码格式 |
| 既无认缴金额也无比例 | 该出资人竖线旁将不显示数字 |

## 修改与测试

- 版式常量集中在 `fund_svg.py` 顶部（方框尺寸、间距、灰度、线宽、字体栈）；改动后重新生成两个示例 SVG 并目视比对。
- 问答与命令行共用同一个 `fund_svg.py`，不要复制出第二份实现。新增给问答用的函数要加进 `__all__`（docassamble 的 `modules:` 只导入 `__all__` 中的名称）。
- 回归测试：`python tests/run_tests.py`（渲染器、比例算法、问答 YAML 块结构、code 块与 Mako 模板编译、用模拟 DAList/DAFile 跑出图代码块）。测试不启动真实 docassamble 服务，首次部署后仍需在服务器上走一遍问答。

## 常见问题

| 现象 | 处理 |
|------|------|
| 中文显示为方块 | 查看器缺中文字体；浏览器/Word 打开即可。cairosvg 不支持字体回退列表，导出 PNG 时用 `rsvg-convert` 或在 YAML 写 `font_family: 'Noto Serif CJK SC'` 等本机已有字体 |
| 需要插入 Word | Word 2016+ 可直接插入 SVG；旧版本用 `--png` 导出 300 dpi PNG |
| 出资人很多导致图很宽 | SVG 会自动加宽；放进文档时按页宽缩放即可 |
| 想去掉金额只留比例 | YAML 写 `show_amount: false`（`show_ratio` 同理） |

---
title: "边界用例：冒号「：」与\"引号\""
subtitle: 'YAML 单引号'
author:
  - 张三
  - 李四
date: 2026年8月7日
abstract: >-
  折叠摘要，含 **加粗**
  与第二行。
---

# 研究背景 {#sec-bg}

正文脚注^[这是行内脚注。]，公式 $E=mc^2$，见[背景](#sec-bg)。
脱敏主体李\*与杨\*\*。

$$\int_0^1 x\,dx = \frac{1}{2}$$

::: {custom-style="Quote-Block"}
引文块内容。
:::

[术语]{custom-style="Term"}测试。

## 表格

管道表：

| 序号 | 内容 |
|------|------|
| 1    | 甲   |

: 管道表标题

导语后面紧跟表格（缺空行）：
<table><thead><tr><th>甲</th><th>乙</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>

<table class="mt-plain">
  <tr><td>无表头 A</td><td>无表头 B</td></tr>
  <tr><td>a</td><td>b</td></tr>
</table>

<table class="mt-reg">
  <thead>
    <tr><th rowspan="2">分类</th><th colspan="2">要求</th></tr>
    <tr><th>细项</th><th>内容</th></tr>
  </thead>
  <tbody>
    <tr><th rowspan="2" colspan="2">跨两行两列</th><td>x</td></tr>

    <tr><td>y &amp; z <strong>粗</strong> **公司</td></tr>
    <tr><td>嵌套</td><td colspan="2"><table><tr><td>内1</td><td>内2</td></tr></table></td></tr>
  </tbody>
</table>

```html
<table><tr><td>这是代码，不是表</td></tr></table>
```

<!-- <table><tr><td>注释里的表</td></tr></table> -->

![子目录图片](img/dot.png)

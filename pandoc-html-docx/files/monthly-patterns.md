# 植德私募基金月刊 — 三类表 HTML 模式

对齐 2024-04 final 体例。导语后接表；**表头统一灰底 `#D9D9D9`，表格通栏**（不再用粉底、不再按栏目分套列宽）。

## A. 新规表 `mt-reg`

列模型：`事项` | `具体要求`（常见 2～3 列网格；表头「具体要求」可 `colspan`）。

```html
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
      <td colspan="2">……（以下简称“引导基金”）……</td>
    </tr>
    <tr>
      <th>投资方式</th>
      <td colspan="2">采用“母基金-子基金”两层架构……</td>
    </tr>
    <tr>
      <th rowspan="2">子基金设立</th>
      <td>基金类型</td>
      <td>天使(种子)类……产业引导类……</td>
    </tr>
    <tr>
      <td>出资限制</td>
      <td>……</td>
    </tr>
    <tr>
      <th>设立流程</th>
      <td colspan="2">……</td>
    </tr>
  </tbody>
</table>
```

正文导语模板：日期 + 主体 + 文件全称 + `（以下简称“《简称》”）` + 章条结构 +「主要内容如下：」。

## B. 协会处分表 `mt-discipline`

列：`违法违规情况` | `违法违规依据` | `处分结果`。  
每个决定书先出一行 **banner**（`colspan="3"`），再跟数据行。

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
      <td>……脱敏主体与事实……</td>
      <td>……依据条文……</td>
      <td>……处分种类……</td>
    </tr>
    <tr class="banner">
      <td colspan="3">《纪律处分决定书》(中基协处分〔2024〕63号)</td>
    </tr>
    <tr>
      <td>……</td>
      <td>……</td>
      <td>……</td>
    </tr>
  </tbody>
</table>
```

## C. 地方证监局处罚表 `mt-penalty`

列：`违规行为` | `处罚依据` | `处罚结果`。  
按「### 某某证监局」分小节；每节一张表（可多行）。

```html
<table class="mt-penalty">
  <thead>
    <tr>
      <th>违规行为</th>
      <th>处罚依据</th>
      <th>处罚结果</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>……</td>
      <td>……</td>
      <td>出具警示函 / 责令改正 / 罚款……</td>
    </tr>
  </tbody>
</table>
```

## 栏目骨架（MD 标题，编号已剥）

```markdown
# 导读
### 私募基金市场新规
### 基金业协会及其他市场动态
### 基金涉诉情况及处罚案例
### 案例精选

# 私募基金市场新规
## ……通知标题……

# 基金业协会及其他市场动态
## ……

# 私募基金涉诉情况及处罚案例
## 基金业协会处分案例
## 地方证监局处罚案例
### 北京证监局
## 基金涉诉案例分析

# 特此声明
# 编委会成员
```

脱敏：机构 `**公司`；自然人 `李*` / `杨**`。分析口吻用「本刊 / 我们」。

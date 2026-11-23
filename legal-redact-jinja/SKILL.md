---
name: legal-redact-jinja
description: >-
  Use when redacting Chinese legal documents into reusable Jinja2 templates with
  private variable files, or when regenerating an agreement from templated
  parties. Prefer legal-relationship modeling: map parties/roles/instruments
  first, then nest Jinja paths so variables mirror the transaction graph.
---
# Legal redaction to Jinja2

## Goal
Turn a Chinese legal Word/text file into a reusable Jinja2 template plus a private vars file. Keep real identities off shared templates.

核心不只是「把专有名词换成占位符」，而是用**法律思维**建一张可复用的**主体关系图**，再落到嵌套 Jinja 路径：谁对谁、以什么身份、就什么标的、通过什么载体。

## Legal relationship modeling（先于命名）

在写任何 `{{ … }}` 之前，先做关系建模；命名服从关系，不服从出现顺序。

### 1. 识别交易类型与文书角色
从标题、鉴于、签约方、定义条款判断文书类型，例如：
- 股权/份额转让 → 转让方 / 受让方 / 标的公司（或标的合伙企业）
- 增资 → 原股东 / 投资方 / 标的公司
- 借款/担保 → 出借人 / 借款人 / 担保人 / 抵押物或质押标的
- 基金 LPA / 认购 → 基金 / GP / LP / 管理人 / 托管人
- 劳动/服务/采购 → 甲方（用人单位或采购方）/ 乙方（劳动者或服务方）

同一主体可兼多个角色（如 GP 同时是管理人）；**身份唯一、角色可多**，不要为每个角色复制一份公司名。

### 2. 画出主体关系图（变量图）
至少回答：
| 问题 | 落到变量 |
|------|----------|
| 谁是缔约方？角色是什么？ | `parties.<role>` 或语义角色根（`transferor` / `transferee`） |
| 标的是谁/什么？与缔约方什么关系？ | `target_company`、`target_interest`、`collateral` |
| 谁代表谁签字？ | `<party>.legal_rep` / `.signatory` |
| 账户、住所、证件归属谁？ | 嵌在所属主体下，禁止平行散落 |
| 同一实体是否多处出现？ | 全文同一路径；简称用 `.short_name`，勿另造实体 |

优先语义角色根；角色不清时再用 `parties.party_a` / `party_b`，并在 vars 注释里写明法律角色。

### 3. 嵌套原则（关系 > 扁平计数）
```yaml
# ✅ 关系清晰：账户、住所挂在主体下
transferor:
  name:
  uscc:
  address:
  legal_rep: { name:, title: }
  bank: { name:, account:, account_name: }
transferee:
  name:
  uscc:
  address:
target_company:
  name:
  short_name:
  uscc:

# ❌ 扁平计数会切断法律关系
companies.company01.name
companies.company02.name   # 看不出谁是转让方
contacts.phone01           # 看不出归属
banks.bank01.account       # 看不出户主
```

Fallback 计数器（`companies.company01` 等）**仅用于**关系图仍无法归类的边角实体；一旦能归入某角色，立即升格为语义路径，并全文替换。

### 4. 常见文书的路径骨架（按需裁剪）

**股权转让**
- `transferor.*` / `transferee.*` / `target_company.*`
- 标的份额：`transfer.interest_percent` / `transfer.price`（金额是否脱敏按 Default rules）
- 共同转让人：`transferors[i].*` 或 `transferor_a` / `transferor_b`（同一交易角色簇）

**增资 / 投资**
- `company.*`（标的）/ `investors[i].*` / `existing_shareholders[i].*`
- 投后：可挂 `investment.amount`、`investment.shares`（商务数字默认保留）

**借款 + 担保**
- `lender.*` / `borrower.*` / `guarantors[i].*`
- 担保财产：`collateral.*`；抵押人与借款人同一人时，`collateral.owner` 引用借款人路径语义，vars 中勿复制两套姓名

**基金 / LPA**
- `fund.*` / `general_partner.*` / `limited_partners[i].*` / `manager.*` / `custodian.*`
- LP 出资挂在该 LP 下：`limited_partners[i].commitment`

**通用双务合同（角色仅甲乙方）**
- `party_a.*` / `party_b.*`，example vars 顶部注释：「甲方=委托方」等

### 5. 同一性与别称
- 同一真实主体 → 全文同一 Jinja 路径。
- 「全称 / 简称 / 曾用名」：`name` / `short_name` / `former_name`，同属一个节点。
- 「甲方（以下简称「转让方」）」：模板保留角色称谓文字，变量只用一套 `transferor.*`，不要再造 `party_a.name` 并行。

## Default rules
- Redact: person names, company/partnership names, institutions, USCCs, phones, emails, detailed addresses, bank account names/numbers, project/fund/case identifiers, signature-block specifics.
- Preserve unless asked otherwise: amounts, dates, ratios, durations, statute citations, clause structure, generic legal terms (转让方/受让方/标的公司 as role words, 有限责任公司, 股份有限公司, etc.).
- Same real entity → same Jinja path across the whole document.
- Prefer semantic, **relationship-nested** paths (见上)；计数器仅作 fallback。
- Do not send source text or `*.vars.yaml` to cloud models. Use the Mac Mini local Ollama model when entity assist is needed.
- Never attach or paste the private vars file into chat; only the template and `*.vars.example.yaml`.

## Toolkit location
On the home Mac Mini:
`~/Documents/redact-trial/toolkit/`
- `rules.yaml` — reusable policy
- `redact_to_jinja.py` — source → template + vars
- `render_jinja.py` — template + vars → filled text (round-trip check)

## Steps
1. Save the source docx/txt into a working folder on the Mac Mini.
2. **先建模再跑脚本**：写出文书类型、角色清单、主体关系草图（可记在 `inventory` 备注或本地笔记）；决定语义路径骨架。
3. Run:
   `python3 ~/Documents/redact-trial/toolkit/redact_to_jinja.py --input <source.docx> --rules ~/Documents/redact-trial/toolkit/rules.yaml --out-dir <out> --stem <name>`
4. Outputs:
   - `<name>.jinja.docx` / `.jinja.txt` — shareable template
   - `<name>.vars.example.yaml` — empty schema, shareable（结构应反映关系图）
   - `<name>.vars.yaml` — PRIVATE real values, Mac Mini only
   - `<name>.inventory.json` — mapping audit
5. **关系升格**：若脚本产出大量 `company01` / 散落 `contacts`，按关系图手工或二次规则升格为语义嵌套路径，并同步改 template、vars、example、inventory。
6. Verify round-trip:
   `python3 ~/Documents/redact-trial/toolkit/render_jinja.py --template <name>.jinja.txt --vars <name>.vars.yaml --out <name>.rendered.txt`
   Rendered text should match the source for redacted spans.
7. Spot-check:
   - 残留专名、简称、USCC、账号、文档元数据（作者/标题）
   - **关系检查**：账户/电话/地址是否挂在正确主体下；同一主体是否只有一条路径；角色与鉴于条款、签署页是否一致
8. Deliver only the Jinja template and example vars to the user. Mention where private vars live. Remind that local-model assist can miss items; human review still required. Optionally attach a one-line **关系摘要**（如：转让方→标的公司←受让方；账户均挂转让方）。

## Extending rules
Edit `rules.yaml` to add role labels, extractors, preserved terms, or Jinja naming. Keep the skill generic; put matter-specific paths in the vars file, not in this recipe. New文书类型先补「路径骨架」再补抽取规则，避免只堆扁平别名。

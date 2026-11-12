---
name: legal-redact-jinja
description: >-
  Use when redacting Chinese legal documents into reusable Jinja2 templates with
  private variable files, or when regenerating an agreement from templated
  parties.
---
# Legal redaction to Jinja2

## Goal
Turn a Chinese legal Word/text file into a reusable Jinja2 template plus a private vars file. Keep real identities off shared templates.

## Default rules
- Redact: person names, company/partnership names, institutions, USCCs, phones, emails, detailed addresses, bank account names/numbers, project/fund/case identifiers, signature-block specifics.
- Preserve unless asked otherwise: amounts, dates, ratios, durations, statute citations, clause structure, generic legal terms (转让方/受让方/标的公司 as role words, 有限责任公司, 股份有限公司, etc.).
- Same real entity → same Jinja path across the whole document.
- Prefer semantic paths when roles are detectable:
  - `{{ transferor.name }}` / `.uscc` / `.address` / `.bank.name` / `.bank.account`
  - `{{ transferee.name }}` / `.uscc` / `.address`
  - `{{ target_company.name }}` / `.short_name`
- Fallback counters for leftovers: `companies.company01.name`, `people.person01.name`, `institutions…`, `contacts…`, `addresses…`, `projects…`.
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
2. Run:
   `python3 ~/Documents/redact-trial/toolkit/redact_to_jinja.py --input <source.docx> --rules ~/Documents/redact-trial/toolkit/rules.yaml --out-dir <out> --stem <name>`
3. Outputs:
   - `<name>.jinja.docx` / `.jinja.txt` — shareable template
   - `<name>.vars.example.yaml` — empty schema, shareable
   - `<name>.vars.yaml` — PRIVATE real values, Mac Mini only
   - `<name>.inventory.json` — mapping audit
4. Verify round-trip:
   `python3 ~/Documents/redact-trial/toolkit/render_jinja.py --template <name>.jinja.txt --vars <name>.vars.yaml --out <name>.rendered.txt`
   Rendered text should match the source for redacted spans.
5. Spot-check the template for leftover proper names, short brands, USCCs, account numbers, and metadata (author/title).
6. Deliver only the Jinja template and example vars to the user. Mention where private vars live. Remind that local-model assist can miss items; human review still required.

## Extending rules
Edit `rules.yaml` to add role labels, extractors, preserved terms, or Jinja naming. Keep the skill generic; put matter-specific paths in the vars file, not in this recipe.

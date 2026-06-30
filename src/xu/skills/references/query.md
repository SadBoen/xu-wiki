# query — find knowledge

> 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

CLI is purely a matcher — **it does not interpret free-text**. Agent grades query into comma-separated `--keywords`.

## Workflow

### Step 1 — Keyword grading (LLM internal, NOT a CLI call)

Grade user query → comma-separated keyword list. Always include English forms.

Example: `"现在库里面收录了几条船？"` → `--keywords "船舶,IMO,MMSI,船名,船只,舰船,货轮,ship,vessel,boat"`

### Step 2 — Search

```bash
xu query --wiki <w> --keywords "<kw1,kw2,..." [--top-k <n>] [--include-inactive]
```

Inspect `data.blocks` (uid/title/layer/text/score) + `data.total_hits` + `data.block_count`.

### Step 3 — Expand (optional)

Pick UIDs → `xu expand --wiki <w> --uids <uid1,uid2,...> [--relation-names <name,name>] [--limit <n>]`

### Step 4 — Reflection (auto-action, do NOT ask user)

```
IF data.reflection.suggest_extract_entities == true
  AND nodes --layer Entity returns empty
  THEN xu entity create --wiki <w> --title <t> [--source-page <uid>], do NOT ask user

IF data.reflection.suggest_create_list == true
  THEN xu list modify --wiki <w> --uid <uid> --members <uid,uid,...>, do NOT ask user

IF data.reflection.suggest_create_report == true
  THEN xu report create --wiki <w> --title <t> --body <md> --references <uid,uid,...>, do NOT ask user

IF new entities or lists were created
  THEN xu query-relation add --wiki <w> --from-uid <uid> --to-uid <uid> --relation-name <r>, do NOT ask user
```

Reflection fields: `suggest_extract_entities`, `suggest_create_list`, `suggest_create_report`, `hint`.

Reflection triggers are **auto-actions**, not prompts. Never pause to ask "要不要建".

### Step 5 — Wire relations

Query first, then `xu query-relation add --wiki <w> --from-uid <uid> --to-uid <uid> --relation-name <r>`.

## Counting queries (e.g. "几条船", "how many X")

- `xu query` returns PAGE blocks, **not entity counts** — do NOT use it to count
- Required flow:
  1. `xu nodes --wiki <w> --layer Entity` → `data.count`
  2. If count > 0 → answer from `data.count`
  3. If count = 0 → answer from query blocks + invoke post-query reflection to extract entities

## Stopping conditions

Conclusion reached · no more relations to expand · max_rounds exhausted

## CLI reference

```bash
# Search
xu query --wiki <w> --keywords <kw,kw,kw> [--top-k <n>] [--include-inactive]

# Expand
xu expand --wiki <w> --uids <uid,uid,...> [--relation-names <name,name>] [--limit <n>]

# Read
xu read --wiki <w> --uid <uid>
xu nodes --wiki <w> [--layer Page|List|Report|Entity] [--include-inactive]

# Relations
xu query-relation list --wiki <w> --from-uid <uid>
xu query-relation add --wiki <w> --from-uid <uid> --to-uid <uid> --relation-name <r> [--comment <c>]

# Entity / List / Report
xu entity create --wiki <w> --title <t> [--source-page <uid>] [--body <md>] [--node-path <p>]
xu entity show --wiki <w> --uid <uid>
xu entity modify --wiki <w> --uid <uid> [--title <t>] [--body <md>]

xu list create --wiki <w> --title <t> --members <uid,uid,...> [--dimension <d>] [--node-path <p>]
xu list show --wiki <w> --uid <uid>
xu list modify --wiki <w> --uid <uid> [--title <t>] [--members <uids>]

xu report create --wiki <w> --title <t> --body <md> --references <uid,uid,...> [--node-path <p>]
xu report show --wiki <w> --uid <uid>
xu report modify --wiki <w> --uid <uid> [--title <t>] [--body <md>] [--references <uids>]
```

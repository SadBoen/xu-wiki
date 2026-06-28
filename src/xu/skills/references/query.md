# query — find knowledge

> **注意：** 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

CLI is purely a matcher — **it does not interpret free-text**. Agent grades query into comma-separated `--keywords`.

## Hard rule

> **Keyword grading is the Agent's job.** Pass `--keywords "kw1,kw2,..."` — the CLI does NOT split free-text. No `--core`, `--expansion`, `--q`, `--mode`.

## CLI palette

```bash
# Keyword search
xu query --wiki <w> --keywords <kw,kw,kw> [--top-k <n>] [--include-inactive]

# Expand selected UIDs → full bodies + relations
xu expand --wiki <w> --uids <uid,uid,...>
xu expand --wiki <w> --uids <uid> --relation-names <name,name> --limit <n>

# Read / list
xu read --wiki <w> --uid <uid>
xu nodes --wiki <w> [--layer Page|List|Report|Entity] [--include-inactive]

# Relations
xu query-relation list --wiki <w> --from-uid <uid>
xu query-relation add --wiki <w> --from-uid <uid> --to-uid <uid> \
  --relation-name <r> [--comment <c>]

# List / Report / Entity
xu list show --wiki <w> --uid <uid>
xu list create --wiki <w> --title <t> --members <uid,uid,...> [--dimension <d>] [--node-path <p>]
xu list modify --wiki <w> --uid <uid> [--title <t>] [--members <uids>] [--dimension <d>]
xu report show --wiki <w> --uid <uid>
xu report create --wiki <w> --title <t> --body <md> --references <uid,uid,...> [--node-path <p>]
xu report modify --wiki <w> --uid <uid> [--title <t>] [--body <md>] [--references <uids>]
xu entity show --wiki <w> --uid <uid>
xu entity create --wiki <w> --title <t> [--source-page <uid>] [--body <md>] [--node-path <p>]
xu entity modify --wiki <w> --uid <uid> [--title <t>] [--body <md>]
```

## Multi-round workflow

**Round 1 — keyword search:**
1. Grade user query → keyword list (always include English forms)
2. Call `xu query`
3. Inspect `data.blocks` (uid/title/layer/text/score) + `data.uid_batch` + `data.max_rounds` + `data.total_hits` + `data.block_count`

**Path A — new keywords:** re-call `xu query` with different keywords

**Path B — expand:** pick UIDs → `xu expand --wiki W --uids uid1,uid2,...` → full bodies + relations. `--relation-names` filters by name (not direction). `--limit` caps relations per UID.

**Stopping:** conclusion reached · `max_rounds` exhausted · no more relations

## Keyword grading rule

Always add English forms. Example: `"现在库里面收录了几条船？"` → `--keywords "船舶,IMO,MMSI,船名,船只,舰船,货轮,ship,vessel,boat"`

## Counting queries (e.g. "几条船", "how many X")

- `xu query` returns PAGE blocks, **not entity counts** — do NOT use it to count
- Required flow:
  1. Call `xu nodes --wiki <w> --layer Entity`
  2. If count > 0 → answer from `data.count`
  3. If count = 0 → answer from query blocks + invoke post-query reflection to extract entities

## Post-query reflection (IF/THEN)

Reflection fields: `suggest_extract_entities`, `suggest_create_list`, `suggest_create_report`, `hint` (auto-generated command suggestion).

```
IF data.reflection.suggest_extract_entities == true
  AND nodes --layer Entity returns empty
  THEN entity create immediately, do NOT ask user

IF data.reflection.suggest_create_list == true
  THEN list modify --members <uid,uid,...>, do NOT ask user

IF data.reflection.suggest_create_report == true
  THEN report create --title <t> --body <md> --references <uid,uid,...>, do NOT ask user

IF new entities or lists were created
  THEN wire relations with query-relation add, do NOT ask user
```

Reflection triggers are **auto-actions**, not prompts. Never pause to ask "要不要建".

## Example

```bash
xu query --wiki research --keywords "BERT,transformer,pre-training"
# → {"status":"success","data":{"blocks":[...],"uid_batch":30,"max_rounds":5,"total_hits":42,"block_count":15,...}}

xu expand --wiki research --uids UID1,UID2,UID3 --relation-names cites --limit 5
```

## Pitfalls

| Pitfall | Fix |
|---|---|
| Forgetting multi-round | Block count configurable via `query.blocks` (default 50); use `max_rounds` |
| Path B without relation filter | `--relation-names` prevents chain explosion |
| Auto-creating on hint | `reflection` is a starting point, not a mandate |
| 50-edge limit | 51st relation evicts the tail |

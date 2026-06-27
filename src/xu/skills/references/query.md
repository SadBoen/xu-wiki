# query — find knowledge

CLI is purely a matcher — **it does not interpret free-text**. Agent grades query into comma-separated `--keywords`.

## Hard rule

> **Keyword grading is the Agent's job.** Pass `--keywords "kw1,kw2,..."` — the CLI does NOT split free-text. No `--core`, `--expansion`, `--q`, `--mode`.

## CLI palette

```bash
# Keyword search
xu query --wiki <w> --keywords <kw,kw,kw>

# Expand selected UIDs → full bodies + relations
xu expand --wiki <w> --uids <uid,uid,...>
xu expand --wiki <w> --uids <uid> --relation-names <name,name> --limit <n>

# Read / list
xu read --wiki <w> --uid <uid>
xu nodes --wiki <w> [--layer Page|List|Report] [--include-inactive]

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
3. Inspect `data.blocks` (uid/title/layer/text/score) + `data.uid_batch` (default 30) + `data.max_rounds` (default 5)

**Path A — new keywords:** re-call `xu query` with different keywords

**Path B — expand:** pick UIDs → `xu expand --wiki W --uids uid1,uid2,...` → full bodies + relations. Use `--relation-names` to filter direction. `--limit` caps per UID.

**Stopping:** conclusion reached · `max_rounds` exhausted · no more relations

## Keyword grading rule

Always add English forms. Example: `"现在库里面收录了几条船？"` → `--keywords "船舶,IMO,MMSI,船名,船只,舰船,货轮,ship,vessel,boat"`

## Post-query reflection

1. Inspect `data.reflection` — it scans existing Entity/List/Report for keyword matches and suggests whether to create new ones
2. Extend existing if found; else LLM decides to create
3. Wire relations with `query-relation add`

## Example

```bash
xu query --wiki research --keywords "BERT,transformer,pre-training"
# → {"status":"success","data":{"blocks":[...],"uid_batch":30,"max_rounds":5,...}}

xu expand --wiki research --uids UID1,UID2,UID3 --relation-names cites --limit 5
```

## Pitfalls

| Pitfall | Fix |
|---|---|
| Forgetting multi-round | Up to 50 blocks per round; use `max_rounds` |
| Path B without relation filter | `--relation-names` prevents chain explosion |
| Auto-creating on hint | `reflection` is a starting point, not a mandate |
| 50-edge limit | 51st relation evicts the tail |

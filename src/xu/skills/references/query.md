# query — find knowledge

`/xu-wiki query` finds Page/List/Report/Entity nodes by graded keywords. The CLI is purely
a matcher — **it does not interpret free-text**. The agent grades the user's
query into a comma-separated `--keywords` list before invoking.

This file is **self-contained**. Cross-cutting rules
(4-key JSON, missing-args, paths) live in `SKILL.md`; the keyword-grading
rule is restated here because it is the dominant failure mode of this SOP.

## CLI palette

```bash
# Round 1: keyword search → top N blocks
xu query --wiki <w> --keywords <kw,kw,kw>

# Path B: expand selected UIDs → full bodies + relations
xu expand --wiki <w> --uids <uid,uid,...>
xu expand --wiki <w> --uids <uid,...> --relation-names <name,name> --limit <n>

# Read individual node (Page markdown body)
xu read  --wiki <w> --uid <uid>

# List nodes in a layer (debug / discovery)
xu nodes --wiki <w> [--layer Page|List|Report] [--include-inactive]

# Follow a relation edge
xu query-relation list --wiki <w> --from-uid <uid>
xu query-relation add  --wiki <w> --from-uid <uid> --to-uid <uid> \
                            --relation-name <r> [--comment <c>]

# Follow List / Report hints
xu list   show --wiki <w> --uid <uid>
xu list   create --wiki <w> --title <t> --members <uid,uid,...> \
                    [--dimension <d>] [--node-path <p>]
xu report show --wiki <w> --uid <uid>
xu report create --wiki <w> --title <t> --body <md> \
                      --references <uid,uid,...> [--node-path <p>]
```

## Hard rule for this SOP

> **Keyword grading is the Agent's job. The CLI does NOT split a free-text
> query.** You pass a comma-separated `--keywords` list — the LLM grades
> entities (high weight) vs synonyms (low weight) before calling CLI.
> There is **no** `--core`, **no** `--expansion`, **no** `--q`, **no** `--mode`.

## Multi-round query workflow

The CLI executes searches; **you** (the agent) decide every next step.
The loop is bounded by `max_rounds` (default: 5).

**Round 1 — keyword search:**
1. Grade the user's query into a keyword list (always include English forms).
2. Call `xu query --wiki W --keywords "kw1,kw2,..."`.
3. Inspect `data.blocks` — each block has `uid / title / layer / text / score`.
4. `data.uid_batch` tells you how many UIDs to pick (default: 30).
5. `data.max_rounds` tells you the remaining rounds (default: 5).

**Path B — follow relation edges:**
- Pick UIDs from blocks → call `xu expand --wiki W --uids uid1,uid2,...`
- Each expanded node returns full `body` + `relations` list.
- `--relation-names` filters to specific directions (e.g. `--relation-names cites,references`).
- `--limit` caps relations per UID (e.g. `--limit 5`).
- Touched relations are advanced in the LRU (most-recently-used order).

**Path A — new keywords:**
- Call `xu query` again with a new keyword list.
- Any round can take either path.

**Stopping conditions:**
- You can give a conclusion → stop.
- `max_rounds` exhausted → stop.
- No more relations to follow (end of chain) → stop.

## Workflow

1. **Grade the user's query** into a comma-separated keyword list:
   - Input: the **raw user query** (full natural language, e.g. "现在库里面收录了几条船？")
   - **Always add English forms** — regardless of query language,
     include English synonyms (e.g. `ship,vessel,boat` for 船).
   - Output: `--keywords` (comma-separated)
   - Example: `"现在库里面收录了几条船？"` →
     `--keywords "船舶,IMO,MMSI,船名,船只,舰船,货轮,ship,vessel,boat"`
2. **Invoke `query`** with `--keywords`.
3. **Pick up to `data.uid_batch` UIDs** from `data.blocks` (sorted by score).
4. **Call `expand`** on those UIDs to get full bodies + relations.
5. **Decide next**: give conclusion / Path A (new keywords) / Path B (more expand).
6. **Post-query reflection** — before declaring done, run reflection:
   - Query for similar existing Entity/List/Report.
   - Extend existing if found; else LLM decides to create.
   - The CLI's `reflection` field in query response gives you starting hints.
7. **Wire relations** with `query-relation add`.

## Example — multi-round

```bash
# Round 1
xu query --wiki research --keywords "BERT,transformer,pre-training"
# → {"status":"success","data":{
#     "blocks": [...50 blocks...],
#     "uid_batch": 30,
#     "max_rounds": 5,
#     "reflection": {"existing_entities":[], "suggest_extract_entities":true,...},
#     "hints": ["pick up to 30 UIDs, call xu expand --wiki research --uids ...",
#               "Path A: re-call xu query with new keywords",
#               "Path B: expand UIDs to traverse relation edges"]
#   },...}

# Path B: pick 3 UIDs, expand with relation filter
xu expand --wiki research --uids UID1,UID2,UID3 --relation-names cites --limit 5
# → {"status":"success","data":{
#     "nodes": {
#       "UID1": {"uid":"UID1","body":"...","relations":[...]},
#       "UID2": {...},
#       "UID3": {...}
#     },"found":3,"requested":3
#   },...}
```

## Common pitfalls

- **Forgetting multi-round**: each query round gives you up to 50 blocks and
  lets you pick up to `uid_batch` UIDs. You don't need to cram everything
  into one call.
- **Path B without relation filter**: `--relation-names` prevents chain
  explosion — always narrow the direction when you know what you're looking for.
- **Auto-creating List/Report on hint**: the `reflection` field is a starting point,
  not a mandate. Always run valuation first.
- **Forgetting the 50-edge limit**: 51st relation evicts the tail.

## Cross-references

- Cross-cutting rules (4-key JSON, paths, 50-edge LRU) → `SKILL.md §Hard rules`
- The `ingest-*` CLIs (to add a hit's source if it doesn't exist) →
  `SKILL.md §SOP map` (ingest SOP)
- The `doctor-*` CLIs (to check query results are consistent) →
  `SKILL.md §SOP map` (doctor SOP)

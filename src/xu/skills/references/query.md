# query — find knowledge

`/xu-wiki query` finds L1/L2/L3 nodes by graded keywords. The CLI is purely
a matcher — **it does not interpret free-text**. The agent grades the user's
query into a comma-separated `--keywords` list before invoking.

This file is **self-contained**. Cross-cutting rules
(4-key JSON, missing-args, paths) live in `SKILL.md`; the keyword-grading
rule is restated here because it is the dominant failure mode of this SOP.

## CLI palette

```bash
# Main search
xu query --wiki <w> --keywords <kw,kw,kw> [--top-k N] [--neighbors] [--include-inactive]

# Expand specific UIDs (Path B: follow relation edges from selected hits)
xu expand --wiki <w> --uids <uid,uid,...>

# Read individual node (L1 markdown body)
xu read  --wiki <w> --uid <uid>

# List nodes in a layer (debug / discovery)
xu nodes --wiki <w> [--layer Page|List|Report] [--include-inactive]

# Follow a relation edge
xu query-relation list --wiki <w> --from-uid <uid>
xu query-relation add  --wiki <w> --from-uid <uid> --to-uid <uid> \
                            --relation-name <r> [--comment <c>]

# Follow L2 / L3 hints
xu list   show --wiki <w> --uid <uid>
xu list   create --wiki <w> --title <t> --members <uid,uid,...> \
                    [--dimension <d>] [--node-path <p>]
xu report show --wiki <w> --uid <uid>
xu report create --wiki <w> --title <t> --body <md> \
                      --references <uid,uid,...> [--node-path <p>]
```

| Flag | Required | Purpose |
|---|---|---|
| `--wiki` | yes | Wiki name or alias |
| `--keywords` | yes | Comma-separated keywords (LLM grades core vs expansion before calling) |
| `--top-k` | no | Max results; default 10 |
| `--neighbors` | no | Also include 50-edge LRU neighbors of top hits |
| `--include-inactive` | no | Include nodes marked inactive (default: active only) |

## Hard rule for this SOP

> **Keyword grading is the Agent's job. The CLI does NOT split a free-text
> query.** You pass a comma-separated `--keywords` list — the LLM grades
> entities (high weight) vs synonyms (low weight) before calling CLI.
> There is **no** `--core`, **no** `--expansion`, **no** `--q`, **no** `--mode`.
>
> - "find papers about BERT" → `xu query --wiki W --keywords "BERT,transformer,pre-training,encoder,attention,model,architecture"`
> - "现在库里面收录了几条船？" → `xu query --wiki W --keywords "船舶,IMO,MMSI,船名,船只,舰船,货轮,ship,vessel,boat"`
>
> If the user gives a free-text query and you cannot extract entities, **ask**
> for core entities before invoking.

## Workflow

1. **Grade the user's query** into a comma-separated keyword list:
   - Input: the **raw user query** (full natural language, e.g. "现在库里面收录了几条船？")
   - **Always add English forms** — regardless of query language,
     include English synonyms (e.g. `ship,vessel,boat` for 船). This is a hard
     requirement.
   - Output: `--keywords` (comma-separated, LLM grades importance before calling)
   - Example: `"现在库里面收录了几条船？"` →
     `--keywords "船舶,IMO,MMSI,船名,船只,舰船,货轮,ship,vessel,boat"`
    - Jieba plays **no role in query keyword generation** — it only runs inside
      ingest for noun extraction. At query time, you grade from the raw
      query text directly.
2. **Invoke `query`** with `--keywords` (required).
3. **Inspect the result's `data.hits`** — list of UIDs with relevance score.
4. **Read the top hits** with `read --wiki W --uid <uid>`.
5. **Post-query reflection** — the agent runs
   this before answering the user. LLM decides autonomously — no user approval needed.
   The CLI's `list_hint` / `report_hint` are **starting points, not mandates**.

   **Step 1 — Find similar Report (mandatory, before any creation decision):**
   Run a query to find existing Reports that reference the same or overlapping L1
   nodes as the current hits. If one exists → extend that Report (add the new
   hits as additional evidence or update the conclusion). Do not ask the user.

   **Step 2 — Assess Report value (only if no similar found):**
   - Do the hits + any existing `report_hint` form an evidence chain
     (premise → evidence → conclusion)?
   - Is there a conclusion emerging that future "what's the verdict on X"
     queries would benefit from being able to look up?
   - Would writing this up as a Node_Report prevent the user (or others)
     from having to re-ask the same question later?
   → If yes: call `report create` autonomously. Do not ask the user.

   **Step 3 — List valuation (SECONDARY, opportunistic):**
   Only if the hits form a natural comparable group on a missing axis and no
   similar List exists. Otherwise, by default, do not propose List after query.

   **Why query leans Report, not List**: query is "I asked a question"; the
    natural follow-up is "save the answer". A List would just bundle related
    hits without synthesizing anything. The CLI does NOT run this reflection
    and never auto-creates.
6. **If the user wants to wire edges** — `query-relation add` with
   `--from-uid` / `--to-uid` / `--relation-name`.
7. **If the user wants the neighborhood** — re-run with `--neighbors`.

## Example

```bash
xu query --wiki research --keywords "BERT,transformer,pre-training,encoder,attention" --top-k 5
# → {"status": "success", "data": {
#     "blocks": [{"uid": "...", "title": "...", "score": 24.5, "text": "..."}],
#     "total_hits": 12, "block_count": 5,
#     "reflection": {
#       "existing_entities": [...], "existing_lists": [...],
#       "existing_reports": [...],
#       "suggest_extract_entities": true,
#       "hint": "5 page(s) found – consider extracting entities..."
#     }
#   }, ...}

xu read --wiki research --uid WXYZ5678
# → {"status": "success", "data": {"uid": "...", "body": "## BERT\n..."}, ...}

xu query-relation add --wiki research \
  --from-uid WXYZ5678 --to-uid ABCD1234 \
  --relation-name cites --comment "section 3.2"
# → {"status": "success", "data": {"from": "...", "to": "...", "relation": "cites"}, ...}
```

## Common pitfalls

- **Free-text to `--keywords`** — "BERT papers" is a free-text phrase, not
  keyword list. Convert to `--keywords "BERT,papers"` (commas) or ask the user
  for the entities.
- **`--neighbors` without intent** — adding `--neighbors` returns up to
  50 edges per top hit. For a 5-hit result with full neighborhoods, this
  is 250 nodes. Use only when the user actually wants the neighborhood.
- **Auto-creating L2/L3 on hint** — the CLI's `list_hint` / `report_hint`
  are starting points, not mandates. The post-query reflection in step 5
  is the **agent's** job; the agent must always run the valuation and
  only propose if value is real, with PRIMARY bias toward Report
  LLM decides autonomously; always query for similar Report first
  and extend existing if found.
- **Forgetting the 50-edge limit** — when wiring relations, adding a
  51st evicts the tail (hard rule 3 in `SKILL.md`). Don't re-add the
  evicted one unless the user really needs it.

## Cross-references

- Cross-cutting rules (4-key JSON, paths, 50-edge LRU) → `SKILL.md §Hard rules`
- The `ingest-*` CLIs (to add a hit's source if it doesn't exist) →
  `SKILL.md §SOP map` (ingest SOP)
- The `doctor-*` CLIs (to check query results are consistent) →
  `SKILL.md §SOP map` (doctor SOP)

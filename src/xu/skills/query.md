# query — find knowledge

`/xu-wiki query` finds L1/L2/L3 nodes by graded keywords. The CLI is purely
a matcher — **it does not interpret free-text**. The agent's job is to
grade the user's natural language into `--core` (entities, weighted high)
and `--expansion` (synonyms, weighted low) before invoking (PRIN-ARCH-12,
DESIGN-ARCH-4).

This file is **self-contained** (PRIN-SKILL-1). Cross-cutting rules
(4-key JSON, missing-args, paths) live in `SKILL.md`; the keyword-grading
rule is restated here because it is the dominant failure mode of this SOP.

## CLI palette

```bash
# Main search
xu-wiki query --wiki <w> --core <kw,kw> [--expansion <kw,kw>] [--top-k N] \
              [--neighbors] [--include-inactive]

# Read individual node (L1 markdown body)
xu-wiki read  --wiki <w> --uid <uid>

# List nodes in a layer (debug / discovery)
xu-wiki nodes --wiki <w> [--layer Page|List|Report] [--include-inactive]

# Follow a relation edge
xu-wiki query-relation list --wiki <w> --from-uid <uid>
xu-wiki query-relation add  --wiki <w> --from-uid <uid> --to-uid <uid> \
                            --relation-name <r> [--comment <c>]

# Follow L2 / L3 hints
xu-wiki list   show --wiki <w> --uid <uid>
xu-wiki list   create --wiki <w> --title <t> --members <uid,uid,...> \
                    [--dimension <d>] [--node-path <p>]
xu-wiki report show --wiki <w> --uid <uid>
xu-wiki report create --wiki <w> --title <t> --body <md> \
                      --references <uid,uid,...> [--node-path <p>]
```

| Flag | Required | Purpose |
|---|---|---|
| `--wiki` | yes | Wiki name or alias |
| `--core` | yes | Comma-separated core keywords (entities, weighted high) |
| `--expansion` | no | Comma-separated expansion keywords (synonyms, weighted low) |
| `--top-k` | no | Max results; default 10 |
| `--neighbors` | no | Also include 50-edge LRU neighbors of top hits |
| `--include-inactive` | no | Include nodes marked inactive (default: active only) |

## Hard rule for this SOP (PRIN-ARCH-12 / DESIGN-ARCH-4)

> **Keyword grading is the Agent's job. The CLI does NOT split a free-text
> query.** You pass already-graded `--core` (entities, weighted high) and
> `--expansion` (synonyms, weighted low) comma lists. There is **no** `--q`,
> **no** `--mode`, **no** `--limit`.
>
> - "find papers about BERT" → `--core "BERT,transformer"` `--expansion "pre-training,encoder,attention"`
> - "show me 2025 works on RAG" → `--core "RAG,retrieval-augmented"` `--expansion "2025,generation"`
>
> If the user gives a free-text query and you cannot grade it, **ask** for
> core entities before invoking.

## Workflow

1. **Grade the user's query** into core + expansion keywords.
2. **Invoke `query`** with `--core` (required) and `--expansion` (optional).
3. **Inspect the result's `data.hits`** — list of UIDs with relevance score.
4. **Read the top hits** with `read --wiki W --uid <uid>`.
5. **If the response carries a `list_hint` or `report_hint`** — this is the
   CLI's signal that the user might want to follow up. The CLI does **not**
   act on its own (PRIN-QRY-1). Decide with the user, then call
   `list create` / `report create` if appropriate.
6. **If the user wants to wire edges** — `query-relation add` with
   `--from-uid` / `--to-uid` / `--relation-name`.
7. **If the user wants the neighborhood** — re-run with `--neighbors`.

## Example

```bash
xu-wiki query --wiki research --core "BERT,transformer" \
  --expansion "pre-training,encoder,attention" --top-k 5
# → {"status": "success", "data": {"hits": [{"uid": "...", "score": 0.92}, ...]}, ...}

xu-wiki read --wiki research --uid 2026-WXYZ5678
# → {"status": "success", "data": {"uid": "...", "body": "## BERT\n..."}, ...}

xu-wiki query-relation add --wiki research \
  --from-uid 2026-WXYZ5678 --to-uid 2026-ABCD1234 \
  --relation-name cites --comment "section 3.2"
# → {"status": "success", "data": {"from": "...", "to": "...", "relation": "cites"}, ...}
```

## Common pitfalls

- **Free-text to `--core`** — "BERT papers" is a free-text phrase, not a
  core keyword. Convert to `--core "BERT,papers"` (commas) or ask the user
  for the entities.
- **`--neighbors` without intent** — adding `--neighbors` returns up to
  50 edges per top hit. For a 5-hit result with full neighborhoods, this
  is 250 nodes. Use only when the user actually wants the neighborhood.
- **Auto-creating L2/L3 on hint** — the CLI emits `list_hint` /
  `report_hint` for the agent to decide. **Never auto-create** without
  user confirmation.
- **Forgetting the 50-edge limit** — when wiring relations, adding a
  51st evicts the tail (hard rule 3 in `SKILL.md`). Don't re-add the
  evicted one unless the user really needs it.

## Cross-references

- Cross-cutting rules (4-key JSON, paths, 50-edge LRU) → `SKILL.md §Hard rules`
- The `ingest-*` CLIs (to add a hit's source if it doesn't exist) →
  `SKILL.md §SOP map` (ingest SOP)
- The `doctor-*` CLIs (to check query results are consistent) →
  `SKILL.md §SOP map` (doctor SOP)
- Full query architecture → `design-docs/06-query.md`

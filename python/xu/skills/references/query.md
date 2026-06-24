# query — find knowledge

`/xu-wiki query` finds L1/L2/L3 nodes by related words. The CLI is purely
a matcher — **it does not interpret free-text**. Your job is to generate
related words from the user's natural language: `--core` (entities, hit
weight x3) and `--expansion` (synonyms, hit weight x1).

This file is **self-contained**. Cross-cutting rules live in `SKILL.md`.

## CLI palette

```bash
# Main search — returns top-50 snippet blocks
xu query  --wiki <w> --core <kw,kw> --expansion <kw,kw> [--top-k N] [--neighbors]

# Pull full body + relations for specific UIDs (max 20)
xu expand --wiki <w> --uids <uid,uid,...>

# Read single node
xu read   --wiki <w> --uid <uid>

# Follow/wire relations
xu query-relation list --wiki <w> --from-uid <uid>
xu query-relation add  --wiki <w> --from-uid <uid> --to-uid <uid> --relation-name <r>

# L2 / L3
xu list   show   --wiki <w> --uid <uid>
xu list   create --wiki <w> --title <t> --members <uid,uid,...> --dimension <d>
xu report show   --wiki <w> --uid <uid>
xu report create --wiki <w> --title <t> --body <md> --references <uid,uid,...>
```

## How query works (internal)

```
1. Scan node_page.body for core + expansion hits
2. Each hit -> take 50 chars before + after -> snippet
3. Snippets within 80 chars in same UID -> merged
4. Score = core_hits x 3 + expansion_hits x 1
5. Sort desc -> return top 50

Returns: [{uid, title, layer:"Page", score, snippet}]
No IDF. No Fast Pass. No LLM inside CLI.
```

## How expand works

```
xu expand --uids "A001,B002"

Returns: {A001: {body, title, layer, relations: [...]}, B002: {...}}
Max 20 UIDs. Relations include from_uid/to_uid/relation_name.
```

## The LLM-driven query loop (up to 5 cycles)

```
LOOP:
  You generate related words -> xu query -> read snippets
    |- Have conclusion? -> answer user (done)
    |- Need more, know which UIDs -> xu expand -> read body+relations
    |   |- Have conclusion? -> answer (done)
    |   |- Need more -> follow relations to new UIDs -> xu expand again
    |   |- Or: generate new related words -> back to LOOP top
    |- Not enough, don't know which UIDs -> generate new related words -> LOOP top

After 5 cycles, ask user: "expand search scope?"
```

## Hard rule for this SOP

> **YOU generate the related words. CLI does NOT split free-text.**
>
> - "find papers about BERT" -> `--core "BERT,transformer" --expansion "pretraining,encoder,attention"`
> - "库里有几条船?" -> `--core "船舶,IMO,MMSI" --expansion "船,舰船,货轮,ship,vessel,boat"`
>
> Always include English synonyms in expansion. Always >= 1 core keyword.

## Workflow

1. **Generate related words** from user's natural language
2. **`xu query`** with core + expansion
3. **Read snippets** in response. Do you have an answer?
   - If yes: answer user and stop.
   - If you know which UIDs need full body: `xu expand --uids "A,B"`
   - If you need different keywords: go back to step 1.
4. **Read body+relations** from expand response
   - Conclusion reached? Answer.
   - Relations point to relevant UIDs? `xu expand` those.
   - Need different angle? Go back to step 1.
5. **5 cycles max.** Then ask user.

## Example

```bash
xu query --wiki research --core "BERT,transformer" --expansion "pretraining,encoder,attention"
# -> returns 12 snippet blocks across 5 UIDs

# Agent reads snippets, decides A001 and B002 need full body:
xu expand --wiki research --uids "A001,B002"
# -> returns full body + relations for both

# Agent reads bodies, finds relation to C003:
xu expand --wiki research --uids "C003"
# -> has conclusion: answers user
```

## Common pitfalls

- **Free-text to --core**: "BERT papers" is a phrase. Convert to `--core "BERT,papers"`.
- **Forgetting expand**: Don't `xu read` each UID one by one. Use `xu expand` for batches.
- **Not using the loop**: One `xu query` may not be enough. Generate new keywords, try again.
- **Forgetting 50-edge limit**: Adding a 51st relation evicts the tail.

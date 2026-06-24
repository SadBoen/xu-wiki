# ingest — add content to a wiki

`/xu-wiki ingest` adds content to a wiki as **L1 Node_Page** (immutable). It
is the most complex SOP because L1 body style **must match the content
type**.

This file is **self-contained**. Cross-cutting rules live in `SKILL.md`.

## Hard rule for this SOP

> **Route by content form first; intermediate values are LLM-generated.**
>
> | User says | Route to | Agent action |
> |---|---|---|
> | PDF/DOCX/XLSX/MD/text/single image | `ingest-file` -> `ingest-context` -> `ingest-commit` | Auto-fill `--content-type` (`.xlsx/.csv`->`table`, images->`gallery`, rest->`article`); do not ask |
> | N images, one theme | `ingest-album` | Ask "vision per-photo?" before calling |
> | code block / terminal output | `ingest-commit --native` | `--content-type=article`; do not ask |
>
> After **each** step, you synthesize intermediate values **without asking the user**:
> title, raw_path, relations, content_type. The user never sees these values.
>
> **Parser chain**: MinerU (cloud) -> markitdown (local). Both fail = reject.
> No TextParser fallback — low-quality content not ingested.

## CLI palette

```bash
# Phase 1: parse
xu ingest-file    --wiki <w> --file <abs>

# Bridge: get context for decision-making (raws_tree + related_nodes)
xu ingest-context --wiki <w> --keywords "ship,design,specification"

# Phase 2: commit
xu ingest-commit  --wiki <w> --pending <f> --title <t> \
                       [--content-type article|table|gallery] \
                       [--raw-path <p>] [--relations '<json>'] \
                       [--native '<md>'] --source <abs-path> [--author <a>]

# Album single-shot
xu ingest-album   --wiki <w> --title <t> --files <abs1,abs2,...> \
                       [--raw-path <p>] [--layout table|list] [--vision] \
                       [--captions '<json>'] [--author <a>]

# Verify
xu ingest-verify  --wiki <w> --uid <uid>

# Follow-up
xu query-relation add --wiki <w> --from-uid <uid> --to-uid <uid> --relation-name <r>
xu list create --wiki <w> --title <t> --members <uid,uid,...> --dimension <d>
```

## Workflow — prose/document (PDF/DOCX/MD)

1. **Confirm wiki exists and file path is absolute.**
2. **`ingest-file`**: computes SHA256 -> Level-2 dedup check BEFORE calling parser.
   If duplicate -> warning immediately (no cost). If unique: MinerU -> markitdown chain
   -> writes temp file. Returns `{pending_file, parser, char_count}`.
3. **`ingest-context`**: you extract keywords from the parsed content, then query
   the wiki for context. Returns:
   - `raws_tree`: existing raw/ directory structure (for deciding `--raw-path`)
   - `related_nodes`: top 10 nodes matching keywords (for deciding `--relations`)
4. **You synthesize metadata** from the temp file + context:
   title, raw_path, relations — all LLM-generated, never asked of the user.
5. **`ingest-commit`**: dedup check -> split_pages (300 lines) -> per-page dedup
   -> INSERT node_page + INSERT patches v1 + UPDATE idf. Source file copied to
   `raws/<raw_path>/`. Atomic rollback on failure.
6. **`ingest-verify`** (optional): confirm DB/node/raw file integrity.
7. **Post-commit reflection**: query for similar List -> extend or create.

## Workflow — album (multiple images, one theme)

1. Verify all `--files` are absolute image paths.
2. Ask vision intent: "need AI captions per photo?" Set `--vision` if yes.
3. **`ingest-album`**: single-shot. One L1 page with table/list body.
   Includes dedup + atomic write + raws/ copy.
4. **Post-commit reflection** same as prose flow.

## Phase 1 temp file lifecycle

| Event | What happens |
|---|---|
| `ingest-file` runs | Creates temp file in system temp dir |
| `ingest-commit` succeeds | Temp file deleted immediately |
| `ingest-commit` fails | Temp file retained for debug/retry |
| Leftover after success | Bug — re-run ingest-commit to trigger deletion |

No `nodes/pending/` directory. System temp only.

## Post-commit reflection

After EVERY `ingest-commit`, run creation-value reflection:

**Step 1 — Find similar List:** query for existing Lists that overlap with
new page(s). If found -> extend (call `list create` with existing + new members).

**Step 2 — Assess List value:** did ingest add >=1 page comparable to >=1 existing
L1 on an obvious axis? Or add >=2 pages sharing a dimension? -> create List.

**Step 3 — Report valuation (SECONDARY):** only if new page contradicts or forces
re-evaluation of existing Report. Default: do NOT propose Report after ingest.

## Example

```bash
# Phase 1
xu ingest-file --wiki research --file ~/Downloads/bert.pdf
# -> {"pending_file":"/tmp/xu-pending-a1b2.json","parser":"markitdown","char_count":45230}

# Bridge
xu ingest-context --wiki research --keywords "BERT,transformer,pretraining,encoder"
# -> {"raws_tree":["papers/","models/"],"related_nodes":[{"uid":"A001","title":"Transformer Survey","match_count":3}]}

# Agent decides: raw-path="papers/bert", relations=[{"to_uid":"A001","relation_name":"属于同一主题"}]

# Phase 2
xu ingest-commit --wiki research --pending /tmp/xu-pending-a1b2.json \
  --title "BERT: Pre-training of Deep Bidirectional Transformers" \
  --raw-path "papers/bert" \
  --relations '[{"to_uid":"A001","relation_name":"属于同一主题"}]'
```

## Common pitfalls

- **Skipping ingest-context**: don't guess raw_path and relations. Always query context first.
- **Text fallback removed**: if MinerU and markitdown both fail, ingestion stops. Do not force.
- **Wrong body form**: `.xlsx` -> `table`, images -> `gallery`. Match content_type or CLI rejects.
- **L1 immutability**: never edit body after commit. Use revise for corrections.

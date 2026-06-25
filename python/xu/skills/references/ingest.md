# ingest — add content to a wiki

`xu ingest-commit` adds a page as **L1 Node_Page** (immutable) in a single
step. Dedup + split + atomic write are all handled inside the command.

This file is **self-contained**. Cross-cutting rules live in `SKILL.md`.

## Hard rule for this SOP

> Route by content type; intermediate values are LLM-generated.
>
> | Content type | Route to | Agent action |
> |---|---|---|
> | raw text / PDF / DOCX | `ingest-commit` directly | auto-fill `--content-type`; do not ask |
>
> **Title, raw_path, relations are LLM-generated.** The user never sees these
> values. After each call, synthesize the next step's metadata without asking.

## CLI palette

```bash
# Commit a page to L1 (single phase; dedup + split handled internally)
xu ingest-commit --wiki <w> --pending "<text or <!-- xu-pending ... -->" \
                    --title <t> \
                    [--content-type article|table|gallery] \
                    [--raw-path <p>] \
                    [--author <a>] \
                    [--relations '<json>']

# Build context from keywords (for deciding raw_path and relations)
xu ingest-context --wiki <w> --keywords "kw1,kw2,..."

# Follow-up: manage derived nodes
xu list-create  --wiki <w> --title <t> --members <uid,uid,...> [--dimension <d>]
xu list-extend  --wiki <w> --uid <uid> --members <uid,uid,...>
xu list-show    --wiki <w> --uid <uid>
xu report-create --wiki <w> --title <t> --body <md> --evidence <uid,uid,...> [--dimension <d>]
xu report-show  --wiki <w> --uid <uid>
xu entity-create --wiki <w> --title <t> [--body <md>] [--source-page <uid>] [--attrs '<json>']
```

## Workflow — any content

1. **Confirm wiki exists and content is available.**
2. **`ingest-context`** (optional but recommended): extract keywords from content,
   query the wiki for context. Returns:
   - `raws_tree`: existing raw/ directory structure
   - `related_nodes`: top nodes matching keywords (for deciding `--relations`)
3. **Synthesize metadata**: title, raw_path, relations — all LLM-generated.
4. **`ingest-commit`**: dedup check -> split_pages (300 lines) -> per-page dedup
   -> INSERT node_page + INSERT patches v1 + UPDATE idf. Source copied to
   `raws/<raw_path>/`. Atomic rollback on failure.
5. **Post-commit reflection**: query for similar List -> extend or create.

## Single-phase ingest detail

`--pending` accepts either:
- Raw markdown text (ingested as-is)
- `<!-- xu-pending source_hash=... -->` header + body (from prior parse)

If passing raw text, content-type is required:
- `article` (default): prose
- `table`: CSV/XLSX data
- `gallery`: image collection (body = YAML list of image metadata)

## Example

```bash
# Get context
xu ingest-context --wiki research --keywords "BERT,transformer,pretraining,encoder"
# -> {"related_nodes":[{"uid":"A001","title":"Transformer Survey","match_count":3}]}

# Agent decides: raw-path="papers/bert", relations=[{"to_uid":"A001","relation_name":"属于同一主题"}]

# Commit
xu ingest-commit --wiki research \
  --pending "# BERT: Pre-training of Deep Bidirectional Transformers\n\n..." \
  --title "BERT: Pre-training of Deep Bidirectional Transformers" \
  --content-type article \
  --raw-path "papers/bert" \
  --author agent \
  --relations '[{"to_uid":"A001","relation_name":"属于同一主题"}]'
```

## Common pitfalls

- **Skipping ingest-context**: don't guess raw_path and relations. Always query context first.
- **Wrong content-type**: `.xlsx` -> `table`, images -> `gallery`. Wrong type = body mismatch.
- **L1 immutability**: never edit body after commit. Use `update` for soft corrections.
# ingest — add content to a wiki

> **注意：** 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

Page is immutable. Body form must match content type.

## Content routing (before Phase 1)

| Source file | Default `--content-type` | Notes |
|---|---|---|
| PDF, DOCX, PPTX, MD, TXT | `article` | markitdown outputs markdown prose |
| XLSX, CSV (structured table) | `table` | markitdown outputs CSV; body must be YAML list |
| N images, one theme | `ingest-file --files <paths>` (Phase1) → `ingest-commit --content-type gallery` (Phase2) | Ask "vision per-photo?" first |
| code block / terminal output | `--native --content-type article` | Direct body, no Phase 1 |
| user explicitly says "表格" / "table" | `table` | Trust user intent |

**Rule: PDF/DOCX/PPTX/XLSX → always `article` unless user explicitly says `table`.**
markitdown outputs markdown prose, incompatible with `table`'s YAML list requirement.

## CLI palette

```bash
# Phase 1: dedup → parse → temp file
xu ingest-file --wiki <w> --file <abs> [--author <a>]

# Phase 2: temp → Page
xu ingest-commit --wiki <w> --temp <f> --title <t> \
  [--content-type article|table|gallery] [--node-path <p>] \
  --source <abs-path> [--author <a>]
# NOTE: --source required even with --native (dedup via source_hash)

# Album two-phase (ingest-album is DEPRECATED)
# Phase 1: creates temp file, copies images to raws/
xu ingest-file --wiki <w> --files <abs1,abs2,...> --title <t> \
  [--node-path <p>] [--vision] [--captions '<json>'] [--author <a>]
# Phase 2: commits to Page
xu ingest-commit --wiki <w> --temp <f> --title <t> --content-type gallery

# Phase 3
xu ingest-verify --wiki <w> --uid <uid>
xu query-relation add --wiki <w> --from-uid <uid> --to-uid <uid> \
  --relation-name <r> [--comment <c>]
xu list create --wiki <w> --title <t> --members <uid,uid,...> [--dimension <d>] [--node-path <p>]
xu report create --wiki <w> --title <t> --body <md> --references <uid,uid,...> [--node-path <p>]
```

## Workflow — prose / document

1. **Phase 1** — `ingest-file`: SHA256 dedup → parse → temp file. Returns `data.temp`
2. **Phase 2** — `ingest-commit --temp <f> --title <t>`: promotes to Page. Internal verify + atomic rollback on failure
3. **Verify raws/** — `raw_path` must be non-null (source copied to `raws/<node_path>/`). Exception: `--native` mode → null by design
4. **Phase 3** — `ingest-verify`: mandatory after every commit. Returns pass/fail for 6 checks; read-only — no rollback mechanism exists
5. **Wire relations** — query first, then `query-relation add`
6. **Reflection (IF/THEN)**:
   ```
   IF existing List overlaps → list modify --members <uid,uid,...>, do NOT ask user
   IF existing Report overlaps → report modify --references <uid,uid,...>, do NOT ask user
   IF page_count > 1 → list create with nodes --wiki <w> UID list, do NOT use created[] array
   ```

## Workflow — album

1. **Ask vision intent** — "need per-photo AI captions?" → set `--vision` if yes
2. **Phase 1** — `xu ingest-file --files <paths> --title <t> [--vision] [--captions '<json>']`: copies images to `raws/`, extracts metadata, writes temp file
3. **Phase 2** — `xu ingest-commit --temp <f> --title <t> --content-type gallery`: promotes to Page with `attrs.album.sources`
4. **`ingest-verify`**
5. **(Optional) Wire relations**

## Workflow — code / terminal output

```bash
xu ingest-commit --wiki <w> --native "<code>" --source <abs-path> --title <t>
```
Skips Phase 1. `--source` required (dedup via source_hash). **No physical source file** → `raw_path` null by design. Do NOT use `--native` for external documents.

## Phase 1 temp file lifecycle

| Event | What happens |
|---|---|
| `ingest-file` runs | Creates temp via `tempfile.gettempdir()` |
| `ingest-commit` succeeds | CLI deletes temp immediately |
| `ingest-commit` fails | Temp retained for debug/retry |
| Leftover temp after success | Bug — re-run `ingest-commit` to trigger deletion |

No `nodes/pending/` directory.

## Reorganize

```bash
xu reorganize --wiki <w> --uid <uid> --new-node-path certificates/qsa
# Atomic: nodes/ + raws/ + DB all updated
```

## Page splitting

If `data.page_count > 1`: tell user "文档较长，已自动按容量分片为 N 个 Page 节点"
- **Reflection**: if `page_count > 1`, run `xu nodes --wiki <w>` to fetch the real UID list before creating List/Report or wiring relations — do not rely on the commit JSON's `created[]` array for UIDs, as large outputs may be truncated

## Ingest verify — 6 checks (gallery skips content_hash_match)

Run: `xu ingest-verify --wiki <w> --uid <uid>`

`nodes_file_exists` · `frontmatter_complete` · `content_hash_match` (non-gallery) · `content_type_body_match` · `raw_file_exists` · `raw_path_node_path_mirror`

## Pitfalls

| Pitfall | Fix |
|---|---|
| `ingest-file` on album without `--content-type gallery` | Creates N disjoint Pages — use two-phase workflow above |
| Deciding vision for user | Always ask first |
| Splitting album into N calls | Pass all image paths in one `ingest-file --files` call |
| Editing Page body after commit | Page immutable — use `reorganize` or new ingest |
| Empty raws/ despite Page nodes | Used `--native` on document → re-ingest via `--temp` |
| Skipping `ingest-verify` | Always run after commit |
| Phase 1 temp not deleted after success | Bug — re-run `ingest-commit` with same temp |
| `BodyFormatMismatch` on PDF/DOCX | markitdown outputs markdown (article), not YAML list — use `--content-type article` |
| User says "PDF" but LLM picked `--content-type table` | PDF is always `article` unless user explicitly says otherwise |

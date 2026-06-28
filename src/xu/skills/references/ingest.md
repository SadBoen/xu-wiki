# ingest — add content to a wiki

> **注意：** 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

Page is immutable. Body form must match content type.

## Content routing (before Phase 1)

| Source file | Default `--content-type` | Notes |
|---|---|---|
| PDF, DOCX, PPTX, MD, TXT | `article` | markitdown outputs markdown prose |
| XLSX, CSV (structured table) | `table` | markitdown outputs CSV; body must be YAML list |
| N images, one theme | `ingest-album` | Ask "vision per-photo?" first |
| code block / terminal output | `--native --content-type article` | Direct body, no Phase 1 |
| user explicitly says "表格" / "table" | `table` | Trust user intent |

**Rule: PDF/DOCX/PPTX/XLSX → always `article` unless user explicitly says `table`.**
markitdown 输出的是 markdown prose，不兼容 `table` 的 YAML list 格式要求。

| User says | Route to | Agent action |
|---|---|---|
| PDF / DOCX / XLSX / MD / text / single image | `ingest-file` → `ingest-commit` → `ingest-verify` | Use default content-type from table above |
| N images, one theme | `ingest-album` | Ask "vision per-photo?" first |
| code block / terminal output | `ingest-commit --native` | Auto-fill `--content-type=article` |

## CLI palette

```bash
# Phase 1: dedup → parse → temp file
xu ingest-file --wiki <w> --file <abs>

# Phase 2: temp → Page
xu ingest-commit --wiki <w> --temp <f> --title <t> \
  [--content-type article|table|gallery] [--node-path <p>] \
  --source <abs-path> [--author <a>]
# NOTE: --source required even with --native (dedup via source_hash)

# Album single-shot
xu ingest-album --wiki <w> --title <t> --files <abs1,abs2,...> \
  [--node-path <p>] [--layout table|list] [--vision] \
  [--captions '<json>'] [--author <a>]

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
4. **Phase 3** — `ingest-verify`: mandatory after every commit. On failure: files rolled back → start from Phase 1
5. **Wire relations** — query first, then `query-relation add`
6. **Reflection** — append to existing List/Report if overlap; prefer extend over create

## Workflow — album

1. **Ask vision intent** — "need per-photo AI captions?" → set `--vision` if yes
2. **`ingest-album`** — one Page with table/list. Album theme = `--title`
3. **`ingest-verify`**
4. **(Optional) Wire relations**

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

## Ingest verify — 5 checks

`nodes_file_exists` · `frontmatter_complete` · `content_hash_match` · `content_type↔body_match` · `raw_path_checks`

## Pitfalls

| Pitfall | Fix |
|---|---|
| `ingest-file` on album | Creates N disjoint Pages — use `ingest-album` |
| Deciding vision for user | Always ask first |
| Splitting album into N calls | Use `ingest-album` once |
| Editing Page body after commit | Page immutable — use `reorganize` or new ingest |
| Empty raws/ despite Page nodes | Used `--native` on document → re-ingest via `--temp` |
| Skipping `ingest-verify` | Always run after commit |
| Phase 1 temp not deleted after success | Bug — re-run `ingest-commit` with same temp |
| `BodyFormatMismatch` on PDF/DOCX | markitdown outputs markdown (article), not YAML list — use `--content-type article` |
| User says "PDF" but LLM picked `--content-type table` | PDF is always `article` unless user explicitly says otherwise |

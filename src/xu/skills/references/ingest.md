# ingest — file to knowledge node

> 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

## Content routing

| Source file | Default --content-type | Notes |
|---|---|---|
| PDF, DOCX, PPTX, MD, TXT | `article` | markitdown outputs markdown prose |
| XLSX, CSV | `table` | markitdown outputs CSV; body must be YAML list |
| N images, one theme | Phase1 `ingest-file --files` → Phase2 `ingest-commit --content-type gallery` | Ask "vision per-photo?" first |
| code block / terminal output | `--native --content-type article` | Direct body, no Phase 1 |
| user explicitly says "表格" / "table" | `table` | Trust user intent |

**Rule: PDF/DOCX/PPTX/XLSX → always `article` unless user explicitly says `table`.**

## Workflow

### Step 1 — Phase 1: Parse

```bash
xu ingest-file --wiki <w> --file <abs> [--author <a>]
```

Creates temp file with YAML frontmatter + body. Run once per file.

**Album:** `xu ingest-file --files <abs1,abs2,...> --title <t> [--vision] [--captions '<json>'] [--author <a>]`

### Step 2 — Phase 2: Commit

```bash
xu ingest-commit --wiki <w> --temp <f> --title <t> [--content-type article|table|gallery] [--author <a>]
```

Atomic write to `nodes/pages/`. On failure, temp file is cleaned up.

**Reflection triggers (auto-action, do NOT ask user):**
- IF existing List overlaps → `xu list modify --wiki <w> --uid <uid> --members <uid,uid,...>`
- IF existing Report overlaps → `xu report modify --wiki <w> --uid <uid> --references <uid,uid,...>`

### Step 3 — Verify raws/

`raw_path` must be non-null (source copied to `raws/<node_path>/`). Exception: `--native` mode → null by design.

### Step 4 — Verify (mandatory)

```bash
xu ingest-verify --wiki <w> --uid <uid>
```

6 checks returned: `nodes_file_exists` · `frontmatter_complete` · `content_hash_match` (non-gallery) · `content_type_body_match` · `raw_file_exists` · `raw_path_node_path_mirror`.

**Gallery skips `content_hash_match`.** If a check fails: re-read the file + compare against stored hash; verify the on-disk body matches the stored `content_hash`; `raw_file_exists` failure is a warning only — node validity is determined by `.md` + `content_hash`.

## CLI reference

```bash
# Standard
xu ingest-file --wiki <w> --file <abs> [--author <a>]
xu ingest-commit --wiki <w> --temp <f> --title <t> [--content-type article|table|gallery] [--author <a>]
xu ingest-verify --wiki <w> --uid <uid>

# Native (direct body, skips Phase 1)
xu ingest-commit --wiki <w> --native "<markdown>" --source <abs-path> --title <t> [--author <a>]
```

## Safety

| Scenario | Behavior |
|---|---|
| `ingest-file` on album without `--content-type gallery` | Creates N disjoint Pages — use two-phase workflow above |
| Splitting album into N calls | Pass all image paths in one `ingest-file --files` call |
| Empty `raws/` despite Page nodes | `raw_path` is null in `--native` mode only — elsewhere indicates bug |
| Skipping `ingest-verify` | Don't — always verify after commit |
| Phase 1 temp not deleted | `ingest-commit` cleans up on success; on failure temp remains but is orphaned |

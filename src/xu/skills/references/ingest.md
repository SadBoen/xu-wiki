# ingest — file to knowledge node

> 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

## node_path: which phase owns it

`--node-path`决定节点落在 `nodes/pages/<node_path>/<slug>-<uid>.md` 和 raw 镜像落在 `raws/<node_path>/<file>`。**它只在 Phase 2 (`ingest-commit`) 生效**。

| Phase | 接收 `--node-path`? | 实际作用 |
|---|---|---|
| `ingest-file` (Phase 1) | ✅ 接受 | 仅 `safe_node_path()` 校验格式；不写盘，不传递 |
| `ingest-commit` (Phase 2) | ✅ 接受 | **真正决定** md 和 raw 目录布局 |

**结果**：传了 `ingest-file --node-path` 但 `ingest-commit` 漏传，节点会落到 `nodes/pages/` 根目录。**`ingest-file --node-path` 是 no-op**——只在 Phase 2 给才有效。

**OMISSION RULE**: 任何有"船名/项目/分类"语义的 source，Phase 2 必须传 `--node-path`（不传就建孤儿节点）。**单文件 commit 永远是 `xu ingest-commit --wiki <w> --temp <f> --title <t> --node-path <p> ...`** 四件套。

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
xu ingest-commit --wiki <w> --temp <f> --title <t> --node-path <p> \
                  [--content-type article|table|gallery] [--author <a>] \
                  [--relations '<json>']
```

**`--node-path <p>` 强烈建议必传**（参见顶部 "node_path: which phase owns it"）。不传则节点落到 `nodes/pages/` 根，raw 落到 `raws/` 根——是孤儿节点。

**`--relations '<json>'` 可选**：JSON array of `{to, relation_name, comment?}`。**强烈建议在创建后立刻挂反向链到已有 Entity**（`describes` 关系），否则 Page 是孤立的、`xu query` 不会从 Entity 路由回 Page。**反例**：创建完船舶规格后立刻 `xu query --keywords "<船名>"` 找 Entity UID，再 `xu query-relation add --from-uid <new> --to-uid <entity> --relation-name describes`。

Atomic write to `nodes/pages/`. On failure, temp file is cleaned up.

**Reflection triggers (auto-action, do NOT ask user):**
- IF existing List overlaps → `xu list modify --wiki <w> --uid <uid> --members <uid,uid,...>`
- IF existing Report overlaps → `xu report modify --wiki <w> --uid <uid> --references <uid,uid,...>`
- IF existing Entity matches the new page's subject (e.g. 同一艘船、同一份合同) → `xu query-relation add --from-uid <new-page-uid> --to-uid <entity-uid> --relation-name describes`

### Step 3 — Verify raws/

`raw_path` must be non-null (source copied to `raws/<node_path>/`). Exception: `--native` mode → null by design.

### Step 4 — Verify (mandatory)

```bash
xu ingest-verify --wiki <w> --uid <uid>
```

6 checks returned: `nodes_file_exists` · `frontmatter_complete` · `content_hash_match` (non-gallery) · `content_type_body_match` · `raw_file_exists` · `raw_path_node_path_mirror`.

**Check severity table** (read `data.checks[*].status` field — `status` is the source of truth, not the count):

| Check | `pass` | `warning` | `skip` | `fail` |
|---|---|---|---|---|
| `nodes_file_exists` | OK | n/a | n/a | 节点文件未找到（hard fail） |
| `frontmatter_complete` | OK | n/a | n/a | YAML 缺关键字段（hard fail） |
| `content_hash_match` | OK | n/a | n/a | body hash 不匹配——可能有人手动改了 .md |
| `content_type_body_match` | OK | n/a | n/a | body 格式和 content_type 不一致 |
| `raw_file_exists` | OK | raw 不存在但 node 有效 | n/a | n/a（**仅 warning**） |
| `raw_path_node_path_mirror` | raw 落在 `raws/<node_path>/` 下 | n/a | **`node_path` 为空时跳过**——**不是 OK，是"未分类"信号** | raw 路径和 node_path 不一致 |

**`raw_path_node_path_mirror: skip` 是 post-mortem 信号，不是绿色灯**。它意味着节点建在 `nodes/pages/` 根目录（孤儿节点）。如果 verify 报 skip，**必须立即**：

1. 删节点：`xu delete-node --wiki <w> --uid <uid> --force`
2. 重跑 Phase 1：`xu ingest-file --wiki <w> --file <abs>`
3. 重跑 Phase 2 + 传 `--node-path`：`xu ingest-commit --wiki <w> --temp <f> --title <t> --node-path <p> ...`
4. 重跑 verify：`xu ingest-verify --wiki <w> --uid <new-uid>`

**Gallery skips `content_hash_match`.** If a check fails: re-read the file + compare against stored hash; verify the on-disk body matches the stored `content_hash`; `raw_file_exists` failure is a warning only — node validity is determined by `.md` + `content_hash`.

**Alternative for batch verification**: after all ingests, run `xu doctor-node-path-organization` (catches every page with empty or non-normalized `node_path` in one pass).

## CLI reference

```bash
# Standard (single-file commit — four-arg set, --node-path is required for sourced files)
xu ingest-file --wiki <w> --file <abs> [--author <a>]
xu ingest-commit --wiki <w> --temp <f> --title <t> --node-path <p> \
                  [--content-type article|table|gallery] [--author <a>] \
                  [--relations '<json>']
xu ingest-verify --wiki <w> --uid <uid>

# Album (N images, one theme → gallery)
xu ingest-file --wiki <w> --files <abs1,abs2,...> --title <t> [--vision] [--captions '<json>'] [--author <a>]
xu ingest-commit --wiki <w> --temp <f> --title <t> --node-path <p> --content-type gallery [--author <a>]

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
| `ingest-commit` without `--node-path` on a sourced file | **Orphan node** at `nodes/pages/` root; `ingest-verify` reports `raw_path_node_path_mirror: skip`. Always pass `--node-path` for any source with a ship/project/category semantic. Recover via the 4-step recipe in [Step 4](#step-4-verify-mandatory). |

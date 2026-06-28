# doctor — diagnose wiki health

> 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

## Workflow

### Step 1 — Full diagnostic

```bash
xu doctor --wiki <w>
```

Returns a list of findings, each with `kind`, `fixable`, and optional `fix` command.

### Step 2 — Review findings

IF finding kind is one of the following, apply the corresponding fix below:

**`doctor-l1-immutable` — Page body never modified after commit**
- `--fix` is a no-op (returns `fixable: False`); manual review required

**`doctor-node-path-organization` — Page missing `node_path` or path contains uppercase**
- `fixable: False`; run `xu reorganize` manually after reviewing pages

**`doctor-orphan-entity` / `doctor-orphan-list` / `doctor-orphan-report` — Entity/List/Report with no incoming relations**
- `--fix` adds self-relation to unlink from orphan pool

**`doctor-dangling-relation` — Relation points to deleted UID**
- `--fix` removes the dangling reference from the relation table

**`doctor-files-missing` — Page or raw file missing from disk**
- `fixable: False`; requires manual recovery

### Step 3 — Fix (if fixable)

```bash
# Per-finding
xu doctor --wiki <w> --fix <kind>

# Granular: rebuild relation positions (all three granularity values behave identically — only renumber relations, nothing is rebuilt or destroyed)
xu rebuild --wiki <w> --granularity keep-l1

# Granular: delete specific node
xu delete-node --wiki <w> --uid <uid> --force

# Granular: fix orphan reports
xu doctor-report-evidence --wiki <w> --fix
```

### Step 4 — Verify

```bash
xu doctor --wiki <w>
```

All findings should be resolved.

## CLI reference

```bash
# Diagnose
xu doctor --wiki <w>
xu doctor --wiki <w> --fix <kind>

# Per-check
xu doctor-files --wiki <w>
xu doctor-entity-evidence --wiki <w> [--fix]
xu doctor-list-evidence --wiki <w> [--fix]
xu doctor-report-evidence --wiki <w> [--fix]

# Node management
xu delete-node --wiki <w> --uid <uid> --force
xu nodes --wiki <w> [--layer Page|List|Report|Entity] [--include-inactive]
xu reorganize --wiki <w> --uid <uid> --new-node-path <p>

# Rebuild
xu rebuild --wiki <w> [--granularity keep-l1|keep-l1-l2|full]
```

## Safety

| Command | Effect |
|---|---|
| `doctor` without `--fix` | Read-only diagnostic |
| `doctor --fix doctor-dangling-relation` | Removes dangling refs |
| `doctor --fix doctor-orphan-*` | Adds self-relation |
| `delete-node --force` | Removes node + its outgoing relations |
| `rebuild --granularity keep-l1` | Renumbers relations only; safe |

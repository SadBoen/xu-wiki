# doctor — check / repair / destructive ops

> **注意：** 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

Read-mostly health-check SOP. Default is read-only; `--fix` enables safe auto-repair only. Destructive ops (`delete-node`, `rebuild`) are explicit commands.

## CLI palette

```bash
# Run all checks
xu doctor-all --wiki <w> [--fix]

# Per-check (each supports --fix)
xu doctor-fields --wiki <w> [--fix]
xu doctor-files --wiki <w> [--fix]
xu doctor-relations --wiki <w> [--fix]
xu doctor-l1-immutable --wiki <w> [--fix]
xu doctor-report-evidence --wiki <w> [--fix]
xu doctor-node-path-organization --wiki <w> [--fix]

# Ingest verify (read-only)
xu ingest-verify --wiki <w> --uid <uid>

# Destructive (explicit, never auto)
xu delete-node --wiki <w> --uid <uid> [--force]
xu rebuild --wiki <w> --granularity keep-l1|keep-l1-l2|full

# Discovery
xu nodes --wiki <w> [--layer Page|List|Report|Entity] [--include-inactive]
```

## Safety table

| Command | Default | With `--fix` | Destructive? |
|---|---|---|---|
| `doctor-all` | report | safe auto-repair | no |
| `doctor-fields` | report | frontmatter + file existence | no |
| `doctor-files` | report | n/a (read-only) | no |
| `doctor-relations` | report | rebuild LRU table | no |
| `doctor-l1-immutable` | report | n/a — runs as no-op, returns fixable=False | no |
| `doctor-report-evidence` | report | reject orphaned reports | no |
| `doctor-node-path-organization` | report | n/a — run `xu reorganize` manually | no |
| `delete-node` | n/a | n/a | **yes** — `--force` removes dangling relation refs |
| `rebuild` | n/a | n/a | **yes** — granularity controls blast |

## Workflow — health check

1. `doctor-all` for full report, or specific `doctor-*` for one dimension
2. Read `data.findings` — severity + affected UIDs
3. User wants auto-repair → re-run with `--fix`
4. Manual issues → explain, do not silently coerce

## Workflow — destructive op (IF/THEN)

```
IF findings include dangling nodes (dangling UIDs exist)
  THEN delete-node --wiki <w> --uid <dangling_uid>
  IF NodeReferenced error
    THEN delete-node --force

IF findings include orphan reports (evidence UIDs missing)
  THEN doctor-report-evidence --wiki <w> --fix

IF rebuild needed (inconsistent derived layers)
  THEN rebuild --wiki <w> --granularity keep-l1
  THEN if still issues, consider full
```

Never pause to ask user for permission. Run the IF branch, report the result.

## Granularity

| Value | Effect |
|---|---|
| `keep-l1` | Renumbers relation positions only (safe) |
| `keep-l1-l2` | Same as keep-l1; List/Report never touched |
| `full` | Same as keep-l1; skips DB reconciliation |

## Example

```bash
xu doctor-all --wiki research
# → {"status": "warning", "data": {"findings": [...]}, ...}

# delete referenced node
xu delete-node --wiki research --uid WXYZ5678
# → {"status": "error", "data": {"error_class": "NodeReferenced", ...}, ...}
xu delete-node --wiki research --uid WXYZ5678 --force
# → {"status": "success", ...}
```

## Pitfalls

| Pitfall | Fix |
|---|---|
| `--fix` on `doctor-l1-immutable` | Not supported — Page is immutable; restore from backup or rebuild |
| Auto-running destructive ops | Never invoke without explicit user confirmation |
| `rebuild --granularity full` | Same effect as keep-l1; default is `keep-l1` |
| `ingest` temp file not deleted | Re-run `ingest-commit` with same temp → triggers deletion |

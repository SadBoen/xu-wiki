# doctor — check / repair / destructive ops

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
xu rebuild --wiki <w> --granularity keep-page|keep-page-list|full

# Discovery
xu nodes --wiki <w> [--layer Page|List|Report] [--include-inactive]
```

## Safety table

| Command | Default | With `--fix` | Destructive? |
|---|---|---|---|
| `doctor-all` | report | safe auto-repair | no |
| `doctor-fields` | report | frontmatter + file existence | no |
| `doctor-files` | report | n/a (read-only) | no |
| `doctor-relations` | report | rebuild LRU table | no |
| `doctor-l1-immutable` | report | n/a (always refuses) | no |
| `doctor-report-evidence` | report | reject orphaned reports | no |
| `doctor-node-path-organization` | report | calls `reorganize` | no |
| `delete-node` | n/a | n/a | **yes** — `--force` ignores refs |
| `rebuild` | n/a | n/a | **yes** — granularity controls blast |

## Workflow — health check

1. `doctor-all` for full report, or specific `doctor-*` for one dimension
2. Read `data.findings` — severity + affected UIDs
3. User wants auto-repair → re-run with `--fix`
4. Manual issues → explain, do not silently coerce

## Workflow — destructive op

1. **Verify intent explicitly** — state wiki + UIDs, ask confirmation
2. **`delete-node`**: run without `--force` first (refuses if referenced); if user accepts orphans → `--force`
3. **`rebuild`**: `keep-page` safest (rebuilds List/Report from Page only); `full` is destructive for derived layers

## Granularity

| Value | Destroys |
|---|---|
| `keep-page` | List/Report rebuilt from Page (safe) |
| `keep-page-list` | Report only rebuilt |
| `full` | Everything from raw markdown — destructive |

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
| `rebuild --granularity full` | Destructive for List/Report edits; default is `keep-page` |
| `ingest` temp file not deleted | Re-run `ingest-commit` with same temp → triggers deletion |

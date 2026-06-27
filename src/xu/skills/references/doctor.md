# doctor — check / repair / destructive ops

`/xu-wiki doctor` is the **read-mostly** health-check SOP, plus the only
legitimate way to perform destructive operations (delete, rebuild) on a
wiki. Default is read-only; `--fix` is opt-in and only enables **safe**
auto-repair. Truly destructive ops (`delete-node --force`, `rebuild`) are
explicit commands, not flags on a read operation.

This file is **self-contained**. Cross-cutting rules
(4-key JSON, missing-args) live in `SKILL.md`; the safety boundaries
specific to doctor are stated here.

## CLI palette

```bash
# Run all checks (default: report only)
xu doctor-all --wiki <w> [--fix]

# Per-check subcommands (each supports --fix for safe auto-repair)
xu doctor-fields         --wiki <w> [--fix]   # frontmatter completeness + file existence
xu doctor-files          --wiki <w> [--fix]   # raws/ / nodes/ filesystem consistency
xu doctor-relations      --wiki <w> [--fix]   # 50-edge LRU invariants
xu doctor-l1-immutable   --wiki <w> [--fix]   # L1 markdown body never modified
xu doctor-report-evidence --wiki <w> [--fix]  # L3 reports have ≥ 1 evidence ref
xu doctor-node-path-organization --wiki <w> [--fix]  # root-level pages + suggested paths

# Node integrity verification (ingest module)
xu ingest-verify --wiki <w> --uid <uid>        # read-only post-commit integrity check

# Destructive ops (NEVER auto-invoked — explicit command, not a flag)
xu delete-node --wiki <w> --uid <uid> [--force]
xu rebuild    --wiki <w> --granularity keep-l1|keep-l1-l2|full

# Discovery (used to look up dangling UIDs)
xu nodes --wiki <w> [--layer Page|List|Report] [--include-inactive]
```

| Command | Default | With `--fix` | Truly destructive? |
|---|---|---|---|
| `doctor-all` | read-only report | safe auto-repair enabled | no |
| `doctor-fields` | read-only | frontmatter completeness + file existence | no |
| `doctor-files` | read-only | rename / link missing files | no |
| `doctor-relations` | read-only | rebuild LRU table from edges | no |
| `doctor-l1-immutable` | read-only | n/a (always refuses) | no |
| `doctor-report-evidence` | read-only | reject reports w/o evidence | no |

| `doctor-node-path-organization` | read-only | calls `xu reorganize` per page | no |
| `delete-node` | n/a (always destructive) | n/a | **yes** — `--force` ignores references |
| `rebuild` | n/a (always destructive) | n/a | **yes** — granularity controls blast radius |

## Hard rule for this SOP

> **Within doctor, match user natural-language intent to the right CLI.**
> The doctor SOP is the only place where destructive ops live. Examples:
>
> - "delete X node" → `delete-node --wiki W --uid X` (with `--force` only
>   if X is referenced and the user explicitly accepts the orphan refs).
> - "full check" → `doctor-all --wiki W`.
> - "rebuild from scratch" → `rebuild --wiki W --granularity full`.
> - "move X to Y directory" → `xu reorganize --wiki W --uid X --new-node-path Y`
>   (atomic: nodes/ + raws/ + DB all updated in one transaction).
>
> Default for any destructive op is to ask the user to confirm and to
> name the wiki + the affected UIDs.

## Workflow — health check

1. **Verify wiki** (rule 8 / rule 9 in `SKILL.md`).
2. **Run `doctor-all`** for a full report, or a specific `doctor-*` for
   one dimension. Default: read-only.
3. **Read the report** — `data.findings` lists each issue with severity
   and the affected UIDs.
4. **If the user wants auto-repair** — re-run with `--fix`. Only the
   safe auto-repairable items are touched; anything else is listed as
   "manual intervention needed" and **not** changed.
5. **For issues that need manual action** — explain to the user, do not
   silently coerce.

## Workflow — destructive op (delete or rebuild)

1. **Verify the user's intent explicitly.** "delete X" is destructive
   even if X is unreferenced. State the affected UID(s) and the wiki
   and ask for confirmation.
2. **For `delete-node`**:
   - Run **without** `--force` first; the CLI refuses if X is referenced
     by L2/L3.
   - If the user accepts the orphan references, re-run with `--force`.
3. **For `rebuild`**:
   - Pick the granularity. `keep-l1` is the safest (only rebuilds L2/L3
     from L1). `keep-l1-l2` rebuilds L3 only. `full` rebuilds everything
     from raw markdown — **destructive** for L2/L3 edits.
   - The CLI requires a confirmation flag (check current CLI; ask the
     user if unsure).

## Example — health check

```bash
xu doctor-all --wiki research
# → {"status": "warning", "data": {"findings": [
#      {"check": "fields", "severity": "warn", "uid": "...", "msg": "..."}
#    ]}, ...}

xu doctor-relations --wiki research --fix
# → {"status": "success", "data": {"repaired": 3, "skipped": 0}, ...}
```

## Example — destructive

```bash
# Step 1: dry check (no --force)
xu delete-node --wiki research --uid WXYZ5678
# → {"status": "error", "data": {"error_class": "ReferencedByList", "refs": ["..."]}, ...}

# Step 2: user accepts orphan refs → re-run with --force
xu delete-node --wiki research --uid WXYZ5678 --force
# → {"status": "success", "data": {"uid": "...", "deleted": true}, ...}
```

## Common pitfalls

- **`--fix` on a check that doesn't support it** — `doctor-l1-immutable`
  never auto-repairs (L1 is immutable; if it's modified, the only fix is
  to restore from a backup or rebuild). The CLI returns "fix not supported
  for this check".
- **Auto-running destructive ops** — never invoke `delete-node` or
  `rebuild` without explicit user confirmation, even if the doctor report
  lists them as candidates.
- **Phase 1 temp file not deleted after commit** — if `ingest-commit` succeeded
  but the temp file at `data.temp` still exists on disk, that is a bug.
  Re-running `ingest-commit` with the same temp file (it will be rejected as
  duplicate by Level-2 dedup) will trigger the deletion. There is no `nodes/pending/`
  directory.
- **Rebuilding L1 from raw markdown** — `rebuild --granularity full` is
  destructive for any L2/L3 work done after the L1 ingest. Default
  granularity is `keep-l1`; only escalate if the user really wants to
  throw away derived layers.

## Cross-references

- Cross-cutting rules (4-key JSON, paths) → `SKILL.md §Hard rules`
- The 50-edge LRU semantics → `SKILL.md §Architecture in 30 seconds`
- The `ingest-*` CLIs (to re-ingest after a delete) → `SKILL.md §SOP map` (ingest SOP)
- The `register` / `unregister` CLIs (to recover a wiki from doctor
  reports) → `SKILL.md §SOP map` (config SOP)

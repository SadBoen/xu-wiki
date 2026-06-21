---
name: "xu-wiki"
description: "Operate xu-wiki three-layer knowledge base via 5 SOPs (create/ingest/query/doctor/config) on a deterministic CLI. Manage 50-edge LRU, Node_List (L2), Node_Report (L3)."
---

# xu-wiki

xu-wiki is a **relation-driven three-layer knowledge base** designed for AI
agents. It exposes a deterministic offline-first CLI; this skill is the
authoritative invocation guide for the agent side.

## Naming conventions

Three distinct names — DO NOT mix them up:

| Name | What it is | Where you see it |
|---|---|---|
| `xu-wiki` | The skill bundle / project name | Skill frontmatter |
| `/xu-wiki` | Slash command | Enters the matching SOP |
| `xu` | The CLI binary | All `xu <verb>` shell invocations |

The slash command `/xu-wiki` is the agent's UX entry into a SOP and is
not a CLI invocation.

## SOP map

A slash command `/xu-wiki <verb>` enters a SOP — **not** a CLI subcommand.
Each SOP is self-contained in its own file (`*.md` below); the agent says
"see SKILL.md §SOP map" rather than linking directly.

| SOP | Intent | CLI commands it calls | File |
|---|---|---|---|
| `/xu-wiki create` | build a new empty wiki at a path (raws/, nodes/{page,list,report}/, .xu/) | `create` (+ optional `wikis` to verify) | `create.md` |
| `/xu-wiki ingest` | add content (PDF / DOCX / PPTX / MD / image / album) as immutable L1 Node_Page. Two-phase prose/doc flow (`ingest-file` → `ingest-commit`); single-shot album flow (`ingest-album`). Body style must match content type. **Post-commit reflection**: query for similar List → extend or create new; LLM decides autonomously | `ingest-file` → `ingest-commit`; `ingest-album`; `ingest-verify`; `reorganize` (if user不满意路径); optional `query-relation add` | `ingest.md` |
| `/xu-wiki query` | find knowledge with elastic slicing, IDF, Fast Pass; read nodes; follow L2/L3 hints. **Post-query reflection**: query for similar Report → extend or create new; LLM decides autonomously | `query`; then `read`, `list show`, or `report show` per hint | `query.md` |
| `/xu-wiki doctor` | read-only consistency checks on fields / files / relations / L1 immutability / Report evidence / IDF; apply `--fix` for safe repairs; rebuild derived layers | `doctor-all`; per-check subcommands; `--fix`; `delete-node`; `rebuild`; `nodes` (dangling lookup) | `doctor.md` |
| `/xu-wiki config` | manage wiki aliases, register/unregister directories, set MinerU API key, inspect wikis, **and uninstall xu-wiki** | `wikis`; `alias set/unset/show`; `register` / `unregister`; `config set-mineru-key / show / path`; `skills path / list`; **`uninstall`** (always dry-run first, then `--execute` after user confirms) | `config.md` |

## Architecture in 30 seconds

- **L1 Node_Page** — immutable markdown facts. SHA256-dedup. UID never reused.
- **L2 Node_List** — `.md` comparison/aggregation in `nodes/list/`. Members in frontmatter.
- **L3 Node_Report** — `.md` reasoning in `nodes/report/`. **Requires ≥ 1 evidence ref** (else rejected).
- **Relations** — exactly **50 edges per node** (LRU, head=touch, tail=evict). No category, no score.
- **FS** holds raw material pool (`raws/`), L1 markdown (`nodes/page/`), L2 (`nodes/list/`), L3 (`nodes/report/`).
- **CLI is offline-first.** MinerU is an optional parser in the fallback chain.

## Hard rules the agent MUST respect

0. **You are the only legitimate caller of `xu`.** User never touches CLI directly.
   Translate intent → CLI calls. Parse 4-key JSON → natural language reply. On pushback: re-interpret via SOP, don't ask user to retype.

0a. **Uninstall = 2 surfaces.** Skill bundle → agent removes its skill dir. Program + config → `xu uninstall --execute`. **Wiki data NEVER deleted** (no flag, no option, no branch). See doctor.md §Uninstall.

0b. **No install step in this bundle.** xu-wiki is pre-installed when this skill loads. No `xu install` or `/xu-wiki install` command.

1. **Never edit L1 markdown body** — immutable. UIDs retired on delete, never reused.
2. **Report needs ≥1 evidence ref** at create-time. Empty evidence rejected.
3. **50 edges max per node** (LRU: 51st evicts tail). Do not re-add evicted edge unless needed.
4. **Offline-first** — only MinerU parse hits network. On failure: markitdown → text → image silently.
5. **No secret in code or git** — MinerU key in `~/.xu-wiki/config.yaml` or `MINERU_API_KEY` env.
6. **All commands return 4-key JSON** — `{status, data, message, hints}`. `hints` is for agent, not user.
7. **Deterministic output** — no timestamps, random IDs, or locale in response. Use `--wiki`.
8. **Missing required args: ask, don't guess.** Never auto-pick names or paths.
9. **Absolute paths only** (`~` is fine). Never `./foo` (breaks idempotency + symlink guard).
10. **Slash command = SOP entry, not CLI subcommand.** `/xu-wiki <verb>` → enter SOP → pick CLI(s). See SOP map above.
11. **Within a SOP: match intent to CLI.** Do NOT coerce to an unrelated CLI.
    - doctor + "move X to Y" → `xu reorganize --wiki W --uid X --new-node-path Y` (atomic; never delete+re-ingest)
12. **Asymmetric creation bias:** After ingest → bias List; after query → bias Report. LLM decides autonomously, no user approval needed. Before creating: query to find similar existing List/Report. If similar found → extend the existing one instead of creating a new one.
13. **Phase 1 temp file:** Written to system temp, deleted on success, retained on failure. No `nodes/pending/`.
14. **Forbidden: `execute_code` for xu CLI.** stderr corrupts JSON output. Use bash/terminal tool.

## Quick safety checklist

Before declaring an ingest done, run through this every time:

1. **`raws/<node_path>/` has the source file copy?** — if empty but `nodes/page/`
   has content, the copy was bypassed. Stop and re-investigate.
2. **Phase 1 temp file was deleted on success?** — if `ingest-commit` succeeded but
   the temp file still exists, that is a bug. Re-run `ingest-commit` (it will
   reject a duplicate commit) to confirm deletion.
3. **`data.created[].raw_path` is non-null?** — if null, explains why raws/ is
   empty. Null is expected only for `--native` (agent-synthesized text).
4. **`xu doctor-all --wiki W` returns zero issues?** — do not proceed to the next
   batch if doctor reports pending leftovers or other ingest anomalies.

**Any NO answer means: stop, investigate, fix before continuing.**

## Reading the response

Every command prints one JSON object to stdout. Read `data.*` for facts and
`hints` for the next step. Examples:

```json
{"status": "success", "data": {"uid": "ABCD1234", "title": "BERT"},
 "message": "read complete", "hints": ["query-relation list --from-uid ..."]}
```

On a `list_hint` / `report_hint` field, the agent runs the post-query
reflection (see hard rule 12): query for similar List/Report first;
extend existing if found; otherwise LLM decides autonomously (no user approval needed).
Hints are starting points, not mandates.

## Quick start for the agent

```bash
# 1. create a wiki
xu create --name research --path /abs/path/to/wiki

# 2. ingest L1 — two phases; verify raws/ has copy after
xu ingest-file   --wiki research --file /abs/path/to/source.pdf   # → {"data":{"pending":"/tmp/...-pre.md",...}}
# Agent reviews the temp file content, then:
xu ingest-commit --wiki research --pending /tmp/...-pre.md --title "BERT" --content-type article # → L1 entry

# 3. query (Agent grades the keywords into core vs expansion)
xu query --wiki research --core "transformer,attention" \
  --expansion "self-attention,encoder" --top-k 5

# 4. wire relations
xu query-relation add --wiki research \
  --from-uid <uid-A> --to-uid <uid-B> --relation-name cites --comment "section 3.2"

# 5. L2 / L3
xu list   create --wiki research --title "top 10 models" \
  --members <uid1>,<uid2>,... --dimension "by-parameter-count"
xu report create --wiki research --title "transformer survey" \
  --references <uid1>,<uid2>,<uid3> --body "## findings ..."

# 6. health
xu doctor-all --wiki research
xu rebuild    --wiki research --granularity keep-l1
```

## Error catalog

Every `error_class` the CLI may return. Append new entries using this format:

```
## <error_class>
- Trigger: <what user/system action causes it>
- Where: <which CLI subcommand / SOP>
- Response shape: <what `data` keys accompany it>
- Fix: <how the user / agent should respond>
```

Cross-reference: JSON response shape (`status` / `data` / `message` / `hints`) → `SKILL.md §Reading the response`

### CreationRefused
- Trigger: LLM decided not to create an L2/L3 after post-commit or post-query reflection, after checking for similar existing nodes. The agent weighed the evidence and chose not to create.
- Where: agent-side only. The CLI never sees this; it is the agent's internal acknowledgment that no `list create` / `report create` call was made.
- Response shape: N/A (no CLI call). Agent may later revisit the decision if new content is ingested or queried that changes the comparison set.


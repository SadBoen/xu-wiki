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
| `xu-wiki` | The skill bundle / project name | This file's YAML frontmatter |
| `/xu-wiki` | Slash command (Trae convention) | Enters the matching SOP |
| `xu` | The CLI binary | All `xu <verb>` shell invocations |

The
slash command `/xu-wiki` (Trae) is the agent's UX entry into a SOP and is
not a CLI invocation.

## File layout

This skill is split into 8 files per the principles in
`design-docs/09-skill-architecture.md` (PRIN-SKILL-1~7, BAN-SKILL-1/2/3/3a):

| File | Purpose | When to load |
|---|---|---|
| `SKILL.md` (this file) | Index + cross-cutting rules | **Always** |
| `create.md` | `/xu-wiki create` SOP — full self-contained | When entering create SOP |
| `ingest.md` | `/xu-wiki ingest` SOP — full self-contained | When entering ingest SOP |
| `query.md` | `/xu-wiki query` SOP — full self-contained | When entering query SOP |
| `doctor.md` | `/xu-wiki doctor` SOP — full self-contained | When entering doctor SOP |
| `config.md` | `/xu-wiki config` SOP — full self-contained | When entering config SOP |
| `reference/error-catalog.md` | placeholder — future error_class catalog | On demand |

**No file links to another SOP file** (BAN-SKILL-1). If an SOP file needs to
mention a CLI from another SOP, it says "see SKILL.md §X" — never links
directly. The agent places all 8 files in its own skill discovery dir
(via its platform's skill manager — Hermes / Trae / Claude / Cursor).

## When to use this skill

The skill exposes **five SOPs** (Standard Operating Procedures). The
slash command `/xu-wiki <verb>` enters a SOP, which orchestrates one or
more CLI subcommands. The five SOPs cover the full wiki lifecycle:

- **create** — `/xu-wiki create` — build a new empty wiki at a path
  (raws/, nodes/{page,list,report}/, .xu/).
- **ingest** — `/xu-wiki ingest` — add content (PDF / DOCX / PPTX / MD /
  image / album) to a wiki as Node_Page (L1, immutable). Two-phase flow
  for prose / document content (`ingest-file` → `ingest-commit`,
  PRIN-ING-1); **single-shot album flow** for a group of images
  (`ingest-album`, PRIN-ING-14). Body style must match content type
  (PRIN-ING-13: table / prose / code block).
- **query** — `/xu-wiki query` — find knowledge with elastic slicing,
  IDF, Fast Pass; read individual nodes; follow L2/L3 hints.
- **doctor** — `/xu-wiki doctor` — read-only consistency checks on
  fields / files / relations / L1 immutability / Report evidence / IDF;
  apply `--fix` for safe repairs; rebuild derived layers when needed.
- **config** — `/xu-wiki config` — manage configuration: set / change
  wiki alias, register / unregister existing directories, manage the
  MinerU API key, inspect the registered wikis, **and uninstall the
  xu-wiki package itself** (`xu uninstall`).

## SOP map (slash command ↔ CLI orchestration)

A slash command `/xu-wiki <verb>` enters a SOP — **not** a CLI subcommand.
The five SOPs orchestrate one or more CLI subcommands each:

| SOP | Intent | CLI commands it calls |
|---|---|---|
| `/xu-wiki create` | build a new empty wiki | `create` (+ optional `wikis` to verify) |
| `/xu-wiki ingest` | add content to a wiki | `ingest-file` → `ingest-commit` (PRIN-ING-1 two-phase, prose / code block); `ingest-album` (PRIN-ING-14 single-shot, table-form album); `ingest-verify` (post-commit integrity check); `reorganize` (if user不满意路径); optional `query-relation add`; **post-commit reflection (PRIN-CR-1)**: query for similar List → extend or create new; LLM decides autonomously, no user approval needed |
| `/xu-wiki query` | find knowledge | `query`; then `read`, `list show`, or `report show` per hint; **post-query reflection (PRIN-CR-1)**: query for similar Report → extend or create new; LLM decides autonomously, no user approval needed |
| `/xu-wiki doctor` | check / repair / destructive ops | `doctor-all`; per-check subcommands; `--fix` for safe auto-repair; `delete-node`; `rebuild`; `nodes` (for dangling lookup) |
| `/xu-wiki config` | manage configuration | `wikis` to inspect; `alias set/unset/show` for aliases; `register` / `unregister` for wiki registry; `config set-mineru-key / show / path` for global settings; `skills path / list` for the bundled skill source dir; **`uninstall`** for removing xu-wiki itself (always dry-run first, then `--execute` after user confirms) |

Full SOP semantics: design-docs/08-sop-architecture.md.

## Architecture in 30 seconds

- **L1 Node_Page** — immutable markdown facts. SHA256-dedup. UID never reused.
- **L2 Node_List** — `.md` comparison/aggregation in `nodes/list/`. Members in frontmatter.
- **L3 Node_Report** — `.md` reasoning in `nodes/report/`. **Requires ≥ 1 evidence ref** (else rejected).
- **Relations** — exactly **50 edges per node** (LRU, head=touch, tail=evict). No category, no score.
- **DB** holds nodes / patches / IDF / relations (L1 metadata only; L2/L3 are `.md`-only).
- **FS** holds raw material pool (`raws/`), L1 markdown (`nodes/page/`), L2 (`nodes/list/`), L3 (`nodes/report/`).
- **CLI is offline-first** (CONST-ARCH-1 / PRIN-ARCH-11/12). MinerU is an optional
  parser in the fallback chain; the key is loaded from `MINERU_API_KEY` env or
  `~/.xu-wiki/config.yaml` (`XU_HOME` overrides the dir).

## Hard rules the agent MUST respect

0. **You are the only legitimate caller of `xu`.** User never touches CLI directly.
   Translate intent → CLI calls. Parse 4-key JSON → natural language reply. On pushback: re-interpret via SOP, don't ask user to retype.

0a. **Uninstall = 2 surfaces.** Skill bundle → agent self-removes (`~/.hermes/skills/xu-wiki/`). Program + config → `xu uninstall --execute`. **Wiki data NEVER deleted** (no flag, no option, no branch). See doctor.md §Uninstall.

0b. **Install is documented in README only.** xu-wiki is pre-installed when this skill loads — this bundle carries no install steps. No `xu install` or `/xu-wiki install` command.

1. **Never edit L1 markdown body** — immutable (PRIN-ARCH-2/3). UIDs retired on delete, never reused.
2. **Report needs ≥1 evidence ref** at create-time (BAN-ARCH-5). Empty evidence rejected.
3. **50 edges max per node** (LRU: 51st evicts tail). Do not re-add evicted edge unless needed.
4. **Offline-first** — only MinerU parse hits network. On failure: markitdown → text → image silently.
5. **No secret in code or git** — MinerU key in `~/.xu-wiki/config.yaml` or `MINERU_API_KEY` env.
6. **All commands return 4-key JSON** — `{status, data, message, hints}`. `hints` is for agent, not user.
7. **Deterministic output** — no timestamps, random IDs, or locale in response. Use `--wiki`.
8. **Missing required args: ask, don't guess.** Never auto-pick names or paths (BAN-CRT-1/3).
9. **Absolute paths only** (`~` is fine). Never `./foo` (breaks idempotency + symlink guard).
10. **Slash command = SOP entry, not CLI subcommand.** `/xu-wiki <verb>` → enter SOP → pick CLI(s). See SOP map above.
11. **Within a SOP: match intent to CLI (PRIN-SOP-7).** Do NOT coerce to an unrelated CLI.
    - doctor + "move X to Y" → `xu reorganize --wiki W --uid X --new-node-path Y` (atomic; never delete+re-ingest)
12. **Asymmetric creation bias (PRIN-CR-1):** After ingest → bias List; after query → bias Report. LLM decides autonomously, no user approval needed. Before creating: query to find similar existing List/Report. If similar found → extend the existing one instead of creating a new one.
13. **Phase 1 temp file (PRIN-ING-7):** Written to system temp, deleted on success, retained on failure. No `nodes/pending/`.
14. **Forbidden: `execute_code` for xu CLI.** stderr corrupts JSON output. Use bash/terminal tool.

## Quick safety checklist

Before declaring an ingest done, run through this every time:

1. **`raws/<node_path>/` has the source file copy?** (PRIN-ING-6) — if empty but
   `nodes/page/` has content, PRIN-ING-6 was bypassed. Stop and re-investigate.
2. **Phase 1 temp file was deleted on success?** (PRIN-ING-7) — if `ingest-commit`
   succeeded but the temp file still exists, that is a bug. Re-run `ingest-commit`
   (it will reject a duplicate commit) to confirm deletion.
3. **`data.created[].raw_path` is non-null?** — if null, explains why raws/ is
   empty. Null is expected only for `--native` (agent-synthesized text).
4. **`xu doctor-all --wiki W` returns zero issues?** — do not proceed to the next
   batch if doctor reports pending leftovers or other ingest anomalies.

**Any NO answer means: stop, investigate, fix before continuing.**

## Process-layer audit log (CONST-ARCH-6 / PRIN-ARCH-26)

**Every CLI invocation emits exactly one process-layer audit line** — the
agent does NOT need to (and must NOT) call any logging command explicitly:

- Commands with a resolvable `--wiki` write to `<wiki>/.xu/audit.jsonl`
- Commands without `--wiki` (or unresolvable) write to
  `~/.xu-wiki/global_audit.jsonl`

Each line carries `ts` / `command` / `wiki` / `status` / `elapsed_ms`;
failures add `error_class`. This log exists for SOP / CLI health diagnosis
only — it is NOT content history, NOT a substitute for `nodes.created_at`,
and NOT consumed by any CLI decision.

## Reading the response

Every command prints one JSON object to stdout. Read `data.*` for facts and
`hints` for the next step. Examples:

```json
{"status": "success", "data": {"uid": "ABCD1234", "title": "BERT"},
 "message": "read complete", "hints": ["query-relation list --from-uid ..."]}
```

On a `list_hint` / `report_hint` field, the agent runs the post-query
reflection (PRIN-CR-1; see hard rule 12): query for similar List/Report first;
extend existing if found; otherwise LLM decides autonomously (no user approval needed).
Hints are starting points, not mandates.

## Quick start for the agent

> Already installed? For install / deploy steps see README (§Install, §Agent
> skill deployment). The flow below assumes `xu` is already on PATH.

```bash
# 1. create a wiki
xu create --name research --path /abs/path/to/wiki

# 2. ingest L1 — two phases (PRIN-ING-1); verify raws/ has copy after (PRIN-ING-6)
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

## See also

- `README.md` in this repo for the full reference
- `tests/e2e_verify.sh` for a runnable smoke test
- `tests/test_core.py` for unit tests of the deterministic core
- `design-docs/09-skill-architecture.md` for the file-layout principles
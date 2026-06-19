---
name: "xu-wiki"
description: "Operate xu-wiki three-layer knowledge base via 5 SOPs (create/ingest/query/doctor/config) on a deterministic CLI. Manage 50-edge LRU, Node_List (L2), Node_Report (L3)."
---

# xu-wiki

xu-wiki is a **relation-driven three-layer knowledge base** designed for AI
agents. It exposes a deterministic offline-first CLI; this skill is the
authoritative invocation guide for the agent side.

## File layout

This skill is split into 6 files per the principles in
`design-docs/09-skill-architecture.md` (PRIN-SKILL-1~6, BAN-SKILL-1/2):

| File | Purpose | When to load |
|---|---|---|
| `SKILL.md` (this file) | Index + cross-cutting rules | **Always** |
| `create.md` | `/xu-wiki create` SOP — full self-contained | When entering create SOP |
| `ingest.md` | `/xu-wiki ingest` SOP — full self-contained | When entering ingest SOP |
| `query.md` | `/xu-wiki query` SOP — full self-contained | When entering query SOP |
| `doctor.md` | `/xu-wiki doctor` SOP — full self-contained | When entering doctor SOP |
| `config.md` | `/xu-wiki config` SOP — full self-contained | When entering config SOP |

**No file links to another SOP file** (BAN-SKILL-1). If an SOP file needs to
mention a CLI from another SOP, it says "see SKILL.md §X" — never links
directly. The deployer puts all 6 files in the Agent's discovery dir.

## When to use this skill

The skill exposes **five SOPs** (Standard Operating Procedures). The
slash command `/xu-wiki <verb>` enters a SOP, which orchestrates one or
more CLI subcommands. The five SOPs cover the full wiki lifecycle:

- **create** — `/xu-wiki create` — build a new empty wiki at a path
  (raws/, nodes/{page,list,report,pending}/, .xu/).
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
  MinerU API key, inspect the registered wikis.

Software-lifecycle commands (`install` / `uninstall`) are **not** SOPs —
they manage the CLI itself, not wiki data (CONST-SOP-3). They live in
`config.md` since they share the software-lifecycle scope.

## SOP map (slash command ↔ CLI orchestration)

A slash command `/xu-wiki <verb>` enters a SOP — **not** a CLI subcommand.
The five SOPs orchestrate one or more CLI subcommands each:

| SOP | Intent | CLI commands it calls |
|---|---|---|
| `/xu-wiki create` | build a new empty wiki | `create` (+ optional `wikis` to verify) |
| `/xu-wiki ingest` | add content to a wiki | `ingest-file` → `ingest-commit` (PRIN-ING-1 two-phase, prose / code block); `ingest-album` (PRIN-ING-14 single-shot, table-form album); optional `query-relation add`, `list create`, `report create` |
| `/xu-wiki query` | find knowledge | `query`; then `read`, `list show`, or `report show` per hint |
| `/xu-wiki doctor` | check / repair / destructive ops | `doctor-all`; per-check subcommands; `--fix` for safe auto-repair; `delete-node`; `rebuild`; `nodes` (for dangling lookup) |
| `/xu-wiki config` | manage configuration | `wikis` to inspect; `alias set/unset/show` for aliases; `register` / `unregister` for wiki registry; `config set-mineru-key / show / path` for global settings; `install` / `uninstall` for software lifecycle |

`xu-wiki install` and `xu-wiki uninstall` are **not** SOPs — they manage
the software itself, not wiki data (CONST-SOP-3, design-docs/08).
Full SOP semantics: design-docs/08-sop-architecture.md.

## Architecture in 30 seconds

- **L1 Node_Page** — immutable markdown facts. SHA256-dedup. UID never reused.
- **L2 Node_List** — DB-only comparison/aggregation. Members are L1 UIDs.
- **L3 Node_Report** — DB-only reasoning. **Requires ≥ 1 evidence ref** (else rejected).
- **Relations** — exactly **50 edges per node** (LRU, head=touch, tail=evict). No category, no score.
- **DB** holds nodes / patches / IDF / relations / evidence / list_members.
- **FS** holds only the raw material pool (`raws/`) and L1 markdown (`nodes/page/`).
- **CLI is offline-first** (CONST-ARCH-1 / PRIN-ARCH-11/12). MinerU is an optional
  parser in the fallback chain; the key is loaded from `MINERU_API_KEY` env or
  `~/.xu/config.yaml` (`XU_HOME` overrides the dir).

## Hard rules the agent MUST respect

1. **Never edit L1 markdown body** — it is immutable (PRIN-ARCH-2/3).
   UIDs are retired on delete, never reused (BAN-ARCH-2).
2. **Report needs evidence** — `--references` must list ≥ 1 existing UIDs
   (BAN-ARCH-5). Empty evidence is rejected at create-time.
3. **50 edges only** — adding a 51st evicts the tail. Do not re-add the evicted
   edge unless you actually need it; it will go back to the head (PRIN-ARCH-7~10).
4. **Offline-first** — only MinerU parse may hit the network. Everything else
   must be local. If MinerU fails (401 / network / ZIP error), the chain falls
   back to `markitdown` → `text` → `image` silently (CONST-ING-1).
5. **No secret in code or git** — MinerU key lives in `~/.xu/config.yaml`
   (outside this repo) or `MINERU_API_KEY` env. Never hardcode.
6. **All commands return 4-key JSON** — `{status, data, message, hints}`.
   `status ∈ {success, warning, error}` (warning = partial, e.g. SHA256 dup;
   error carries `data.error_class`). `hints` is for the agent, not the user.
7. **Output is deterministic** — given same wiki + same input, output bytes
   are identical. Do not inject timestamps, random IDs, or locale into the
   response body. Use `--wiki` rather than relying on CWD.
8. **Missing required args: ask, do not guess.** When the user requests a
   command whose required flag (`--name`, `--path`, `--file`, `--title`,
   `--references`, `--members`, etc.) is missing from the request,
   **ask the user explicitly before invoking**. The CLI never auto-picks
   a name (`xu-wiki create` without `--name` returns `MissingName` per
   BAN-CRT-3) and never auto-picks a path (a guessed path that already
   holds user content is refused by BAN-CRT-1 — protecting data beats
   saving a round trip). The wrong-name-then-silent-new-wiki failure
   mode is the single most common agent accident; the only safe guard
   is to ask first, every time.
9. **Paths are absolute; `~` is fine.** All `--path` and `--file`
   arguments must be absolute paths. The CLI calls `Path.expanduser`
   internally, so the agent may pass `~/Documents/NepTune` directly
   without pre-expansion. Never pass relative paths like `./foo` — they
   break idempotency (CONST-CRT-3) and the symlink-escape guard
   (CONST-CRT-5). If the user gave a relative path, ask for the absolute
   location before invoking.
10. **Slash command is a SOP entry, NOT a CLI subcommand (BAN-SOP-1).**
    `/xu-wiki <verb>` enters the `<verb>` SOP, which orchestrates one or
    more CLI subcommands. It does **not** translate to `xu-wiki <verb>`.
    Specifically:
    - `/xu-wiki config` does **not** call a CLI named `config` (none
      exists in the current CLI); it enters the config SOP, which calls
      `alias` / `register` / `unregister` / `wikis` / `config`.
    - `/xu-wiki ingest` does **not** call a CLI named `ingest`; it
      calls `ingest-file` then `ingest-commit` (PRIN-ING-1).
    Before invoking anything, read the SOP map above and identify which
    CLI subcommands the SOP needs. If the user's `<verb>` is not in the
    five-SOP list, **stop and ask** — do not guess the nearest CLI name.
11. **Within a SOP, match user natural-language intent to CLI (PRIN-SOP-7).**
    After entering a SOP, the agent's job is to interpret the user's
    actual intent (often natural language, not a verb-noun command)
    and pick the right CLI from that SOP's palette. CLIs are atomic
    capabilities, NOT aliases of the SOP.
    - `/xu-wiki doctor` then user says "delete X node" → call
      `delete-node --wiki W --uid X` (with `--force` if referenced).
    - `/xu-wiki doctor` then user says "full check" → call
      `doctor-all --wiki W`.
    - `/xu-wiki doctor` then user says "move X to Y directory" →
      **no CLI exists for node-move**; SOP must **explicitly refuse
      and explain** (do NOT coerce by calling an unrelated CLI).
    Refusing an unsupported intent is correct behavior; coercing to
    an unrelated CLI is the same class of bug as the
    `/xu-wiki config → create --alias` workaround.

> **Ingest-specific rule** (PRIN-ING-13, the body-form decision tree) lives
> in `ingest.md` since it only applies to the ingest SOP.

## Process-layer audit log (CONST-ARCH-6 / PRIN-ARCH-26)

**Every CLI invocation emits exactly one process-layer audit line** — the
agent does NOT need to (and must NOT) call any logging command explicitly:

- Commands with a resolvable `--wiki` write to `<wiki>/.xu/audit.jsonl`
- Commands without `--wiki` (or unresolvable) write to
  `~/.xu/global_audit.jsonl`

Each line carries `ts` / `command` / `wiki` / `status` / `elapsed_ms`;
failures add `error_class`. This log exists for SOP / CLI health diagnosis
only — it is NOT content history, NOT a substitute for `nodes.created_at`,
and NOT consumed by any CLI decision.

## Reading the response

Every command prints one JSON object to stdout. Read `data.*` for facts and
`hints` for the next step. Examples:

```json
{"status": "success", "data": {"uid": "2026-ABCD1234", "title": "BERT"},
 "message": "read complete", "hints": ["query-relation list --from-uid ..."]}
```

On a `list_hint` / `report_hint` field, the agent decides whether to follow up
with `list create` or `report create` — the CLI does not act on its own
(PRIN-QRY-1).

## Quick start for the agent

```bash
# 1. one-time install (per machine)
xu-wiki install

# 2. create a wiki
xu-wiki create --name research --path /abs/path/to/wiki

# 3. ingest L1 — two phases (PRIN-ING-1)
xu-wiki ingest-file   --wiki research --file /abs/path/to/source.pdf   # → pending
xu-wiki ingest-commit --wiki research --title "BERT" --template article # → L1 entry

# 4. query (Agent grades the keywords into core vs expansion)
xu-wiki query --wiki research --core "transformer,attention" \
  --expansion "self-attention,encoder" --top-k 5

# 5. wire relations
xu-wiki query-relation add --wiki research \
  --from-uid <uid-A> --to-uid <uid-B> --relation-name cites --comment "section 3.2"

# 6. L2 / L3
xu-wiki list   create --wiki research --title "top 10 models" \
  --members <uid1>,<uid2>,... --dimension "by-parameter-count"
xu-wiki report create --wiki research --title "transformer survey" \
  --references <uid1>,<uid2>,<uid3> --body "## findings ..."

# 7. health
xu-wiki doctor-all --wiki research
xu-wiki rebuild    --wiki research --granularity keep-l1
```

## See also

- `README.md` in this repo for the full reference
- `tests/e2e_verify.sh` for a runnable smoke test
- `tests/test_core.py` for unit tests of the deterministic core
- `design-docs/09-skill-architecture.md` for the file-layout principles

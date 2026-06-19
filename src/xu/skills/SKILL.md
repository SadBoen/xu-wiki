---
name: "xu-wiki"
description: "Operate xu-wiki three-layer knowledge base via 5 SOPs (create/ingest/query/doctor/config) on a deterministic CLI. Manage 50-edge LRU, Node_List (L2), Node_Report (L3)."
---

# xu-wiki

xu-wiki is a **relation-driven three-layer knowledge base** designed for AI
agents. It exposes a deterministic offline-first CLI; this skill is the
authoritative invocation guide for the agent side.

## When to use this skill

The skill exposes **five SOPs** (Standard Operating Procedures). The
slash command `/xu-wiki <verb>` enters a SOP, which orchestrates one or
more CLI subcommands. The five SOPs cover the full wiki lifecycle:

- **create** — `/xu-wiki create` — build a new empty wiki at a path
  (raws/, nodes/{page,list,report,pending}/, .xu/).
- **ingest** — `/xu-wiki ingest` — add content (PDF / DOCX / PPTX / MD /
  image) to a wiki as Node_Page (L1, immutable). Two-phase flow:
  `ingest-file` → `ingest-commit` (PRIN-ING-1).
- **query** — `/xu-wiki query` — find knowledge with elastic slicing,
  IDF, Fast Pass; read individual nodes; follow L2/L3 hints.
- **doctor** — `/xu-wiki doctor` — read-only consistency checks on
  fields / files / relations / L1 immutability / Report evidence / IDF;
  apply `--fix` for safe repairs; rebuild derived layers when needed.
- **config** — `/xu-wiki config` — manage configuration: set / change
  wiki alias, register / unregister existing directories, manage the
  MinerU API key, inspect the registered wikis.

Software-lifecycle commands (`install` / `uninstall`) are **not** SOPs —
they manage the CLI itself, not wiki data (CONST-SOP-3).

## SOP map (slash command ↔ CLI orchestration)

A slash command `/xu-wiki <verb>` enters a SOP — **not** a CLI subcommand.
The five SOPs orchestrate one or more CLI subcommands each:

| SOP | Intent | CLI commands it calls |
|---|---|---|
| `/xu-wiki create` | build a new empty wiki | `create` (+ optional `wikis` to verify) |
| `/xu-wiki ingest` | add content to a wiki | `ingest-file` → `ingest-commit` (PRIN-ING-1 two-phase); optional `query-relation add`, `list create`, `report create` |
| `/xu-wiki query` | find knowledge | `query`; then `read`, `list show`, or `report show` per hint |
| `/xu-wiki doctor` | check / repair health | `doctor-all`; optional `--fix`; `rebuild` for derived layers |
| `/xu-wiki config` | manage configuration | `wikis` to inspect; `alias set/unset/show` for aliases; `register` / `unregister` for wiki registry; `config set-mineru-key / show / path` for global settings |

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

## Command map (use the EXACT subcommand names — see `xu-wiki <sub> --help`)

```
xu-wiki install                        # capabilities only; never touches wiki data
xu-wiki uninstall [--execute]          # default dry-run
xu-wiki create --name <n> --path <abs> [--alias <a>]   # empty template at <abs>
xu-wiki wikis                          # list registered wikis (read-only)

# ingest is TWO phases (PRIN-ING-1): parse to pending, then commit to L1.
xu-wiki ingest-file   --wiki <w> --file <abs> [--node-path <p>]   # Phase 1: parse → pending
xu-wiki ingest-commit --wiki <w> [--pending <f>] [--title <t>] [--node-path <p>] \
                      [--template article|table|gallery] [--digest <d>] \
                      [--relations '<json>'] [--native '<md>'] [--author <a>]   # Phase 2: only write entry

xu-wiki query --wiki <w> --core <kw,kw> [--expansion <kw,kw>] [--top-k N] \
              [--neighbors] [--include-inactive]    # core vs expansion are graded by the Agent
xu-wiki read  --wiki <w> --uid <uid>
xu-wiki nodes --wiki <w> [--layer Page|List|Report] [--include-inactive]

xu-wiki query-relation add  --wiki <w> --from-uid <uid> --to-uid <uid> \
                            --relation-name <r> [--comment <c>]
xu-wiki query-relation list --wiki <w> --from-uid <uid>

xu-wiki list create --wiki <w> --title <t> --members <uid,uid,...> \
                    [--dimension <d>] [--node-path <p>]
xu-wiki list show   --wiki <w> --uid <uid>
xu-wiki report create --wiki <w> --title <t> --body <md> \
                      --references <uid,uid,...> [--node-path <p>]   # references = evidence chain
xu-wiki report show   --wiki <w> --uid <uid>

xu-wiki doctor-all --wiki <w> [--fix]   # run all 6 checks
xu-wiki doctor-fields|doctor-files|doctor-relations|doctor-l1-immutable|\
        doctor-report-evidence|doctor-idf --wiki <w> [--fix]
xu-wiki delete-node --wiki <w> --uid <uid> [--force]
xu-wiki rebuild     --wiki <w> --granularity keep-l1|keep-l1-l2|full

# SOP-config (M6): alias / register / unregister / global config
xu-wiki alias set     --wiki <w> --alias <new>     # set or change alias
xu-wiki alias unset   --wiki <w>                   # remove alias (warns if none)
xu-wiki alias show    --wiki <w>                   # show current alias
xu-wiki register      --name <n> --path <abs> [--alias <a>]   # register existing dir (NO files written)
xu-wiki unregister    --name <n>                   # remove from registry (wiki files NOT touched)
xu-wiki config set-mineru-key                       # reads from MINERU_API_KEY env (safer than --key)
xu-wiki config show                                 # global config (secrets masked)
xu-wiki config path                                 # global config file paths
```

NOTE: keyword grading is the Agent's job (PRIN-ARCH-12 / DESIGN-ARCH-4). The CLI
does NOT split a free-text query — you pass already-graded `--core` (entities,
weighted high) and `--expansion` (synonyms, weighted low) comma lists. There is
no `--q`, no `--mode`, no `--limit`.

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
   (CONST-CRT-5). If the user gave a relative path, ask for the
   absolute location before invoking.
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

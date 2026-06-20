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
| `xu-wiki` | The skill bundle / project name | This file's YAML frontmatter; PyPI package name (`pip install xu-wiki`) |
| `/xu-wiki` | Slash command (Trae convention) | Enters the matching SOP |
| `xu` | The CLI binary | All `xu <verb>` shell invocations after install |

After `pip install xu-wiki`, the CLI command is `xu`, not `xu-wiki`. The
slash command `/xu-wiki` (Trae) is the agent's UX entry into a SOP and is
not a CLI invocation.

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
directly. The agent places all 6 files in its own skill discovery dir
(via its platform's skill manager — Hermes / Trae / Claude / Cursor).

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

## SOP map (slash command ↔ CLI orchestration)

A slash command `/xu-wiki <verb>` enters a SOP — **not** a CLI subcommand.
The five SOPs orchestrate one or more CLI subcommands each:

| SOP | Intent | CLI commands it calls |
|---|---|---|
| `/xu-wiki create` | build a new empty wiki | `create` (+ optional `wikis` to verify) |
| `/xu-wiki ingest` | add content to a wiki | `ingest-file` → `ingest-commit` (PRIN-ING-1 two-phase, prose / code block); `ingest-album` (PRIN-ING-14 single-shot, table-form album); optional `query-relation add`; **post-commit reflection (PRIN-CR-1)** with PRIMARY bias toward `list create` (Report only on contradiction) |
| `/xu-wiki query` | find knowledge | `query`; then `read`, `list show`, or `report show` per hint; **post-query reflection (PRIN-CR-1)** with PRIMARY bias toward `report create` (List only on missing axis) |
| `/xu-wiki doctor` | check / repair / destructive ops | `doctor-all`; per-check subcommands; `--fix` for safe auto-repair; `delete-node`; `rebuild`; `nodes` (for dangling lookup) |
| `/xu-wiki config` | manage configuration | `wikis` to inspect; `alias set/unset/show` for aliases; `register` / `unregister` for wiki registry; `config set-mineru-key / show / path` for global settings; `skills path / list` for the bundled skill source dir |

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

0. **You are the only legitimate caller of `xu`.** The user communicates
   with you through your UI (chat / voice / IM). They never run CLI
   commands themselves (PRIN-SOP-8 / BAN-SOP-5). Three consequences:
   - Translate the user's natural-language intent into CLI calls
     yourself; never tell the user "please run `xu <verb>` in a
     terminal" — they shouldn't be anywhere near a shell.
   - The 4-key JSON you get back is for you to parse and reason about,
     then translate into a human-readable reply for the user.
     `data.error_class` is your routing hint; the user should never see
     raw CLI output.
   - When the user pushes back ("that's wrong", "I didn't say create",
     "try a different way"), re-interpret their intent through the SOP
     and pick a new CLI — they will not retype a corrected command
     for you.

0a. **Software lifecycle (install / uninstall / upgrade) is OUTSIDE the
    5 SOPs.** There is **no `/xu-wiki install`**, **no `/xu-wiki uninstall`**,
    and **no `/xu-wiki upgrade`** slash command — they do not exist and
    you must not invent them. When the user says anything about installing,
    uninstalling, or upgrading xu-wiki:
    - **Recognise the intent** ("uninstall xu-wiki", "remove xu-wiki",
      "升级一下 xu-wiki", "把 xu-wiki 删了", "I want to get rid of
      xu-wiki", etc.) and respond in natural language.
    - **Route to your own bash / shell tool** — **NOT** to `xu` (the
      `xu` CLI has no install / uninstall / upgrade subcommand; calling
      `xu install` will return an `ArgParseError`).
    - **Run the corresponding pip command**:
      - install   → `pip install "xu-wiki[parse,nlp,vision]"`
      - upgrade   → `pip install --upgrade "xu-wiki[parse,nlp,vision]"`
      - uninstall → `pip uninstall xu-wiki -y`
    - **Translate pip's stdout/stderr back to the user** in natural
      language. Example: pip prints "Successfully uninstalled
      xu-wiki-0.1.0" → tell the user "已卸载 xu-wiki 0.1.0".
    - **Confirm destructive operations** before running them (especially
      uninstall) — show what will be removed and wait for explicit "yes"
      from the user. This is the same safety contract you apply to
      any other destructive xu CLI (see `delete-node` / `rebuild`).
    - **Never ask the user to run pip themselves** — that violates
      PRIN-SOP-8 ("User never touches CLI"). You run it on their behalf.

    PRIN-SOP-8 still holds: you are the only legitimate caller of `xu`
    AND you are the only legitimate executor of pip on the user's behalf.
    The user only ever types natural language into your UI.
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
   a name (`xu create` without `--name` returns `MissingName` per
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
    more CLI subcommands. It does **not** translate to `xu <verb>` —
    `xu` is the binary name but `/xu-wiki` is the agent's slash command
    for entering a SOP. Specifically:
    - `/xu-wiki config` does **not** call a CLI subcommand literally
      named `config` with no sub-subcommand; it enters the config SOP,
      which calls `alias set/unset/show` / `register` / `unregister` /
      `wikis` / `config set-mineru-key|show|path` / `skills path|list`.
      (`config` itself is a subcommand that **requires** one of
      `set-mineru-key | show | path`.)
    - `/xu-wiki ingest` does **not** call a CLI named `ingest`; it
      calls `ingest-file` then `ingest-commit` (PRIN-ING-1).
    Before invoking anything, read the SOP map above and identify which
    CLI subcommands the SOP needs. If the user's `<verb>` is not in the
    five-SOP list, **stop and ask** — do not guess the nearest CLI name.
    Also note: there is NO `xu install` or `xu uninstall` command —
    install is `pip install xu-wiki` (see Quick start).
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
12. **Asymmetric creation bias** (PRIN-CR-1). After `ingest-commit` or after
    `query`, the agent MUST run a creation-value reflection before declaring
    the task done / before answering the user. The reflection has an
    asymmetric default so it maps to user intent:
    - After **ingest** → bias toward proposing **List** (PRIMARY
      valuation). Report is SECONDARY (only if a contradiction /
      re-evaluation emerged). Single-page ingest also triggers
      reflection; "just one page" is not an excuse.
    - After **query**  → bias toward proposing **Report** (PRIMARY
      valuation). List is SECONDARY (only if hits form a natural
      comparable group on a missing axis).
    - **Never auto-create** — if value is real, draft the payload
      (`--title` / `--members` / `--dimension` for List;
      `--title` / `--body` / `--references` for Report), show a
      one-sentence preview to the user, and wait for explicit
      approval. The CLI does not run this reflection (PRIN-QRY-3) and
      does not act on its own (PRIN-QRY-1).
    Full reflection checklist → `ingest.md §Post-commit reflection`
    and `query.md §Workflow` step 5.

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

On a `list_hint` / `report_hint` field, the agent must run the post-query
reflection (PRIN-CR-1; see hard rule 12): hints are starting points, not
mandates. PRIMARY bias after query is toward Report; the CLI does not
act on its own (PRIN-QRY-1).

## Quick start for the agent

```bash
# 1. one-time install (per machine) — same as any Python tool
pip install "xu-wiki[parse,nlp,vision]"
#    ↳ installs the xu CLI binary, the skill bundle source (site-packages/xu/skills/),
#      and the 3 optional parser groups

# 2. discover the skill source path (for the agent's own skill manager)
xu skills path
#    ↳ prints the on-disk dir of the 8 skill files; the agent copies them into
#      its own skill discovery dir per the agent platform's convention

# 3. create a wiki
xu create --name research --path /abs/path/to/wiki

# 4. ingest L1 — two phases (PRIN-ING-1)
xu ingest-file   --wiki research --file /abs/path/to/source.pdf   # → pending
xu ingest-commit --wiki research --title "BERT" --template article # → L1 entry

# 5. query (Agent grades the keywords into core vs expansion)
xu query --wiki research --core "transformer,attention" \
  --expansion "self-attention,encoder" --top-k 5

# 6. wire relations
xu query-relation add --wiki research \
  --from-uid <uid-A> --to-uid <uid-B> --relation-name cites --comment "section 3.2"

# 7. L2 / L3
xu list   create --wiki research --title "top 10 models" \
  --members <uid1>,<uid2>,... --dimension "by-parameter-count"
xu report create --wiki research --title "transformer survey" \
  --references <uid1>,<uid2>,<uid3> --body "## findings ..."

# 8. health
xu doctor-all --wiki research
xu rebuild    --wiki research --granularity keep-l1
```

## See also

- `README.md` in this repo for the full reference
- `tests/e2e_verify.sh` for a runnable smoke test
- `tests/test_core.py` for unit tests of the deterministic core
- `design-docs/09-skill-architecture.md` for the file-layout principles
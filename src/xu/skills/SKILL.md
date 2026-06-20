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
| `reference/pitfalls.md` | placeholder — future pitfalls log | On demand |

**Install/deploy docs are NOT in this bundle** (BAN-SKILL-3a / CONST-INST-6):
the bundle is loaded *after* xu-wiki is installed, so how-to-install lives in
the repo `README.md` (readable on GitHub before install). See README §Install
and §Agent skill deployment.

**No file links to another SOP file** (BAN-SKILL-1). If an SOP file needs to
mention a CLI from another SOP, it says "see SKILL.md §X" — never links
directly. The agent places all 8 files in its own skill discovery dir
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
  MinerU API key, inspect the registered wikis, **and uninstall the
  xu-wiki package itself** (`xu uninstall`).

## SOP map (slash command ↔ CLI orchestration)

A slash command `/xu-wiki <verb>` enters a SOP — **not** a CLI subcommand.
The five SOPs orchestrate one or more CLI subcommands each:

| SOP | Intent | CLI commands it calls |
|---|---|---|
| `/xu-wiki create` | build a new empty wiki | `create` (+ optional `wikis` to verify) |
| `/xu-wiki ingest` | add content to a wiki | `ingest-file` → `ingest-commit` (PRIN-ING-1 two-phase, prose / code block); `ingest-album` (PRIN-ING-14 single-shot, table-form album); optional `query-relation add`; **post-commit reflection (PRIN-CR-1)** with PRIMARY bias toward `list create` (Report only on contradiction) |
| `/xu-wiki query` | find knowledge | `query`; then `read`, `list show`, or `report show` per hint; **post-query reflection (PRIN-CR-1)** with PRIMARY bias toward `report create` (List only on missing axis) |
| `/xu-wiki doctor` | check / repair / destructive ops | `doctor-all`; per-check subcommands; `--fix` for safe auto-repair; `delete-node`; `rebuild`; `nodes` (for dangling lookup) |
| `/xu-wiki config` | manage configuration | `wikis` to inspect; `alias set/unset/show` for aliases; `register` / `unregister` for wiki registry; `config set-mineru-key / show / path` for global settings; `skills path / list` for the bundled skill source dir; **`uninstall`** for removing xu-wiki itself (always dry-run first, then `--execute` after user confirms) |

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

0a. **Uninstall goes through the `/xu-wiki config` SOP, then `xu uninstall`.**
    Install is documented in README, not here (see rule 0b / CONST-INST-6).
    Uninstall is non-trivial cleanup so it needs a CLI
    command — but it lives in the **config** SOP because it's a
    system-level action, not a wiki-data operation.

    Uninstall has **three independent surfaces** with **three owners**.
    The CLI owns one of them; the user (via agent) owns the other two:

    | Surface | Owner | Why |
    |---|---|---|
    | Program body (`xu` binary + venv) | `pipx uninstall xu-wiki` (or `pip uninstall`) | pipx/pip track their own installs |
    | Skill bundle (`~/.hermes/skills/xu-wiki/`) | the agent's skill manager | xu and pipx don't know about it |
    | Wiki data (`~/.xu/` + `<wiki>` dirs) | `xu uninstall --execute --purge-*` | pipx/pip don't know about it |

    When the user says anything about uninstalling / removing xu-wiki
    ("把 xu-wiki 卸了", "uninstall xu-wiki", "remove xu-wiki from
    this machine", "I don't need xu-wiki anymore", etc.):

    1. **Enter `/xu-wiki config` SOP** — that's where uninstall lives.
       Do NOT invent a `/xu-wiki uninstall` slash command; it does not
       exist.
    2. **Always dry-run first**: `xu uninstall` (no `--execute`).
       Read `data.plan` AND `data.installer` (∈ {`pipx`, `pip`,
       `unknown`}). The installer field tells you who owns the
       program body.
    3. **Confirm with the user** — list the wikis that would be deleted
       (if `--purge-wikis`), whether the global `~/.xu/` config would
       be wiped (if `--purge-config`), and whether pip would remove the
       package. Wait for explicit "yes" / "确认" / "proceed".
    4. **Re-run with the user's chosen flags + `--execute`**. The
       program-body step depends on `data.installer`:
       - `pipx` → `xu uninstall` cleans data only; agent then runs
         `pipx uninstall xu-wiki` to remove the program.
       - `pip` → `xu uninstall --execute` handles everything (program
         body + data); no separate pip call needed.
       The skill bundle is always removed separately via the agent's
        skill manager (NOT `xu uninstall`).
    5. **Translate the 4-key JSON result** back to natural language.
       Don't paste raw JSON at the user.
    6. **Never run `pip uninstall` or `pipx uninstall` directly via
       your bash tool**. Even though it would technically work, it
       bypasses SKILL.md discoverability and the dry-run safety
       contract. Always:
       - For program body: `xu uninstall` handles it (and reports
         `data.installer` so you know which tool owns it). If
         installer is `pipx`, the response will include
         `result.pip.next_action = "pipx uninstall xu-wiki"` — at
         that point you call `pipx uninstall xu-wiki` (NOT
         `pip uninstall`).
       - For wiki data: `xu uninstall --execute --purge-*`.
       - For skill bundle: the agent's own skill manager.
    7. **Independent verification (P0)**: after any `--execute`, you
       MUST independently verify the claim before telling the user
       "done". Do not trust the CLI's word:
       - After pip uninstall: `which xu` should return empty; or
         `command -v xu` should fail.
       - After `--purge-wikis`: each `result.wikis.removed[i].path`
         must NOT exist (run `test -e <path>` in your bash tool).
       - After `--purge-config`: `result.config_dir.existed_before`
         was True and `files_removed_count > 0`, and now
         `test -e ~/.xu` returns false.
       If any independent check contradicts the CLI's report, tell
       the user — do not silently report success.
    8. **Watch for semantic contradictions in the 4-key JSON**. If you
       see `plan.mode == "dry-run"` together with `execute == true`,
       or `result.config_dir.ok == true` together with the path still
       on disk, surface the inconsistency to the user in plain
       language ("注意：CLI 返回了 X 但 Y 没发生，建议手工检查").
    9. **Fold equivalent options before asking the user**. If
       `plan.wikis_found == []`, then scope (a) and (b) are identical
       (both preserve wikis because there are no wikis to purge). Do
       not list three options when one is a no-op for the user's data.
       Show only "a (no wikis to worry about) or c (full clean)".
    10. **Use `xu deploy skill --target <agent>`** instead of writing
        hand-rolled `cp -r` commands. The deploy command handles three
        things the manual flow gets wrong: subdir preservation
        (`reference/` files), Python-artifact filter (no
        `__init__.py` or `__pycache__/` leaking into the agent's
        discovery dir), and target→discovery-dir mapping. If `xu` is
        not yet on PATH (e.g. just installed), run the absolute path
        (`~/.local/bin/xu deploy skill ...`) — do NOT fall back to
        `cp -r` unless `xu` truly doesn't exist (very rare).
    11. **Inspect `data.deployment_status` and `data.next_actions`**
        from `xu selfcheck` before declaring "install complete". Empty
        `next_actions` list = nothing left. Any entry means the user
        (and you) must do more. This catches the case where pip
        install succeeded but the skill wasn't deployed.

    This rule exists because **xu-wiki is a GitHub project, not a
    pre-installed brand**. The user discovers it by reading SKILL.md
    from the GitHub URL; you (the agent) only know about xu-wiki after
    loading SKILL.md. Without a CLI uninstall command, you have no
    documented entry point and cannot help. The CLI is the
    **discoverable, SKILL.md-visible, agent-callable** uninstall entry.
    See [PRIN-SOP-8] / [CONST-SOP-3] / design-docs/08-sop-architecture.md.

0b. **Install/deploy is documented in README, not here.** By the time
    you load this skill, xu-wiki is already installed — so this bundle
    deliberately carries no install steps (BAN-SKILL-3a / CONST-INST-6).
    If you need to (re)install, deploy the skill, or fix a PATH issue,
    read the repo `README.md` (§Install, §Agent skill deployment) — it
    is the single authority and is readable on GitHub before install.
    There is no `xu install` command and no `/xu-wiki install` slash
    command; do not invent one.
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
    install is documented in README (see rule 0b), uninstall goes
    through `xu uninstall` (see rule 0a).
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

> Already installed? This bundle is loaded post-install. For install /
> deploy steps see README (§Install, §Agent skill deployment) — not here
> (CONST-INST-6). The flow below assumes `xu` is already on PATH.

```bash
# 1. create a wiki
xu create --name research --path /abs/path/to/wiki

# 2. ingest L1 — two phases (PRIN-ING-1)
xu ingest-file   --wiki research --file /abs/path/to/source.pdf   # → pending
xu ingest-commit --wiki research --title "BERT" --template article # → L1 entry

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
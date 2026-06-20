# xu-wiki

A relation-driven, three-layer wiki engine for AI agents. The CLI is fully
deterministic and never calls an LLM — semantic judgement stays with the agent,
ranking and storage stay with the engine.

> **Who reads this README**: an AI agent loading `SKILL.md` to invoke `xu`
> subcommands. **Not** the end user. The end user talks to the agent through
> a chat UI; the agent does the calling. See [PRIN-SOP-8] in
> `design-docs/08-sop-architecture.md` for the full rationale.

## Concept

Knowledge is organized in three layers plus a relation graph:

| Layer | Name       | Storage      | Purpose                                        |
|-------|------------|--------------|------------------------------------------------|
| L1    | Node_Page  | Markdown + DB| Immutable fact slices (the source of truth)    |
| L2    | Node_List  | DB only      | Comparison / aggregation over existing nodes   |
| L3    | Node_Report| DB only      | Reasoning + conclusion with an evidence chain  |

Every node also carries an ordered, capped (50) **LRU relation list**: no
strong/weak categories, no scores — just recency. Touching a relation (adding
or hitting it in a query) moves it toward the head; the stalest edge is evicted
when the list is full.

### Design invariants

- L1 is immutable. Revisions are append-only `patches` rows; the body hash is
  verifiable (`doctor-l1-immutable`).
- UIDs (`YYYY-XXXXXXXX`) are globally unique and never reused.
- Every command returns a 4-key JSON envelope: `{status, data, message, hints}`
  where `status ∈ {success, warning, error}`.
- A Report with zero evidence is rejected — no naked conclusions.

## Requirements

- Python 3.10+
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) on PATH (a pure-Python
  fallback scanner is used automatically if absent)
- Python deps:
  - **Required**: `PyYAML`
  - **Optional, recommended**: `markitdown[all]` (PDF/DOCX/PPTX parsing),
    `jieba` (Chinese noun extraction for IDF), `Pillow` (image EXIF for albums)
- On Debian/Ubuntu, also: `sudo apt install -y python3-venv` (the `venv` module
  isn't bundled with the OS Python)

## Install

> **PEP 668 heads-up (READ THIS FIRST if you are on Debian 12+,
> Ubuntu 23.04+, Fedora, or Homebrew Python):** system-managed Pythons
> ship with PEP 668 enabled and reject bare `pip install`. You MUST
> install into a virtual environment, otherwise `pip install` will fail
> with `error: externally-managed-environment`. The recommended flow:
>
> ```bash
> python3 -m venv .venv
> .venv/bin/pip install --upgrade pip
> .venv/bin/pip install "xu-wiki[parse,nlp,vision]"
> .venv/bin/xu --help   # verify CLI works
> ```
>
> If `python3 -m venv` complains about `ensurepip`, install
> `python3-venv` first (`sudo apt install -y python3-venv` on Debian/
> Ubuntu, or `sudo dnf install python3-virtualenv` on Fedora).

Once you're in a venv (or on a non-PEP-668 system like macOS system
Python before 3.12, or a custom-built Python):

```bash
pip install "xu-wiki[parse,nlp,vision]"
```

That single command installs:

- the `xu` CLI binary (placed on `PATH` by pip, like any Python tool)
- the bundled skill source (8 files under `<site-packages>/xu/skills/`)
- the 3 optional parser groups

That's it — no `xu install`, no separate `install.sh`, no venv
management, no symlink config. Pip handles all of it.

Set `XU_HOME` to relocate the global config / registry directory (defaults to
`~/.xu`).

**Verify with `xu selfcheck`** (after install, before doing anything
else): it confirms the CLI is on PATH, the skill bundle is readable,
`~/.xu/` is writable, and the three optional extras are present. See
[§Agent skill deployment](#agent-skill-deployment) below for the full
post-install checklist.

## Uninstall (run by the agent via `/xu-wiki config` → `xu uninstall`)

**Install and uninstall are asymmetric on purpose.** Install is just
`pip install xu-wiki` — pip handles it. Uninstall needs its own CLI
command (`xu uninstall`) because:

- xu-wiki is a **GitHub project**, not a pre-installed brand. The user
  discovers it by giving the agent the **GitHub URL**; the agent then
  loads `SKILL.md` and learns what xu-wiki is. Without a CLI uninstall
  command, the agent has no documented entry point for helping with
  uninstall.
- Uninstall is non-trivial cleanup (pip package + optionally wiki data
  + optionally global config) that benefits from a single command with
  side-effect scoping and a built-in dry-run.

The user never types `pip uninstall` in a terminal. The user just tells
the agent in natural language; the agent enters `/xu-wiki config`,
recognises uninstall intent, and runs `xu uninstall` (default dry-run →
confirmation → `--execute`).

The agent's three-step flow:

```bash
# 1. dry-run — always the first call
xu uninstall
# → {
#     "status": "success",
#     "data": {
#       "mode": "dry-run",
#       "execute": false,
#       "pip_uninstall": true,
#       "purge_wikis": false,
#       "purge_config": false,
#       "wikis_found": [{"name": "research", "path": "/abs/path/to/research"}, ...],
#       "global_dir": "/home/user/.xu",
#       "global_dir_exists": true,
#       "package": "xu-wiki"
#     },
#     "message": "dry-run — pass --execute to actually uninstall"
#   }
# NB: in dry-run, `data` IS the plan (no `plan` nesting). After --execute,
# the shape changes to `data = {"plan": <plan>, "result": {pip, wikis, config_dir}}`.

# 2. agent shows the user what's about to happen, user picks a scope:
#    (a) pip only                  → xu uninstall --execute
#    (b) pip + wikis               → xu uninstall --execute --purge-wikis
#    (c) pip + wikis + ~/.xu/      → xu uninstall --execute --purge-wikis --purge-config

# 3. user confirms → agent re-runs with the chosen flags
xu uninstall --execute [--purge-wikis] [--purge-config]
```

Default scope is (a) — pip package only; wiki data and `~/.xu/` are
preserved. The `--purge-*` flags are explicitly opt-in.

There is no `/xu-wiki install` slash command and no `/xu-wiki upgrade`
slash command. There is no `/xu-wiki uninstall` slash command either —
the entry is `/xu-wiki config`, which contains `xu uninstall` as a
CLI palette item. See [CONST-SOP-3] in
`design-docs/08-sop-architecture.md` and SKILL.md hard rule 0a.

> **What the CLI does NOT do**: install / uninstall the package itself. The
> CLI only manages wiki data — it never touches venv / symlink / system PATH.
> All wiki data lives outside the source tree.

## Configuring MinerU (optional)

MinerU is the first parser tried for PDF/DOCX/PPTX in `ingest-file`. It is
**optional** — when no key is configured, the chain silently falls back to
`markitdown` (CONST-ING-1, PRIN-ING-5). The key is resolved in this order:

1. `--api-key` argument (if your wrapper passes one)
2. environment variable `MINERU_API_KEY`
3. `~/.xu/config.yaml` field `mineru.api_key` (overridable with `XU_HOME`)

```bash
# preferred for one-off runs (never touches a file)
export MINERU_API_KEY="<your-key>"

# or persist in the global config (file is OUTSIDE the project, not git-tracked)
python3 -c "
import os
from xu.utils.config import load_global_config, save_global_config
cfg = load_global_config()
cfg['mineru']['api_key'] = os.environ['MY_KEY']
save_global_config(cfg)
"
chmod 600 ~/.xu/config.yaml                     # private permissions
```

The configured key is sent as `Authorization: Bearer <key>` against the MinerU
v4 Precision Extract API (`/api/v4/file-urls/batch` →
`/api/v4/extract-results/batch/{batch_id}` → ZIP → `full.md`). Any failure
(network error, 401, non-zero `code`, ZIP without `full.md`) returns `""` and
the next parser in the chain takes over.

> **Optional extras — what happens if you skip them.** `pip install
> xu-wiki` (no extras) only installs `PyYAML`. The `parse` / `nlp` /
> `vision` extras add `markitdown[all]` (PDF/DOCX/PPTX parsing),
> `jieba` (Chinese noun extraction for IDF), and `Pillow` (image EXIF
> for albums). **If you skip them:**
> - `parse` → `xu ingest-file --file paper.pdf` will fall back to
>   plain-text extraction (most PDFs return "" → ingest refused).
> - `nlp` → Chinese IDF degrades to character n-gram (less accurate).
> - `vision` → album EXIF reads return "—" (no GPS / resolution).
>
> Recommended: install all three extras on first install. You can
> always `pip install --upgrade "xu-wiki[parse,nlp,vision]"` later.

## Agent skill deployment

**`pip install` does NOT deploy the skill to your agent.** The CLI
writes 8 skill files to `<site-packages>/xu/skills/` (a `package_data`
directory). Each agent platform has its own skill discovery
mechanism — the agent's job is to copy these files into its own
discovery directory. `xu` provides two introspection commands so the
agent can find the source:

```bash
# Where are the skill files?
xu skills path
# → {"status": "success", "data": {"skill_name": "xu-wiki",
#     "source_dir": "/abs/path/to/site-packages/xu/skills",
#     "file_count": 8}, ...}

# What are the 8 files?
xu skills list
# → {"status": "success", "data": {"skill_name": "xu-wiki",
#     "source_dir": "...", "files": ["SKILL.md", "create.md", ...,
#     "reference/error-catalog.md", "reference/pitfalls.md"]}, ...}
```

**Important:** `xu skills path` returns the 4-key JSON envelope — the
actual path is at `data.source_dir`. An agent that tries `cp $(xu
skills path) ~/.hermes/skills/` will copy the JSON string instead of
the directory. Always parse `data.source_dir` first.

### Agent compatibility matrix

| Agent | Skill discovery dir | Install flow |
|---|---|---|
| **Hermes** | `~/.hermes/skills/xu-wiki/` | `mkdir -p` + `cp` 8 files; or use Hermes's own `skills install` if it has one |
| **Trae IDE** | `<project>/.trae/skills/xu-wiki/` (project-local) | `mkdir -p` + `cp` 8 files; reload Trae's skill index |
| **Claude Desktop** | `~/Library/Application Support/Claude/skills/xu-wiki/` (macOS); platform-dependent elsewhere | Same `mkdir` + `cp` flow; restart Claude Desktop after |
| **Cursor** | `<project>/.cursor/skills/xu-wiki/` (project-local) | Same flow; reload Cursor's skill index |
| **Other (Codex, Aider, …)** | Agent-specific — consult your agent's docs | Same `mkdir` + `cp`; the 8 files are platform-agnostic markdown |

### Copy template (bash, agent-callable)

```bash
# 1. Parse the source dir out of the JSON envelope.
SRC=$(xu skills path | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['source_dir'])")

# 2. Parse the file list out of the JSON envelope.
mapfile -t FILES < <(xu skills list | python3 -c "import sys,json; print('\n'.join(json.load(sys.stdin)['data']['files']))")

# 3. Pick the right destination per agent (Hermes shown; swap per the table above).
DEST="$HOME/.hermes/skills/xu-wiki"
mkdir -p "$DEST"
cp "${SRC}/${FILES[@]}" "$DEST/"

# 4. Verify
ls "$DEST"   # should list 8 files
```

**After deploying the skill**, restart the agent (or reload its skill
index) so `/xu-wiki <verb>` is recognised.

## Quick start

```bash
# 1. create an empty wiki
xu create --name mykb --path /abs/path/to/mykb --alias kb

# 2. ingest a document — two phases
xu ingest-file   --wiki kb --file /abs/path/to/paper.pdf --node-path papers/ml
xu ingest-commit --wiki kb --pending /abs/path/to/mykb/nodes/pending/papers__ml__paper-pre.md \
                      --title "Some Paper" --node-path papers/ml --template article

# 3. retrieve (deterministic ranking; agent supplies graded keywords)
xu query --wiki kb --core "network,learning" --expansion "training" --top-k 5
xu query --wiki kb --core "network" --neighbors      # include 1-hop relations

# 4. read one node's full body
xu read --wiki kb --uid 2026-ABCD1234

# 5. relations (50-edge LRU)
xu query-relation add  --wiki kb --from-uid <u1> --to-uid <u2> --relation-name compares_to
xu query-relation list --wiki kb --from-uid <u1>

# 6. upper layers
xu list create   --wiki kb --title "ML papers" --members <u1>,<u2> --dimension architecture
xu report create --wiki kb --title "Trend" --body "..." --references <u1>,<list_uid>

# 7. health & maintenance
xu doctor --wiki kb                 # read-only; runs all checks
xu doctor-idf --wiki kb --fix       # mechanical fixes only
xu rebuild --wiki kb --granularity keep-l1   # rebuild derived layers from L1
xu delete-node --wiki kb --uid <u> # ref-safe; --force to cascade
```

## VPS / clean-machine deployment notes

Tested flow for bringing xu-wiki up on a fresh VPS (Debian 12 / Ubuntu 22.04
as root or a normal user):

```bash
# 1. system packages (Debian/Ubuntu only)
sudo apt update && sudo apt install -y python3 python3-venv python3-pip ripgrep

# 2. install (recommended: project-local venv to avoid PEP 668)
python3 -m venv .venv
.venv/bin/pip install "xu-wiki[parse,nlp,vision]"

# 3. verify
.venv/bin/xu wikis     # lists registered wikis (empty at first)
```

Failure modes and what to check:

| symptom | likely cause |
|---|---|
| `python3 -m venv` complains about ensurepip | missing `python3-venv` (Debian/Ubuntu) |
| `pip install` fails with PEP 668 "externally-managed-environment" | use a venv (`python3 -m venv .venv`) |
| `xu` not found after install | shell PATH missing — run `hash -r` or reopen shell; for venv installs, use `.venv/bin/xu` |
| Agent can't find the skill | skill bundle not deployed by the agent's skill manager → the agent runs `xu skills path` to locate the source dir, then copies the 8 files into its own skill discovery dir |
| `/tmp` writes fail with EPERM | running inside a sandboxed shell that disallows writes outside the project tree — run from a real shell |

The CLI is **deterministic** — it never invokes an LLM or hits the network
beyond optional `markitdown` / MinerU parsing (MinerU requires an explicit API
key). No daemon, no background process; safe to run unattended.

## Ingest pipeline (the L1 closed loop)

1. **Phase 1 `ingest-file`** — parse a source file via a fallback chain
   (MinerU → markitdown → text/image). A non-empty parse result is required to
   proceed. Output lands in `nodes/pending/` as reviewable markdown. No node
   is created yet.
2. **Phase 2 `ingest-commit`** — the only write entry. It validates frontmatter,
   splits the body into ~300-line pages (header-aware with remainder rule),
   deduplicates by source hash and per-page body hash (SHA256), writes the Page
   markdown atomically, mirrors the raw file into `raws/`, records `patches`
   version 1, updates the IDF noun table, and attaches any relations.

Pass `--native "<markdown>"` to `ingest-commit` to commit hand-authored content
through the same validation path (no Phase 1 file needed).

## Query scoring

For each merged slice:

```
score = (core_weight * core_hits + expansion_weight * expansion_hits + idf_rarity)
        * density_bonus      # density_bonus > 1 applies only when >1 distinct keyword hits
```

IDF rarity comes from the `idf` table (`weight = idf_constant / (freq + 1)`).
**Fast Pass** auto-fetches the top bodies when results are few or one clearly
dominates, saving the agent a follow-up `read`. All weights live in the
wiki-internal config (`.xu/config.yaml`) and are tunable per instance.

## Physical layout

```
<wiki>/
  raws/                 # original source files, mirrored by node_path
  nodes/
    page/<node_path>/   # L1 Node_Page markdown (frontmatter + body)
    list/               # (L2 is DB-only; dir reserved)
    report/             # (L3 is DB-only; dir reserved)
    pending/            # Phase 1 parse output, deleted on commit
  .xu/
    wiki.db             # SQLite: nodes, patches, idf, relations, evidence, list_members
    config.yaml         # tunable per-instance settings
    audit.jsonl         # append-only command log
```

## Tests

```bash
.venv/bin/python tests/test_core.py     # deterministic unit tests
bash tests/e2e_verify.sh                # full M1->M5 run against sample files
```

## Command reference

| Command | Purpose |
|---------|---------|
| `create` | new empty wiki instance |
| `wikis` / `nodes` | read-only registry / node listing |
| `ingest-file` / `ingest-commit` | two-phase L1 creation |
| `query` / `read` | retrieval + full-body read |
| `query-relation add\|list` | 50-edge LRU relations |
| `list create\|show` | L2 comparison nodes |
| `report create\|show` | L3 reasoning + evidence |
| `doctor*` | health checks (`--fix` for mechanical repairs) |
| `delete-node` | ref-safe physical delete |
| `rebuild` | rebuild derived layers from L1 |
| `skills path\|list` | locate the bundled skill source dir (for the agent's skill manager) |
| `alias set\|unset\|show` | wiki registry alias management |
| `register` / `unregister` | wiki registry management |
| `config set-mineru-key\|show\|path` | global config management |
| `uninstall` | remove the xu-wiki package (CLI command — see CONST-SOP-3 for why install isn't) |
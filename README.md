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

xu-wiki is a **GitHub project, not a pre-installed brand**. The user
discovers it by reading `SKILL.md` from the GitHub URL; the agent
loads `SKILL.md` and learns how to install/uninstall. There are three
distinct install surfaces and you must keep them straight:

| Layer | What | Location decided by |
|---|---|---|
| Source repo | git clone dir (throwaway) | where you cloned it |
| Package + `xu` command | the actually-running code | pipx (or pip+venv) |
| Skill bundle | 9 markdown files for the agent | agent's discovery dir |

The recommended path uses `pipx` — one command, no venv wrangling,
PEP-668-safe on Debian/Ubuntu/Fedora/Homebrew. `pip` is supported for
the venv-willing and for environments without pipx.

### Recommended: `pipx` (one line, works on PEP 668 systems)

```bash
pipx install "xu-wiki[parse,nlp,vision] @ git+https://github.com/SadBoen/xu-wiki.git"
```

This:

1. Creates an **isolated venv** at `~/.local/share/pipx/venvs/xu-wiki/`
2. Installs the package + 3 optional extras into that venv
3. Symlinks `xu` → `~/.local/bin/xu` (already on `PATH` after
   `pipx ensurepath`)

**PEP 508 URL syntax** — note `name[extra] @ git+URL`. The
older `#egg=name[extra]` form is **deprecated** by pip and will be
rejected as `invalid-egg-fragment`.

To upgrade later (zero-migration):

```bash
pipx upgrade xu-wiki
```

### Alternative: `pip` + manual venv

If you don't have pipx (or don't want it):

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install "xu-wiki[parse,nlp,vision]"
.venv/bin/xu --version    # → "xu-wiki 0.1.0"
```

You MUST use a venv on Debian 12+, Ubuntu 23.04+, Fedora 38+, or
Homebrew Python — bare `pip install` will fail with
`error: externally-managed-environment`. If `python3 -m venv` complains
about `ensurepip`, install the OS package first
(`sudo apt install -y python3-venv` / `sudo dnf install python3-virtualenv`).

### What this single command does NOT do

- It does **not** deploy the skill bundle to your agent. That step
  needs to know which agent platform you're using — see [§Agent skill
  deployment](#agent-skill-deployment) below.
- It does **not** create or modify `~/.xu/` (the global config dir).
  That happens automatically the first time you run any `xu` command.

### Default wiki data location

Wiki data lives at whatever path you pass to `xu create --path`. The
default convention (used by INSTALL.md and the agent's
auto-suggestion) is:

```
~/Documents/xu-wikis/<wiki-name>/
```

You can override per-wiki; the convention just makes `ls` / backup
/ migration easy.

### Verify with `xu selfcheck`

After install, before doing anything else, run:

```bash
xu selfcheck
```

It returns a 4-key JSON response with three new high-signal fields:

- **`deployment_status`** — `{installer, binary_on_path, skill_deployed_to, ...}`
- **`next_actions`** — list of what's still left to do (deploy skill,
  fix permissions, etc.). Empty list = nothing left.
- **`agent_deployment_hint.copy_template_bash`** — fallback bash
  template if you prefer not to use `xu deploy skill`.

The agent uses `next_actions` to avoid declaring "install complete"
prematurely. See [§Agent skill deployment](#agent-skill-deployment)
for the full flow.

## Uninstall (run by the agent via `/xu-wiki config` → `xu uninstall` + `pipx uninstall`)

**Install and uninstall are asymmetric on purpose.** Install is just
`pip install xu-wiki` (or one `pipx install` line). Uninstall needs
its own CLI command because:

- xu-wiki is a **GitHub project**, not a pre-installed brand. The user
  discovers it by giving the agent the **GitHub URL**; the agent then
  loads `SKILL.md` and learns what xu-wiki is. Without a CLI uninstall
  command, the agent has no documented entry point.
- Uninstall is non-trivial cleanup with three independent surfaces
  (program body, skill bundle, wiki data) that need different owners.

### Three uninstall surfaces, three owners

| Surface | Owner | Why |
|---|---|---|
| Program body (`xu` binary + venv) | `pipx uninstall xu-wiki` (or `pip uninstall`) | pipx/pip track their own installs |
| Skill bundle (`~/.hermes/skills/xu-wiki/`) | the agent's skill manager | xu and pipx don't know about it |
| Wiki data (`~/.xu/` + `<wiki>` dirs) | `xu uninstall --execute --purge-*` | pipx/pip don't know about it |

`xu uninstall` **does NOT touch the program body** in a pipx-managed
install — it detects the pipx venv and refuses to call
`pip uninstall`, instead returning `next_action: "pipx uninstall
xu-wiki"` for the agent to run separately. This split is enforced:

- **pipx users**: `xu uninstall` cleans `~/.xu/` + wikis; you must
  separately run `pipx uninstall xu-wiki` to remove the program.
- **pip+venv users**: `xu uninstall --execute` does everything
  (pip uninstall + optional purge).

### The agent's complete uninstall flow

```bash
# 1. Dry-run first (always). Detect installer from the response.
xu uninstall
# → data.installer ∈ {"pipx", "pip", "unknown"}
# → data.plan with wikis_found, global_dir, etc.
# → data.next_actions might suggest "pipx uninstall xu-wiki"

# 2. Tell the user what will happen. Pick scope:
#    (a) data layer only (--purge-wikis --purge-config):  wikis + ~/.xu/
#    (b) program body (pipx uninstall OR pip uninstall via xu)
#    (c) everything: (a) + (b) in order
# Default = (a) only — preserves the program; user can re-run later.

# 3a. If installer == "pipx": program body goes through pipx
xu uninstall --execute --purge-wikis --purge-config   # data layer
pipx uninstall xu-wiki                                # program body

# 3b. If installer == "pip": program body goes through xu's pip call
xu uninstall --execute --purge-wikis --purge-config   # everything

# 4. Skill bundle: the agent's skill manager, not xu/pipx
rm -rf ~/.hermes/skills/xu-wiki        # Hermes
# (other agents: see §Agent skill deployment above)

# 5. INDEPENDENT VERIFICATION — never trust the tool's self-report
command -v xu || echo "OK: xu removed"
test -e ~/.xu && echo "FAIL" || echo "OK: ~/.xu removed"
test -e ~/.hermes/skills/xu-wiki && echo "FAIL" || echo "OK: skill removed"
```

### Why `xu uninstall` doesn't run `pip uninstall` in pipx context

`pip uninstall` inside a pipx-managed venv is **undefined behavior**:
pipx tracks installs in its own JSON registry
(`~/.local/share/pipx/venvs/xu-wiki/pipx_metadata.json`), and a
bare `pip uninstall` would remove the package from the venv without
notifying pipx, leaving a "ghost" venv that pipx still thinks owns
the install. The fix is `pipx uninstall`, which both removes the
package AND cleans up the venv + symlink.

`xu uninstall` detects this context (`sys.prefix` under
`/pipx/venvs/`) and refuses to act on the program body. The
`--purge-wikis` and `--purge-config` flags still work — those are
pipx-unconcerned.

### What's NOT in this SOP

There is **no `/xu-wiki install` slash command and no
`/xu-wiki upgrade` slash command**. Install is `pipx install` /
`pip install` (run by the agent's bash tool, not the CLI). Upgrade is
`pipx upgrade xu-wiki` / `pip install --upgrade
"xu-wiki[parse,nlp,vision]"`.

There is also **no `/xu-wiki uninstall` slash command** — the entry
is `/xu-wiki config`, which contains `xu uninstall` as a CLI palette
item. See [CONST-SOP-3] in `design-docs/08-sop-architecture.md` and
SKILL.md hard rule 0a.

> **What the CLI does NOT do for install / uninstall**: see the
> `## Uninstall` section above for the responsibility split between
> `pipx` (program body), the agent's skill manager (skill bundle),
> and `xu uninstall` (wiki data). The CLI never touches venv / symlink
> / system PATH on its own.

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
writes 9 markdown files (SKILL.md + 5 SOPs + 2 reference + INSTALL.md)
to `<site-packages>/xu/skills/` as `package_data`. Each agent
platform has its own skill discovery directory layout — the agent's
job is to copy these files into it.

The recommended way is `xu deploy skill --target <agent>`. The
manual `cp -r` fallback is documented at the end of this section
for environments where `xu` isn't on PATH yet.

### Recommended: `xu deploy skill`

```bash
xu deploy skill --target hermes      # → ~/.hermes/skills/xu-wiki/
xu deploy skill --target trae        # → <cwd>/.trae/skills/xu-wiki/  (project-local)
xu deploy skill --target claude      # → ~/Library/Application Support/Claude/skills/xu-wiki/  (macOS only)
xu deploy skill --target cursor      # → <cwd>/.cursor/skills/xu-wiki/  (project-local)
xu deploy skill --target auto        # probe existing agent dirs, deploy to first match
```

`auto` resolves to whichever target's PARENT directory already
exists on the machine — meaning the agent is installed there. If
none match, `auto` falls back to `hermes` (most common).

The command handles three things the manual flow got wrong:

1. **Subdir preservation** — each file in the curated
   `ALL_SKILL_FILES` list is copied to `$DEST/<relative-path>`, so
   `reference/error-catalog.md` lands at
   `$DEST/reference/error-catalog.md` (not flattened).
2. **Python-artifact filter** — the source dir is a regular Python
   package, so a naive `cp -r` would copy `__init__.py` and
   `__pycache__/` into the agent's discovery dir. `xu deploy skill`
   uses the same curated list that `xu skills list` returns (which
   already excludes these artifacts).
3. **Built-in target → discovery-dir mapping** — no need to look up
   the matrix below.

After `xu deploy skill`, **reload the agent's skill index / restart
the agent** so it picks up the new files.

### Introspection helpers

```bash
# Where are the 9 skill files?
xu skills path
# → {"status": "success", "data": {"skill_name": "xu-wiki",
#     "source_dir": "/abs/path/to/site-packages/xu/skills",
#     "file_count": 9}, ...}

# What are the 9 files?
xu skills list
# → {"status": "success", "data": {"skill_name": "xu-wiki",
#     "source_dir": "...", "files": ["SKILL.md", "create.md", ...,
#     "reference/error-catalog.md", "reference/pitfalls.md",
#     "INSTALL.md"]}, ...}
```

**Important:** `xu skills path` returns the 4-key JSON envelope —
the actual path is at `data.source_dir`. An agent that tries
`cp $(xu skills path) ~/.hermes/skills/` will copy the JSON string
instead of the directory. Always parse `data.source_dir` first.

### Agent compatibility matrix

| Agent | Skill discovery dir |
|---|---|
| **Hermes** | `~/.hermes/skills/xu-wiki/` |
| **Trae IDE** | `<project>/.trae/skills/xu-wiki/` (project-local) |
| **Claude Desktop** | `~/Library/Application Support/Claude/skills/xu-wiki/` (macOS only) |
| **Cursor** | `<project>/.cursor/skills/xu-wiki/` (project-local) |
| **Other (Codex, Aider, …)** | Agent-specific — consult your agent's docs. Same 9 files apply. |

### Manual fallback (only if `xu` isn't on PATH yet)

If for some reason `xu deploy skill` isn't available, fall back to:

```bash
SRC=$(xu skills path | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['source_dir'])")
DEST="$HOME/.hermes/skills/xu-wiki"
mkdir -p "$DEST"
rm -rf "$DEST"/*                                  # clean stale files
# Copy each file individually (preserves reference/ subdir)
cp "$SRC"/SKILL.md "$SRC"/create.md "$SRC"/ingest.md "$SRC"/query.md \
   "$SRC"/doctor.md "$SRC"/config.md "$SRC"/INSTALL.md "$DEST"/
cp "$SRC"/reference/*.md "$DEST/reference/"
ls "$DEST" && ls "$DEST/reference"
```

**Don't use `cp -r "$SRC/." "$DEST/"`** as the primary flow: it
copies `__init__.py` and `__pycache__/` from the source Python
package into the agent's discovery dir. The per-file `cp` above
excludes them by construction.

**After deploying the skill**, restart the agent (or reload its
skill index) so `/xu-wiki <verb>` is recognised.

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
    list/               # L2 Node_List markdown (frontmatter + comparison table)
    report/             # L3 Node_Report markdown (frontmatter + body)
    pending/            # Phase 1 parse output, deleted on commit
  .xu/
    wiki.db             # SQLite: nodes, patches, idf, relations
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
| `skills path\|list` | locate the bundled skill source dir (Python artifacts filtered); for agent's skill manager |
| `deploy skill --target <agent>` | one-step copy of the 9-file bundle to the agent's discovery dir (replaces hand-rolled `cp -r`) |
| `alias set\|unset\|show` | wiki registry alias management |
| `register` / `unregister` | wiki registry management |
| `config set-mineru-key\|show\|path` | global config management |
| `uninstall` | remove the xu-wiki package (CLI command — see CONST-SOP-3 for why install isn't) |
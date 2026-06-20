# xu-wiki

A relation-driven, three-layer wiki engine for AI agents. The CLI is fully
deterministic and never calls an LLM — semantic judgement stays with the agent,
ranking and storage stay with the engine.

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

```bash
pip install "xu-wiki[parse,nlp,vision]"
```

That single command installs:

- the `xu` CLI binary (placed on `PATH` by pip, like any Python tool)
- the bundled skill source (8 files under `<site-packages>/xu/skills/`)
- the 3 optional parser groups

To **uninstall**:

```bash
pip uninstall xu-wiki
```

That's it — no `xu install`, no `xu uninstall`, no separate `install.sh`,
no venv management, no symlink config. Pip handles all of it.

Set `XU_HOME` to relocate the global config / registry directory (defaults to
`~/.xu`).

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
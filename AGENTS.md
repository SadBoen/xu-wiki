# xu-wiki Agent Instructions

## Project Overview

Relation-driven three-layer wiki engine for AI agents. Python CLI, fully deterministic — no LLM calls.

## Install

```bash
pipx install "xu-wiki[parse,nlp,vision] @ git+https://github.com/SadBoen/xu-wiki.git"
```

## Developer Commands

```bash
.venv/bin/python tests/test_core.py       # unit tests
bash tests/e2e_verify.sh                 # end-to-end M1->M5 run
```

## Architecture

- Package: `src/xu/`
- Entry point: `xu` command (via `xu.cli:main`)
- 4-key JSON envelope on every command: `{status, data, message, hints}`
- L1 nodes are **immutable** — revisions go through `patches` table
- Ingest is **two-phase**: `ingest-file` (parse, output to `nodes/pending/`) → `ingest-commit` (write)

## Skill Deployment

```bash
xu deploy skill --target <agent>   # auto, hermes, trae, claude, cursor
```

## Key Constraints

- `rg` (ripgrep) must be on PATH; pure-Python fallback used if absent
- Debian/Ubuntu: `sudo apt install -y python3-venv` required before pipx/venv
- Wiki data default: `~/Documents/xu-wikis/<wiki-name>/`
- Never commit: `.venv/`, `test-wikis/`, `CREDENTIALS*.md`

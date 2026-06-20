# xu-wiki Agent Instructions

## Project Overview

Relation-driven three-layer wiki engine for AI agents. Python CLI, fully deterministic — no LLM calls.

## Developer Commands

```bash
python3 -m pytest tests/              # unit tests (pyenv 3.14.5)
bash tests/e2e_verify.sh              # end-to-end M1->M5 run
```

## Architecture

- Package: `src/xu/`
- Entry point: `xu` command (via `xu.cli:main`)
- 4-key JSON envelope on every command: `{status, data, message, hints}`
- L1 nodes are **immutable** — revisions go through `patches` table
- Ingest is **two-phase**: `ingest-file` (parse → system temp dir) → `ingest-commit` (atomic write, only write entry)

## Skill Deployment

```bash
xu deploy skill --target <agent>   # hermes, trae, claude, cursor, auto
```

## Key Constraints

- `rg` (ripgrep) must be on PATH; pure-Python fallback used if absent
- Wiki data is **NEVER deleted** by uninstall under any circumstances — hard invariant (BAN-UNINST-1)
- Never commit: `.venv/`, `test-wikis/`, `CREDENTIALS*.md`

## Uninstall is a 2-surface operation

**Wiki data is NEVER deleted. No flag, no branch, no surface ever touches it.**

| Surface | Owner | How |
|---|---|---|
| Skill bundle (`~/.local/share/xu-wiki/skills/<target>/`) | **xu CLI** | `xu uninstall --execute` reads manifest and removes each deployed target |
| Program body (`xu` binary + venv) + `~/.xu-wiki/` config | **xu CLI** | `xu uninstall --execute` handles pip/pipx + config dir |

**Forbidden**:
- ❌ Running `pipx uninstall xu-wiki` as a separate step
- ❌ Manually deleting skill bundle directories
- ❌ Any flow that deletes wiki data, even with `--purge-wikis`

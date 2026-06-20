# xu-wiki Agent Instructions

## Project Overview

Relation-driven three-layer wiki engine for AI agents. Python CLI, fully deterministic — no LLM calls.

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

## Uninstall is a 3-surface operation

Uninstall handles three surfaces. **Never do any of these manually:**

- **Program** (pipx/pip-managed): `xu uninstall --execute` handles this internally — do NOT run `pipx uninstall` separately.
- **Skill bundle** (`~/.hermes/skills/xu-wiki/`, etc.): `xu uninstall` reads the manifest at `~/.local/share/xu-wiki/manifest.json` and removes each deployed target — do NOT delete skill directories manually.
- **Config / wiki data**: `~/.xu/` is removed by default (`--preserve-config` to keep it). Wiki data is **NEVER deleted** under any circumstances — this is a hard invariant.

**Forbidden**:
- ❌ Running `pipx uninstall xu-wiki` as a separate step
- ❌ Manually deleting `~/.hermes/skills/xu-wiki/`
- ❌ Any flow that deletes wiki data, even with `--purge-wikis`


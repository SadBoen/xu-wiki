# xu-wiki Agent Instructions

## Project Overview

Relation-driven wiki engine for AI agents: Page (knowledge) + Entity/List/Report (learning). Python CLI, fully deterministic — no LLM calls.

## Developer Commands

```bash
# Lint / typecheck / test (CI order: lint -> typecheck -> test)
ruff check src/
mypy src/
python3 -m pytest tests/

# Unit tests only
python3 -m pytest tests/ -q

# End-to-end M1->M6 run (requires .venv; sample files at design-docs/测试用样例文件/)
.venv/bin/xu create ...     # bootstrap .venv first: pip install -e ".[parse,vision]"
# or run via the wrapper script that manages .venv internally:
bash tests/e2e_verify.sh

# Local pre-commit hooks (also run in CI)
pre-commit run --all-files
```

**CI pipeline**: `ruff check` → `mypy` → `pytest` on Python 3.10–3.13. Pre-commit (`ruff --fix` + `ruff-format`) runs alongside lint in CI.

## Architecture

- Package: `src/xu/`
- Entry point: `xu` command (via `xu.cli:main`)
- 4-key JSON envelope on every command: `{status, data, message, hints}`
- Page nodes are **immutable** — revisions go through `patches` table
- Ingest is **two-phase**: `ingest-file` (parse → system temp dir) → `ingest-commit` (atomic write, only write entry)

## Node Types

| Type | Storage | Key Rule |
|---|---|---|
| Page | `nodes/page/*.md` | Immutable, SHA256 dedup, revisions via `patches` |
| List | `nodes/list/*.md` | Members via frontmatter `members` list |
| Report | `nodes/report/*.md` | **≥1 evidence Page required**, no naked reports |
| Entity | `nodes/entity/*.md` | First-class nodes |

## Key Constraints

- `rg` (ripgrep) must be on PATH; pure-Python fallback used if absent
- Wiki data is **NEVER deleted** by uninstall — hard invariant (BAN-UNINST-1)
- Never commit: `.venv/`, `test-wikis/`, `CREDENTIALS*.md`, `target/`, `.trae/`, `.mimocode/`

## Skill Deployment

```bash
xu deploy skill --target <agent>   # hermes, trae, claude, cursor, auto
xu selfcheck                       # verify install is complete
xu update                          # upgrade xu-wiki + re-deploy skills to all manifest targets
xu update --check                  # only check if update is available
xu update --no-redeploy            # upgrade pip package only, skip skill re-deploy
```

Skill files are in `src/xu/skills/` (SKILL.md + references/).

## Uninstall is a 2-surface operation

**Wiki data is NEVER deleted. No flag, no branch, no surface ever touches it.**

| Surface | Owner | How |
|---|---|---|
| Skill bundle (`~/.local/share/xu-wiki/skills/<target>/`) | **xu CLI** | `xu uninstall --execute` reads manifest and removes each deployed target |
| Program body (`xu` binary + venv) + `~/.xu-wiki/` config | **xu CLI** | `xu uninstall --execute` handles pip/pipx + config dir |

**Forbidden**:
- ❌ Running `pipx uninstall xu-wiki` as a separate step
- ❌ Manually deleting skill bundle directories
- ❌ Any flow that deletes wiki data

## Design Docs

Architecture decisions are in `design-docs/` — notably `01-wiki-architecture.md` and `08-sop-architecture.md`. The SKILL.md in `src/xu/skills/` is the agent-facing skill entry (installed via `xu deploy skill`), not the same as this file.

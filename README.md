# xu-wiki

A relation-driven, three-layer wiki engine for AI agents. The CLI is fully
deterministic and never calls an LLM — semantic judgement stays with the agent,
ranking and storage stay with the engine.

> **Who reads this README**: an AI agent loading `SKILL.md` to invoke `xu`
> subcommands. **Not** the end user. The end user talks to the agent through
> a chat UI; the agent does the calling.

## Concept

Knowledge is organized in three layers plus a relation graph:

| Layer | Name | Storage | Purpose |
|---|---|---|---|
| L1 | Node_Page | `.md` + SQLite index | Immutable fact slices (the source of truth) |
| L2 | Node_List | `.md` only | Comparison / aggregation over existing nodes |
| L3 | Node_Report | `.md` only | Reasoning + conclusion with an evidence chain |

Every node carries an ordered, capped (50) **LRU relation list** — no categories,
no scores. The CLI is **offline-first**: optional MinerU API key for PDF parsing;
everything else works without network.

Every command returns a **4-key JSON envelope**: `{status, data, message, hints}`.

## Requirements

- Python 3.12+
- `ripgrep` (optional; pure-Python fallback used if absent)
- MinerU API key (optional; only needed if `markitdown` is insufficient for PDFs)

## Install

```bash
# recommended — one line, PEP 668-safe
pipx install "xu-wiki[parse,nlp,vision] @ git+https://github.com/SadBoen/xu-wiki.git"

# alternative — project-local venv
python3 -m venv .venv && .venv/bin/pip install "xu-wiki[parse,nlp,vision]"
```

After install, the agent deploys the skill bundle:

```bash
xu deploy skill --target <agent>   # hermes, trae, claude, cursor, ...
```

Verify:

```bash
xu selfcheck   # checks program body + skill deployment + config
```

## Uninstall

Handled in two steps — the **agent self-removes** the skill bundle, then the
**agent calls `xu`** to remove the program:

1. Agent deletes `~/.hermes/skills/xu-wiki/` using its own skill manager.
2. Agent runs:

```bash
xu uninstall --execute          # pipx → then: pipx uninstall xu-wiki
xu uninstall --execute          # pip  → removes program + preserves wiki data
```

Wiki data (your knowledge) is **never deleted** by the uninstall flow.

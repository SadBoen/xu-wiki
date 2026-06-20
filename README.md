# xu-wiki

A relation-driven, three-layer wiki engine for AI agents. The CLI is fully
deterministic and never calls an LLM — semantic judgement stays with the agent,
ranking and storage stay with the engine.

## Two documents, two scopes

| | README (this file) | SKILL.md |
|---|---|---|
| **When** | You are installing xu-wiki | You have xu-wiki installed and want to use it |
| **Who reads it** | You (the agent) before install | The agent after install |
| **What** | Install + Uninstall | Every command detail |

## Concept

Knowledge is organized in three layers plus a relation graph:

| Layer | Name | Storage | Purpose |
|---|---|---|---|
| L1 | Node_Page | `.md` + SQLite index | Immutable fact slices (source of truth) |
| L2 | Node_List | `.md` only | Comparison / aggregation over existing nodes |
| L3 | Node_Report | `.md` only | Reasoning + conclusion with an evidence chain |

Every node carries an ordered, capped (50) **LRU relation list** — no categories,
no scores. Every command returns a **4-key JSON envelope**: `{status, data, message, hints}`.

## Install (Linux / macOS)

One command. Works on both Linux and macOS, PEP 668-safe:

```bash
pipx install "xu-wiki[parse,nlp,vision] @ git+https://github.com/SadBoen/xu-wiki.git"
```

After install, the agent deploys the skill bundle:

```bash
xu deploy skill --target <agent>   # hermes, trae, claude, cursor, ...
```

Verify:

```bash
xu selfcheck
```

## Uninstall

Two steps:

1. Agent deletes `~/.hermes/skills/xu-wiki/` using its own skill manager.
2. Agent runs:

```bash
xu uninstall --execute          # removes the program
pipx uninstall xu-wiki         # (only if pipx was used)
```

**Wiki data is never deleted.** The uninstall flow only touches the program
itself — your knowledge stays intact.

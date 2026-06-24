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
pipx install "xu-wiki[pdf,parse,nlp,vision] @ git+https://github.com/SadBoen/xu-wiki.git"
```

**What each extra provides** (install all four — all required for full SOP coverage):

| Extra | Packages | Required for |
|---|---|---|
| `pdf` | `pypdf`, `pdfplumber` | PDF text extraction |
| `parse` | `markitdown[all]` | DOCX / PPTX text extraction |
| `nlp` | `jieba` | Chinese query segmentation |
| `vision` | `Pillow>=10.0` | Image EXIF metadata for albums |

**Missing any extra → `MissingExtra` error at first use, no silent fall-back.**

After install, deploy the skill bundle:

```bash
xu deploy skill --target <agent>   # hermes, trae, claude, cursor, ...
xu selfcheck                       # verify install is complete
```

To deploy to multiple harnesses:

```bash
xu deploy skill --target hermes --target claude --target cursor
```

## Uninstall

**Default scope — never touches wiki data or `~/.xu-wiki/` config.**

**Default removes**: pip/pipx package + skill bundle at target. Wiki data and `~/.xu-wiki/` are **never touched**.

Multiple targets in one call:

```bash
xu uninstall --target hermes --target claude --execute
```

The uninstall plan is always shown first (dry-run). Pass `--execute` to apply.

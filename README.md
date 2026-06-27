# xu-wiki

A relation-driven wiki engine for AI agents. The CLI is fully deterministic
and never calls an LLM — semantic judgement stays with the agent, ranking and
storage stay with the engine.

> **Note:** `AGENTS.md` is a local IDE instruction file — **do not read it**
> during install. It is for the IDE's own agent use only.

## Two documents, two scopes

| | README (this file) | SKILL.md |
|---|---|---|
| **When** | You are installing xu-wiki | You have xu-wiki installed and want to use it |
| **Who reads it** | You (the agent) before install | The agent after install |
| **What** | Install + Uninstall | Every command detail |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      AI Agent                           │
│         (semantic judgement, multi-round decisions)     │
└─────────────────┬───────────────────────────────────────┘
                  │ JSON {status, data, message, hints}
                  ▼
┌─────────────────────────────────────────────────────────┐
│                      xu CLI                             │
│     query · expand · read · nodes · list · report     │
│                                                         │
│  Page ──▶ Immutable .md + SHA256 dedup                │
│  List ──▶ YAML members in frontmatter                  │
│  Report ──▶ Evidence chain required                     │
│  Entity ──▶ First-class node                            │
│                                                         │
│  50-edge LRU relation graph per node                    │
└─────────────────────────────────────────────────────────┘
```

**Node types:**

| Type | Storage | Purpose |
|---|---|---|
| Page | `nodes/page/*.md` | Immutable fact slices — revisions via `patches` table |
| List | `nodes/list/*.md` | Comparison / aggregation over existing nodes |
| Report | `nodes/report/*.md` | Reasoning + conclusion — **≥1 evidence ref required** |
| Entity | `nodes/entity/*.md` | First-class entity nodes |

**Key constraints:**
- Page is immutable — edits go through `patches` table, never rewrite the file
- 50-edge LRU per node — no category, no score; hit → promote in list
- CLI is fully offline — **never calls an LLM**
- Every command returns **`{status, data, message, hints}`** (4-key JSON envelope)

## Quickstart (5 minutes)

```bash
# 1. Install
pipx install "xu-wiki[pdf,parse,nlp,vision] @ git+https://github.com/SadBoen/xu-wiki.git"

# 2. Create a wiki
xu create --name my-wiki --path ~/wikis/my-wiki --alias mine

# 3. Ingest content
xu ingest-commit --wiki mine --title "Python Intro" \
  --native "Python is a high-level programming language." \
  --source "https://python.org"

# 4. Query (agent calls this — CLI never interprets free text)
xu query --wiki mine --keywords "Python,programming,language"

# 5. Expand selected UIDs to get full bodies + relations
xu expand --wiki mine --uids <uid1>,<uid2>

# 6. Deploy skill for your agent
xu deploy skill --target claude
xu selfcheck
```

## Install (Linux / macOS)

PEP 668-safe, one command:

```bash
pipx install "xu-wiki[pdf,parse,nlp,vision] @ git+https://github.com/SadBoen/xu-wiki.git"
```

**Optional extras:**

| Extra | Packages | Required for |
|---|---|---|
| `pdf` | `pypdf`, `pdfplumber` | PDF text extraction |
| `parse` | `markitdown[all]` | DOCX / PPTX text extraction |
| `nlp` | `jieba` | Chinese query segmentation |
| `vision` | `Pillow>=10.0` | Image EXIF metadata for albums |

**Missing any extra → `MissingExtra` error at first use, no silent fall-back.**

After install, deploy the skill bundle:

```bash
xu deploy skill --target <agent>   # hermes, trae, claude, cursor, auto (default: auto)
xu selfcheck                       # verify install is complete
```

## Uninstall

**Default scope — never touches wiki data or `~/.xu-wiki/` config.**

**Default removes**: pip/pipx package + skill bundle at target. Wiki data and `~/.xu-wiki/` are **never touched**.

Multiple targets in one call:

```bash
xu uninstall --target hermes --target claude --execute
```

The uninstall plan is always shown first (dry-run). Pass `--execute` to apply.

## Comparison

| | xu-wiki | Notion | Obsidian | Logseq |
|---|---|---|---|---|
| **AI agent CLI** | ✅ Native JSON + SOP | ❌ | ❌ | ❌ |
| **Page immutable** | ✅ patches table | ❌ | ❌ (file-level only) | ❌ |
| **50-edge LRU graph** | ✅ O(1), no explosion | ❌ | ❌ | ❌ |
| **Offline / no LLM calls** | ✅ | ❌ | ✅ | ✅ |
| **git-versioned wiki** | ✅ pure `.md` + frontmatter | ❌ | ✅ | ✅ |
| **Page/List/Report/Entity** | ✅ | ❌ | ❌ | ❌ |
| **DB lock-free** | ✅ | ❌ | N/A | N/A |

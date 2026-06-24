---
name: "xu-wiki"
description: "Operate xu-wiki three-layer knowledge base via 5 SOPs (create/ingest/query/doctor/config) on a deterministic CLI. Manage 50-edge LRU, Node_List (L2), Node_Report (L3)."
---

# xu-wiki

xu-wiki is a **relation-driven three-layer knowledge base** designed for AI
agents. It exposes a deterministic offline-first CLI; this skill is the
authoritative invocation guide for the agent side.

## Naming conventions

| Name | What it is | Where you see it |
|---|---|---|
| `xu-wiki` | The skill bundle / project name | Skill frontmatter |
| `/xu-wiki` | Slash command | Enters the matching SOP |
| `xu` | The CLI binary | All `xu <verb>` shell invocations |

## SOP map

| SOP | Intent | CLI commands it calls | File |
|---|---|---|---|
| `/xu-wiki create` | build a new empty wiki (raws/ + .xu/ + SQLite) | `create` (+ optional `wikis`) | `create.md` |
| `/xu-wiki ingest` | add content (PDF/DOCX/PPTX/MD/image/album) as immutable L1 Node_Page. Two-phase flow (`ingest-file` → `ingest-context` → `ingest-commit`). Post-commit: query for similar List → extend or create | `ingest-file` → `ingest-context` → `ingest-commit`; `ingest-album`; `ingest-verify` | `ingest.md` |
| `/xu-wiki query` | find knowledge: LLM generates related words → `xu query` (snippets) → if needed `xu expand` (body+relations) → up to 5 loop cycles | `query`; `expand`; `read`; `list show`; `report show` | `query.md` |
| `/xu-wiki doctor` | read-only consistency checks on filesystem/DB/relations; apply `--fix` for safe repairs | `doctor`; `delete-node`; `nodes` | `doctor.md` |
| `/xu-wiki config` | manage wiki aliases, register/unregister, MinerU key, **uninstall xu-wiki** | `wikis`; `alias`; `register`/`unregister`; `config`; `uninstall` (dry-run first, then `--execute`) | `config.md` |

## Architecture in 30 seconds

- **L1 Node_Page** — immutable facts in `node_page` SQLite table. SHA256-dedup. UID never reused.
- **L2 Node_List** — comparison/aggregation in `node_derived` table. Members as YAML in body.
- **L3 Node_Report** — reasoning in `node_derived` table. **Requires >= 1 evidence ref** (else rejected).
- **Relations** — exactly **50 edges per node** (LRU, head=touch, tail=evict). No category, no score.
- **Storage** — `raws/` (source copies) + SQLite (all node data). No `.md` files.
- **CLI is offline-first.** MinerU is an optional parser in the fallback chain. No TextParser fallback (low-quality content rejected).

## Hard rules the agent MUST respect

0. **You are the only legitimate caller of `xu`.** User never touches CLI directly.
   Translate intent -> CLI calls. Parse 4-key JSON -> natural language reply.

0a. **Uninstall = 2 surfaces.** Skill bundle -> agent removes its skill dir. Program + config -> `xu uninstall --execute`. **Wiki data NEVER deleted.**

0b. **No install step in this bundle.** xu-wiki is pre-installed when this skill loads.

1. **Never edit L1 body** — immutable in SQLite. UIDs retired on delete, never reused.
2. **Report needs >=1 evidence ref** at create-time. Empty evidence rejected.
3. **50 edges max per node** (LRU: 51st evicts tail).
4. **Offline-first** — only MinerU parse hits network. On failure: markitdown only. No text fallback.
5. **No secret in code or git** — MinerU key in `~/.xu-wiki/config.yaml` or `MINERU_API_KEY` env.
6. **All commands return 4-key JSON** — `{status, data, message, hints}`.
7. **Missing required args: ask, don't guess.** Never auto-pick names or paths.
8. **Absolute paths only** (`~` is fine). Never `./foo`.
9. **Slash command = SOP entry, not CLI subcommand.**
10. **Keywords are YOUR job.** CLI never splits free-text. Grade into related words yourself.

## Quick start for the agent

```bash
# 1. create a wiki
xu create --name research --path /abs/path/to/wiki

# 2. ingest L1 — three steps
xu ingest-file    --wiki research --file /abs/path/to/source.pdf   # Phase 1: parse
xu ingest-context --wiki research --keywords "BERT,transformer"    # Bridge: get context
# Agent decides title, raw_path, relations from context, then:
xu ingest-commit  --wiki research --pending /tmp/... --title "BERT" --raw-path "papers/bert"

# 3. query — LLM-driven loop
xu query  --wiki research --core "transformer,attention" --expansion "encoder,self-attention"
# Agent reads snippets, if needed:
xu expand --wiki research --uids "A001,B002"

# 4. wire relations
xu query-relation add --wiki research --from-uid A001 --to-uid B002 --relation-name cites

# 5. L2 / L3
xu list   create --wiki research --title "Transformer Models" --members "A001,B002" --dimension "by-year"
xu report create --wiki research --title "Survey" --references "A001,B002" --body "## findings"
```

## Reading the response

Every command prints one JSON object to stdout. `hints` is for you, not the user.

```json
{"status": "success", "data": {"uid": "ABCD1234", "title": "BERT"},
 "message": "read complete", "hints": ["query-relation list --from-uid ..."]}
```

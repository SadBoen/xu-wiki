---
name: "xu-wiki"
description: "Relation-driven three-layer wiki. Deterministic CLI. 50-edge LRU."
---

# xu-wiki

Three names, never mix:
- `/xu-wiki` = slash command -> enters SOP
- `xu` = CLI binary -> `xu <verb>`
- `xu-wiki` = project name

## ⚠️ If you are an agent reading this

You are looking at the skill bundle that was installed by **`xu skills
install`**. If you got here through some other path (e.g. by `cat`ing
`SKILL.md` directly, or by reading the wheel's package data), you should
also make sure the bundle is deployed to the agent's skill directory:

```bash
xu skills install
xu skills path    # see where the source lives
xu skills list    # see what files are bundled
```

Without this, subsequent sessions may not pick up the slash commands or
the SOP map below.

## SOP map

| Slash command | Intent | CLI | File |
|---|---|---|---|
| `/xu-wiki create` | new empty wiki | `xu create` | create.md |
| `/xu-wiki ingest` | add L1 pages from files | `xu ingest-file` -> `xu ingest-context` -> `xu ingest-commit` | ingest.md |
| `/xu-wiki query` | search + read | `xu query` -> (if needed) `xu expand` | query.md |
| `/xu-wiki doctor` | health checks | `xu doctor` | doctor.md |
| `/xu-wiki config` | registry, uninstall | `xu uninstall`, `xu alias`, `xu wikis` | config.md |

## Hard rules

1. Never edit L1 body. Immutable in SQLite.
2. All writes go through CLI. Never touch SQLite directly.
3. Missing required args -> ask user. Never guess paths or names.
4. Absolute paths only (`~` OK, `./foo` refused).
5. Every CLI call returns `{status, data, message, hints}`.
6. Keywords are YOUR job. CLI never splits free-text.
7. 50 relation edges max per node (LRU).
8. Report needs >=1 evidence ref. Empty = rejected.
9. Wiki data NEVER deleted by uninstall.
10. Parser chain: MinerU -> markitdown. Both fail = reject.

## Architecture

```
node_page   — L1 immutable facts (ingested)
node_derived — L2 List + L3 Report (curated)
patches     — L1 revisions
relations   — 50-edge LRU
```

All data in SQLite. No .md files. Source copies in `raws/`.

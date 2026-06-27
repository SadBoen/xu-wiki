# create — build a new empty wiki

`/xu-wiki create` is the **only** way to mint a brand-new wiki. It writes the
empty template (raws/, nodes/{page,list,report}/, .xu/) at an absolute
path and registers the wiki. The CLI is **fail-loud on safety**: if the path
already holds user content, it refuses rather than overwriting.

This file is **self-contained**. All cross-cutting rules
(Page immutability, 4-key JSON, missing-args policy, paths-must-be-absolute) live
in `SKILL.md` and are referenced when needed, not duplicated here.

## CLI palette

```bash
xu create --name <n> --path <abs> [--alias <a>]
```

| Flag | Required | Purpose |
|---|---|---|
| `--name` | yes | Wiki's registry key (lowercase, must be unique) |
| `--path` | yes | Absolute directory for the new wiki. `~` is fine; relative is refused |
| `--alias` | no | Short alias for quick `--wiki <alias>` reference |

## Workflow

1. **Verify required args first** (rule 8 in `SKILL.md`). If the user said
   "create a wiki" without a path, **ask** — never guess a path that might
   already hold user content.
   2. **Confirm the path is empty or doesn't exist.** The CLI runs
   internally; a non-empty path returns `PathNotEmpty` with the offending
   entries listed in `data.conflicting`.
3. **Invoke `create`.** It writes the template, registers the wiki under
   `--name`, optionally with `--alias`.
4. **(Optional) Verify with `wikis`** — listed in `config.md` since it
   belongs to the config SOP, but reachable from any context. **Do not**
   link to it from here; tell the user to confirm via `SKILL.md §SOP map`
   or run it.

## Example

```bash
xu create --name research --path /Users/agent/Wikis/research --alias r
# → {"status": "success", "data": {"name": "research", "path": "...", "alias": "r"}, ...}
```

## Common pitfalls

- **Guessed path** — the single most common agent accident. If the user
  said "create a wiki" without saying where, **ask**. The CLI will refuse
  the result anyway, but the round-trip wastes time.
- **Relative path** — `./foo` is rejected at parse time. Always expand to
  absolute, or pass `~/...` directly (the CLI calls `Path.expanduser`).
- **Name collision** — `--name` must be unique in the global registry. On
  collision, the CLI returns `NameConflict` with the existing entry's path.
- **Want to register an EXISTING directory** — that's the `register` CLI
  in the config SOP, not `create`. `create` is for fresh empty wikis only.

## Cross-references

- Cross-cutting rules (paths, missing-args, JSON shape) → `SKILL.md §Hard rules`
- The `wikis` command (to verify) → `SKILL.md §SOP map` (config SOP)
- Registration of an existing directory → `SKILL.md §SOP map` (config SOP)


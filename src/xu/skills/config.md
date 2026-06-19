# config — manage configuration (and software lifecycle)

`/xu-wiki config` is the SOP for **everything that isn't wiki data**:
registering / aliasing / unregistering wikis, managing the MinerU API key,
inspecting the global state, and software lifecycle (`install` /
`uninstall`). It does not touch L1/L2/L3 content.

This file is **self-contained** (PRIN-SKILL-1). Cross-cutting rules
(4-key JSON, missing-args) live in `SKILL.md`; the safety rules for
register / unregister / install / uninstall are stated here.

## CLI palette

```bash
# Inspect registered wikis (read-only)
xu-wiki wikis

# Wiki registry: alias, register, unregister
xu-wiki alias set     --wiki <w> --alias <new>     # set or change alias
xu-wiki alias unset   --wiki <w>                   # remove alias
xu-wiki alias show    --wiki <w>                   # show current alias
xu-wiki register      --name <n> --path <abs> [--alias <a>]   # register EXISTING dir (no files written)
xu-wiki unregister    --name <n>                   # remove from registry (wiki files NOT touched)

# Global config (MinerU key etc.)
xu-wiki config set-mineru-key                       # reads from MINERU_API_KEY env (safer than --key)
xu-wiki config show                                 # global config (secrets masked)
xu-wiki config path                                 # global config file paths

# Software lifecycle (not a SOP — see CONST-SOP-3, lives here for scope)
xu-wiki install                                      # capabilities only; never touches wiki data
xu-wiki uninstall [--execute]                       # default dry-run
```

| Command | Touches wiki data? | Touches software? | Reversible? |
|---|---|---|---|
| `wikis` | no (read-only) | no | n/a |
| `alias set/unset/show` | no (registry only) | no | yes |
| `register` | no (registry only) | no | yes (via `unregister`) |
| `unregister` | no (registry only; wiki files preserved) | no | yes (via `register`) |
| `config set-mineru-key` | no | no (writes to `~/.xu/config.yaml`) | yes |
| `config show` / `config path` | no (read-only) | no | n/a |
| `install` | **NEVER** (PRIN-INST-1) | yes (venv, CLI symlink, deploys skill) | yes (via `uninstall`) |
| `uninstall` | **NEVER** (BAN-UNINST-1) | yes (removes what install wrote) | yes (via `install`) |

## Hard rule for this SOP (PRIN-INST-1 / BAN-UNINST-1)

> **`install`装能力不装数据; `uninstall` 卸能力不卸数据.**
>
> - `install` sets up the project-local venv, the CLI symlink, deploys
>   the packaged `SKILL.md` (and SOP files) into the Agent's discovery
>   dir, and writes a global config skeleton with the API-key field left
>   empty. It **never** touches any wiki instance data.
> - `uninstall` is the inverse: removes only what `install` wrote, with
>   `--execute` to actually apply (default is dry-run). It **never**
>   deletes wiki data, the patches table, the IDF table, or the
>   packaged skill source. It does remove the deployed skill copy from
>   the Agent's discovery dir (since `install` wrote it).

## Workflow — first-time setup

1. **Install once per machine**: `xu-wiki install` (idempotent — safe to
   re-run after a `git pull`).
2. **Set the MinerU API key** (optional — only needed if the offline
   fallback chain hits a PDF and `markitdown` is not enough):
   ```bash
   export MINERU_API_KEY="..."   # safer than passing --key
   xu-wiki config set-mineru-key
   ```
   Or write it directly to `~/.xu/config.yaml` (outside this repo).
3. **Inspect the install**:
   ```bash
   xu-wiki config path    # show where config / global dir lives
   xu-wiki wikis          # show registered wikis (empty after first install)
   ```

## Workflow — register an existing wiki directory

Use `register` (NOT `create`) when the directory already exists with
wiki data. `create` is only for fresh empty wikis (it refuses to
overwrite a non-empty path — BAN-CRT-1).

```bash
xu-wiki register --name legacy --path /abs/path/to/existing/wiki --alias lg
# → {"status": "success", "data": {"name": "legacy", "path": "...", "alias": "lg"}, ...}
```

## Workflow — change or remove an alias

```bash
xu-wiki alias show --wiki research
# → {"status": "success", "data": {"alias": "r"}, ...}
xu-wiki alias set --wiki research --alias res
# → {"status": "success", ...}
xu-wiki alias unset --wiki research
# → {"status": "warning", "data": {"removed_alias": "res"}, ...}
```

## Workflow — unregister a wiki (does NOT delete wiki files)

```bash
xu-wiki unregister --name legacy
# → {"status": "success", "data": {"name": "legacy", "registry_removed": true, "wiki_files_intact": true}, ...}
```

The wiki directory is **untouched**. To bring it back: `register` again.

## Workflow — uninstall (DANGER)

```bash
# 1. Always dry-run first
xu-wiki uninstall
# → {"status": "success", "data": {"dry_run": true, "will_remove": [...], "preserved": [...]}, ...}

# 2. Inspect what will be removed
# 3. Re-run with --execute to actually apply
xu-wiki uninstall --execute
# → {"status": "success", "data": {"removed": [...], "residue": []}, ...}
```

**What is preserved by `uninstall --execute`**:
- All wiki instances (raws/, nodes/, .xu/) — BAN-UNINST-1
- The patches table & IDF table — BAN-UNINST-4
- The packaged skill source (the python package itself) — `install` did
  not write it; `uninstall` does not touch it
- The global config api-key segment & registry (preserved unless `--purge`
  is added; current CLI does not have a `--purge` flag — to wipe, remove
  `~/.xu/` manually after `uninstall`)

## Common pitfalls

- **`create` to register an existing dir** — refused by BAN-CRT-1. Use
  `register` instead.
- **`uninstall` thinking it deletes the wiki** — it does not. The wiki
  directory is preserved. To wipe, `rm -rf` manually AFTER `uninstall`.
- **Hardcoding the MinerU key** — never write the key into the repo, the
  SKILL.md, or any code. Use `MINERU_API_KEY` env or `~/.xu/config.yaml`.
- **Re-running `install` after a wiki move** — `install` is idempotent
  for venv / symlink / skill deploy, but it does NOT update the wiki
  registry. After moving a wiki directory, run `unregister` + `register`
  (or `alias set` if only the alias changed).

## Cross-references

- Cross-cutting rules (4-key JSON, paths, secrets) → `SKILL.md §Hard rules`
- The `create` CLI (fresh empty wiki) → `SKILL.md §SOP map` (create SOP)
- The `delete-node` CLI (to wipe wiki contents before removing the dir) →
  `SKILL.md §SOP map` (doctor SOP)
- The 3-layer metadata model (for what `register` accepts) →
  `SKILL.md §Architecture in 30 seconds`
- Full install / uninstall semantics → `design-docs/03-install.md` /
  `design-docs/04-uninstall.md`

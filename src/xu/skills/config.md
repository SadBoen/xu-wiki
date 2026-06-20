# config — manage wiki configuration

`/xu-wiki config` is the SOP for **everything that isn't wiki data**:
registering / aliasing / unregistering wikis, managing the MinerU API key,
and inspecting the global state. It does not touch L1/L2/L3 content.

This file is **self-contained** (PRIN-SKILL-1). Cross-cutting rules
(4-key JSON, missing-args) live in `SKILL.md`; the safety rules for
register / unregister are stated here.

## CLI palette

```bash
# Inspect registered wikis (read-only)
xu wikis

# Wiki registry: alias, register, unregister
xu alias set     --wiki <w> --alias <new>     # set or change alias
xu alias unset   --wiki <w>                   # remove alias
xu alias show    --wiki <w>                   # show current alias
xu register      --name <n> --path <abs> [--alias <a>]   # register EXISTING dir (no files written)
xu unregister    --name <n>                   # remove from registry (wiki files NOT touched)

# Global config (MinerU key etc.)
xu config set-mineru-key                       # reads from MINERU_API_KEY env (safer than --key)
xu config show                                 # global config (secrets masked)
xu config path                                 # global config file paths

# Skill bundle source (for the agent's own skill manager to copy from)
xu skills path                                 # print source dir of the xu-wiki skill bundle
xu skills list                                 # list files in the xu-wiki skill bundle
```

| Command | Touches wiki data? | Reversible? |
|---|---|---|
| `wikis` | no (read-only) | n/a |
| `alias set/unset/show` | no (registry only) | yes |
| `register` | no (registry only) | yes (via `unregister`) |
| `unregister` | no (registry only; wiki files preserved) | yes (via `register`) |
| `config set-mineru-key` | no (writes to `~/.xu/config.yaml`) | yes |
| `config show` / `config path` | no (read-only) | n/a |
| `skills path` / `skills list` | no (read-only) | n/a |

## Hard rule for this SOP

> **Wiki configuration only — no install/uninstall commands live here.**
>
> The CLI has no `xu install` or `xu uninstall` subcommand. Installing the
> package is `pip install "xu-wiki[parse,nlp,vision]"`; uninstalling is
> `pip uninstall xu-wiki`. The `skills path` / `skills list` subcommands
> exist so the agent can locate the bundled skill source dir for its own
> skill manager — they do not deploy anything to any agent.

## Workflow — first-time setup

1. **Install the package once per machine**:
   ```bash
   pip install "xu-wiki[parse,nlp,vision]"
   xu skills path    # discover the bundled skill source dir
   ```
2. **Set the MinerU API key** (optional — only needed if the offline
   fallback chain hits a PDF and `markitdown` is not enough):
   ```bash
   export MINERU_API_KEY="..."   # safer than passing --key
   xu config set-mineru-key
   ```
   Or write it directly to `~/.xu/config.yaml` (outside this repo).
3. **Inspect the global state**:
   ```bash
   xu config path    # show where config / global dir lives
   xu wikis          # show registered wikis (empty at first install)
   ```

## Workflow — register an existing wiki directory

Use `register` (NOT `create`) when the directory already exists with
wiki data. `create` is only for fresh empty wikis (it refuses to
overwrite a non-empty path — BAN-CRT-1).

```bash
xu register --name legacy --path /abs/path/to/existing/wiki --alias lg
# → {"status": "success", "data": {"name": "legacy", "path": "...", "alias": "lg"}, ...}
```

## Workflow — change or remove an alias

```bash
xu alias show --wiki research
# → {"status": "success", "data": {"alias": "r"}, ...}
xu alias set --wiki research --alias res
# → {"status": "success", ...}
xu alias unset --wiki research
# → {"status": "warning", "data": {"removed_alias": "res"}, ...}
```

## Workflow — unregister a wiki (does NOT delete wiki files)

```bash
xu unregister --name legacy
# → {"status": "success", "data": {"name": "legacy", "registry_removed": true, "wiki_files_intact": true}, ...}
```

The wiki directory is **untouched**. To bring it back: `register` again.

## Common pitfalls

- **`create` to register an existing dir** — refused by BAN-CRT-1. Use
  `register` instead.
- **Hardcoding the MinerU key** — never write the key into the repo, the
  SKILL.md, or any code. Use `MINERU_API_KEY` env or `~/.xu/config.yaml`.

## Cross-references

- Cross-cutting rules (4-key JSON, paths, secrets) → `SKILL.md §Hard rules`
- The `create` CLI (fresh empty wiki) → `SKILL.md §SOP map` (create SOP)
- The `delete-node` CLI (to wipe wiki contents before removing the dir) →
  `SKILL.md §SOP map` (doctor SOP)
- The 3-layer metadata model (for what `register` accepts) →
  `SKILL.md §Architecture in 30 seconds`
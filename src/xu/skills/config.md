# config — manage wiki configuration & software lifecycle

`/xu-wiki config` is the SOP for **everything that isn't wiki data**:
registering / aliasing / unregistering wikis, managing the MinerU API key,
inspecting the global state, and **uninstalling the xu-wiki package
itself**. It does not touch L1/L2/L3 content.

This file is **self-contained** (PRIN-SKILL-1). Cross-cutting rules
(4-key JSON, missing-args) live in `SKILL.md`; the safety rules for
register / unregister / uninstall are stated here.

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

# Software lifecycle — uninstall xu-wiki itself (PRIN-UNINST-*)
xu uninstall                                          # DRY-RUN by default; --execute to apply
xu uninstall --execute                               # remove pip package + skill bundles + ~/.xu-wiki/ config
xu uninstall --execute --preserve-config             # keep ~/.xu-wiki/ config dir
xu uninstall --execute --keep-pip                    # skip pip uninstall (test/dev escape hatch)
xu uninstall --execute --keep-skill                 # keep all skill bundles
xu uninstall --execute --target hermes --target trae # remove only specific skill bundles
```

| Command | Touches wiki data? | Touches pip pkg? | Touches ~/.xu-wiki/? | Reversible? |
|---|---|---|---|---|
| `wikis` | no (read-only) | no | no | n/a |
| `alias set/unset/show` | no (registry only) | no | yes (registry) | yes |
| `register` | no (registry only) | no | yes (registry) | yes (via `unregister`) |
| `unregister` | no (registry only; wiki files preserved) | no | yes (registry) | yes (via `register`) |
| `config set-mineru-key` | no | no | yes (config) | yes |
| `config show` / `config path` | no (read-only) | no | no | n/a |
| `skills path` / `skills list` | no (read-only) | no | no | n/a |
| `uninstall` (dry-run) | **never** (always preserved) | no | no | n/a |
| `uninstall --execute` | **never** (always preserved) | yes (unless `--keep-pip`) | only if `--preserve-config` is absent | **no — destructive** |

## Hard rule for this SOP

> **Wiki configuration + software lifecycle. The 5 SOPs share the
> same slash command entry; uninstall lives here because it's a
> system-level action, not a wiki-data operation.**

## Workflow — uninstall xu-wiki

This is the **only** destructive flow in `/xu-wiki config`. The agent
must always **dry-run first**, then confirm with the user, then re-run
with `--execute` and the user's chosen flags. There is no shortcut.

### Step 1 — dry-run

```bash
xu uninstall
# → 4-key JSON: status=success, data.mode="dry-run", data.plan={wikis_found, global_dir_exists, ...}
```

The agent reads `data.plan` and **presents it to the user in natural
language**. The user picks a scope:

| Scope | Flags | What gets removed |
|---|---|---|
| (a) Standard | `--execute` | pip package + skill bundles + `~/.xu-wiki/` config |
| (b) Keep config | `--execute --preserve-config` | pip + skill bundles (keep `~/.xu-wiki/`) |
| (c) Keep pip | `--execute --keep-pip` | skill bundles + `~/.xu-wiki/` (skip pip uninstall) |
| (d) Keep skill | `--execute --keep-skill` | pip + `~/.xu-wiki/` (keep all skill bundles) |
| (e) Target specific | `--execute --target <agent>` | only that agent's skill bundle |

**Wiki data is NEVER touched, no matter which flags are used.** `--purge-wikis`
is accepted but ignored — it is not possible to delete wiki data through uninstall.

### Step 2 — confirm with the user

The agent shows the dry-run plan and the scope options, then waits
for explicit confirmation. PRIN-UNINST-6: **the user must type "yes"
/ "确认" / "proceed" before any --execute runs.** This is non-negotiable.

### Step 3 — execute

```bash
xu uninstall --execute [--preserve-config] [--keep-pip] [--keep-skill] [--target <agent>]
# → 4-key JSON: status=success / warning / error
#           data.result = { pip, wikis, config_dir }  with each step's outcome
```

The agent translates `data.result` back to natural language and tells
the user what happened. The JSON is NOT shown to the user.

### Critical rules for the agent

1. **Never run `pip uninstall` directly via your bash tool.** Even
   though it would technically work, it bypasses SKILL.md
   discoverability and the dry-run safety contract. Always go through
   `xu uninstall`.
2. **Never invent `/xu-wiki uninstall` slash command.** It doesn't
   exist — the slash command is `/xu-wiki config`, and within that
   SOP the agent recognises uninstall intent and calls `xu uninstall`.
3. **Always dry-run first.** `xu uninstall` without `--execute` is
   the expected entry point. The user's first request → dry-run.
   Confirmation → re-run with `--execute`.
4. **Wiki data is NEVER removed, no exceptions.** `--purge-wikis` is accepted
   but silently ignored — the flag has no effect. Do not propose it,
   do not confirm it, do not explain it as a capability.
5. **Translate JSON → natural language.** Never paste the raw 4-key
   JSON at the user.
6. **Default scope is (a) — standard uninstall.** Only deviate if the user
   explicitly asks to keep config (`--preserve-config`) or keep pip (`--keep-pip`).
7. **`xu uninstall --execute --keep-pip` is a test escape hatch.**
   Agents must NEVER pass `--keep-pip` in normal flows — it's for the
   test suite (PRIN-TEST-*) and developer debugging. If you see it
   in a user-facing flow, treat it as a bug.

### Install is NOT in this SOP

Install is documented in README §Install (single authoritative source).
There is no `xu install` command, no `/xu-wiki install` slash command,
and no `pip upgrade` wrapper.

## Common pitfalls

- **`create` to register an existing dir** — refused by BAN-CRT-1. Use
  `register` instead.
- **Hardcoding the MinerU key** — never write the key into the repo, the
  SKILL.md, or any code. Use `MINERU_API_KEY` env or `~/.xu-wiki/config.yaml`.
- **`xu install`** — does not exist; returns `ArgParseError`. Install
  is `pip install`. Uninstall is `xu uninstall`.
- **Calling `xu uninstall` without `--execute`** — that's the dry-run
  and is the right first step. Just don't forget to re-run with
  `--execute` after the user confirms.

## Cross-references

- Cross-cutting rules (4-key JSON, paths, secrets) → `SKILL.md §Hard rules`
- The `create` CLI (fresh empty wiki) → `SKILL.md §SOP map` (create SOP)
- The `delete-node` CLI (to wipe wiki contents before removing the dir) →
  `SKILL.md §SOP map` (doctor SOP)
- The 3-layer metadata model (for what `register` accepts) →
  `SKILL.md §Architecture in 30 seconds`
- Why uninstall is a CLI command and install is not → `design-docs/08-sop-architecture.md` [CONST-SOP-3]

## Workflow — first-time setup

> This section covers runtime configuration only. For install steps
> (pipx / pip / venv) see **README §Install** — install is not in this
> bundle (CONST-INST-6 / BAN-SKILL-3a).

1. **Set the MinerU API key** (optional — only needed if the offline
   fallback chain hits a PDF and `markitdown` is not enough):
   ```bash
   export MINERU_API_KEY="..."   # safer than passing --key
   xu config set-mineru-key
   ```
   Or write it directly to `~/.xu-wiki/config.yaml` (outside this repo).
2. **Inspect the global state**:
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
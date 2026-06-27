# config — wiki config & software lifecycle

Everything that isn't wiki data: registry, aliases, MinerU key, uninstall.

## CLI palette

```bash
# Inspect
xu wikis
xu config show
xu config path

# Registry
xu alias set --wiki <w> --alias <new>
xu alias unset --wiki <w>
xu alias show --wiki <w>
xu register --name <n> --path <abs> [--alias <a>]
xu unregister --name <n>

# MinerU key
xu config set-mineru-key   # reads MINERU_API_KEY env (safer)
xu config show             # secrets masked

# Skill bundle
xu skills path             # source dir of xu-wiki skill bundle
xu skills list             # list files in bundle

# Uninstall (dry-run first, then --execute)
xu uninstall
xu uninstall --execute [--preserve-config] [--keep-pip] [--keep-skill] [--target <agent>]
```

## Safety table

| Command | Wiki data? | pip pkg? | ~/.xu-wiki/? | Reversible? |
|---|---|---|---|---|
| `wikis` / `config show` / `config path` | no | no | no | n/a |
| `alias set/unset/show` | no | no | yes (registry) | yes |
| `register` / `unregister` | no (registry only) | no | yes | yes |
| `config set-mineru-key` | no | no | yes | yes |
| `skills path` / `skills list` | no | no | no | n/a |
| `uninstall` (dry-run) | never | no | no | n/a |
| `uninstall --execute` | **never** | yes | only without `--preserve-config` | **no** |

## Unworkflow — uninstall

**Step 1 — dry-run:**
```bash
xu uninstall
```
Read `data.plan`, present to user. **Wiki data is NEVER touched.**

**Step 2 — confirm:**
User must explicitly confirm before `--execute`.

**Step 3 — execute:**
```bash
xu uninstall --execute [--flags]
```

Scope options:

| Scope | Flags |
|---|---|
| (a) Standard | `--execute` |
| (b) Keep config | `--execute --preserve-config` |
| (c) Keep pip | `--execute --keep-pip` (test escape hatch) |
| (d) Keep skill | `--execute --keep-skill` |
| (e) Target specific | `--execute --target <agent>` |

**`--purge-wikis`** — accepted but ignored. Wiki data is never deletable via uninstall.

## Setup workflow

1. **MinerU key** (optional):
   ```bash
   export MINERU_API_KEY="..."
   xu config set-mineru-key
   ```
2. **Verify state**:
   ```bash
   xu config path
   xu wikis
   ```

## Register existing wiki

```bash
xu register --name legacy --path /abs/path/to/existing/wiki --alias lg
```

## Pitfalls

| Pitfall | Fix |
|---|---|
| `create` for existing dir | Use `register` instead |
| Hardcoding MinerU key | Use `MINERU_API_KEY` env or `~/.xu-wiki/config.yaml` |
| `xu install` | Doesn't exist — use `pip install` |
| `--keep-pip` in user flow | Test escape hatch — never in normal flows |
| `--purge-wikis` | Accepted but ignored — no effect |

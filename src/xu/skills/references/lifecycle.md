# lifecycle — wiki & program lifecycle

> 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

Everything that touches wiki creation/deletion and the xu-wiki program lifecycle.

## Workflow

### Step 1 — Create wiki

```bash
xu create --name <n> --path <abs> [--alias <a>]
```

Registers in `~/.xu-wiki/registry.yaml`. Wiki data lives at `<path>/`.

Use `pip install "xu-wiki[parse,nlp,vision]"` for first-time setup. `xu create` only registers existing directories.

### Step 2 — Register existing wiki

```bash
xu register --name <n> --path <abs> [--alias <a>]
```

Use `register` for existing directories (different from `create` — `create` writes the wiki scaffold).

### Step 3 — Update program

```bash
xu update
```

Installs from `git+https://github.com/SadBoen/xu-wiki.git@main`. Re-deploys skills to all manifest targets.

**Update process:**
1. `xu update --check` → compare installed SHA vs GitHub HEAD
2. pip install with `--force-reinstall`
3. skill re-deploy to manifest targets

If first install (no prior SHA): warning emitted, pip install still runs — this is correct first-time path.

### Step 4 — Uninstall

```bash
xu uninstall --execute
```

Removes skill bundle + pip/pipx package. **Wiki data is NEVER deleted** (BAN-UNINST-1).

### Step 5 — Config

```bash
xu config path
xu config show
xu alias set --wiki <w> --alias <new>
xu alias unset --wiki <w>
xu alias show --wiki <w>
xu register --name <n> --path <abs> [--alias <a>]
xu unregister --name <n>
```

## CLI reference

```bash
# Wiki lifecycle
xu create --name <n> --path <abs> [--alias <a>]
xu register --name <n> --path <abs> [--alias <a>]
xu unregister --name <n>

# Program lifecycle
xu update [--check]
xu uninstall [--execute]
xu selfcheck

# Deploy skill bundle
xu deploy skill --target <agent>   # hermes | trae | claude | cursor | auto

# Skill bundle
xu skills path
xu skills list

# Config
xu config show
xu config path
xu alias set --wiki <w> --alias <new>
xu alias unset --wiki <w>
xu alias show --wiki <w>
```

## Safety

| Command | Wiki data? | pip pkg? | ~/.xu-wiki/? | Reversible? |
|---|---|---|---|---|
| `create` / `register` | no (registry only) | no | yes | yes |
| `unregister` | no (registry only) | no | yes | yes |
| `update` | no | yes | no | yes (reinstall old SHA) |
| `uninstall --execute` | **never deleted** | yes | yes | yes (reinstall via pip) |

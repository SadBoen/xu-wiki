# config — wiki registry, aliases & global settings

> 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

Everything that isn't wiki data: registry, aliases, MinerU key. Wiki data is NEVER touched.

## Workflow

### Step 1 — Setup MinerU key (optional)

```bash
export MINERU_API_KEY="..."
xu config set-mineru-key
```

Use `MINERU_API_KEY` env or `~/.xu-wiki/config.yaml`. Never hardcode the key.

### Step 2 — Verify state

```bash
xu config path
xu wikis
```

### Step 3 — Register existing wiki

```bash
xu register --name <n> --path <abs> [--alias <a>]
```

Use `register` for existing directories. `xu install` does not exist — use `pip install`.

## CLI reference

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
xu config set-mineru-key
xu config show

# Skill bundle
xu skills path
xu skills list

# Install
xu selfcheck
xu deploy skill --target <agent>   # hermes | trae | claude | cursor | auto
```

## Safety

| Command | Wiki data? | pip pkg? | ~/.xu-wiki/? | Reversible? |
|---|---|---|---|---|
| `wikis` / `config show` / `config path` | no | no | no | n/a |
| `alias set/unset/show` | no | no | yes (registry) | yes |
| `register` / `unregister` | no (registry only) | no | yes | yes |
| `config set-mineru-key` | no | no | yes | yes |
| `skills path` / `skills list` | no | no | no | n/a |

# create — build a new empty wiki

> **注意：** 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

## CLI palette

```bash
xu create --name <n> --path <abs> [--alias <a>]
```

| Flag | Required | Purpose |
|---|---|---|
| `--name` | yes | Registry key (lowercase, unique) |
| `--path` | yes | Absolute dir; `~` OK; relative refused |
| `--alias` | no | Shortcut for `--wiki <alias>` |

## Workflow

1. **Ask if no path** — "create a wiki" without path → ask; CLI refuses guessed paths
2. **Confirm path empty or not exist** — `PathNotEmpty` returns conflicting entries
3. **Call `create`** — writes template, registers under `--name`
4. **Verify** — `xu wikis` (config SOP)

## Example

```bash
xu create --name research --path ~/Wikis/research --alias r
# → {"status": "success", "data": {"name": "research", "path": "...", "alias": "r"}, ...}
```

## Pitfalls

| Pitfall | Why it's wrong |
|---|---|
| Guessed path | CLI refuses; round-trip wastes time — always ask |
| Relative path | `./foo` rejected at parse time |
| Name collision | `NameConflict`; pick another name |
| `create` for existing dir | Use `register` (config SOP) instead |

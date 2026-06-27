# create — build a new empty wiki

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

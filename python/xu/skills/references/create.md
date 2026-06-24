# create — new wiki

```bash
xu create --name <n> --path <abs> [--alias <a>]
```

| Flag | Required | Notes |
|------|----------|-------|
| `--name` | yes | Unique registry key, alnum/-/_ only |
| `--path` | yes | Absolute path. Created if absent. Refused if non-empty. |
| `--alias` | no | Short name for `--wiki <alias>` |

## Steps

1. If user didn't give name or path -> ask for both. Never guess.
2. `xu create --name X --path /abs/path`
3. Read response: `success` -> wiki ready. `error` -> report to user.
4. Optional: `xu wikis` to verify registration.

## Response

`success`: `{name, path, version, layout, tables}`
`error`: `{error_class, message}` — most common: `MissingName`, `PathNotAbsolute`, `InvalidName`

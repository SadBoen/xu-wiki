# lifecycle — wiki and program lifecycle management

> **注意：** 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

This SOP covers five operations across two concerns:

| Concern | Operations |
|---|---|
| Wiki instance lifecycle | `create`, `register`, `unregister` |
| xu-wiki program lifecycle | `update`, `uninstall` |

---

## create — build a new empty wiki

```bash
xu create --name <n> --path <abs> [--alias <a>]
```

| Flag | Required | Purpose |
|---|---|---|
| `--name` | yes | Registry key (lowercase, unique) |
| `--path` | yes | Absolute dir; `~` OK; relative refused |
| `--alias` | no | Shortcut for `--wiki <alias>` |

### Workflow

1. **Ask if no path** — "create a wiki" without path → ask; CLI refuses guessed paths
2. **Confirm path empty or not exist** — `PathNotEmpty` returns conflicting entries
3. **Call `create`** — writes template, registers under `--name`
4. **Verify** — `xu wikis`

### Example

```bash
xu create --name research --path ~/Wikis/research --alias r
```

### Pitfalls

| Pitfall | Fix |
|---|---|
| Guessed path | CLI refuses; round-trip wastes time — always ask |
| Relative path | `./foo` rejected at parse time |
| Name collision | `NameConflict`; pick another name |
| `create` for existing dir | Use `register` instead |

---

## register — register an existing wiki directory

```bash
xu register --name <n> --path <abs> [--alias <a>]
```

Adds an existing wiki directory to the registry without writing any files.

---

## unregister — remove a wiki from the registry

```bash
xu unregister --name <n>
```

Wiki files are untouched; only the registry entry is removed.

---

## update — upgrade xu-wiki

```bash
xu update                    # upgrade pip package + re-deploy skills to all manifest targets
xu update --check            # check PyPI for newer version, no side effects
xu update --no-redeploy      # only upgrade pip package, skip skill re-deploy
```

**Wiki data is NEVER touched.**

### Workflow

1. `xu update --check` — reports `{status, data: {current, latest, update_available}}`
2. `xu update` — pip upgrade + re-deploy skill bundles
3. `xu selfcheck` — verify

### Safety

| Command | Wiki data? | pip pkg? | Skill bundles? | ~/.xu-wiki/? |
|---|---|---|---|---|
| `update --check` | never | never | never | never |
| `update` | never | upgraded | re-deployed | preserved |
| `update --no-redeploy` | never | upgraded | skipped | preserved |

---

## uninstall — uninstall xu-wiki

```bash
xu uninstall                  # dry-run (default)
xu uninstall --execute       # actually uninstall
xu uninstall --execute --preserve-config   # keep ~/.xu-wiki/
xu uninstall --execute --keep-pip           # test escape hatch
xu uninstall --execute --keep-skill         # keep skill bundles
xu uninstall --execute --target <agent>     # target specific agent(s)
```

**Wiki data is NEVER deleted. No flag, no branch, no surface ever touches it.**

### Workflow

1. **Dry-run** — `xu uninstall` → read `data.plan`, present to user
2. **Confirm** — user must explicitly confirm before `--execute`
3. **Execute** — `xu uninstall --execute`

### Safety

| Command | Wiki data? | pip pkg? | ~/.xu-wiki/? | Reversible? |
|---|---|---|---|---|
| `uninstall` (dry-run) | never | no | no | n/a |
| `uninstall --execute` | **never** | yes | only without `--preserve-config` | **no** |

### Pitfalls

| Pitfall | Fix |
|---|---|
| `xu install` | Doesn't exist — use `pip install` |
| `--keep-pip` in user flow | Test escape hatch — never in normal flows |

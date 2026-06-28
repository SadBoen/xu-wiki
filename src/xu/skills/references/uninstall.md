# uninstall — uninstall xu-wiki

> **注意：** 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

Remove xu-wiki from the system: pip package + skill bundles + optional config.

**Wiki data is NEVER deleted. No flag, no branch, no surface ever touches it.**

## CLI palette

```bash
xu uninstall                  # dry-run (default)
xu uninstall --execute        # actually uninstall
xu uninstall --execute --preserve-config   # keep ~/.xu-wiki/
xu uninstall --execute --keep-pip           # skip pip uninstall (test escape hatch)
xu uninstall --execute --keep-skill         # keep skill bundles
xu uninstall --execute --target <agent>     # target specific agent(s)
```

## Safety table

| Command | Wiki data? | pip pkg? | ~/.xu-wiki/? | Reversible? |
|---|---|---|---|---|
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

## Scope options

| Scope | Flags |
|---|---|
| (a) Standard | `--execute` |
| (b) Keep config | `--execute --preserve-config` |
| (c) Keep pip | `--execute --keep-pip` (test escape hatch) |
| (d) Keep skill | `--execute --keep-skill` |
| (e) Target specific | `--execute --target <agent>` |

## Pitfalls

| Pitfall | Fix |
|---|---|
| `xu install` | Doesn't exist — use `pip install` |
| `--keep-pip` in user flow | Test escape hatch — never in normal flows |

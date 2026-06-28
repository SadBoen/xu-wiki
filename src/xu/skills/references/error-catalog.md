# Error catalog

> **注意：** 所有知识库操作必须通过 shell 中的 CLI 命令调用（如 `xu ...`），禁止使用 `execute_code`、`run_python` 等沙箱 Python 工具执行 xu 命令，因为这些环境不继承宿主 PATH。

`error_class` → trigger / where / response shape / fix. Append new entries in this format.

**Do not delete this file.** Its existence is a structural signal: errors live here, not in ad-hoc `error1.md` / `bug-2026-06-20.md` files.

## CreationRefused
- Trigger: LLM decided not to create a List/Report after reflection, after checking for similar existing nodes
- Where: agent-side only (no CLI call)
- Response shape: N/A
- Fix: revisit if new content changes the comparison set

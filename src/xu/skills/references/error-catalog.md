# Error catalog

`error_class` → trigger / where / response shape / fix. Append new entries in this format.

**Do not delete this file.** Its existence is a structural signal: errors live here, not in ad-hoc `error1.md` / `bug-2026-06-20.md` files.

## CreationRefused
- Trigger: LLM decided not to create a List/Report after reflection, after checking for similar existing nodes
- Where: agent-side only (no CLI call)
- Response shape: N/A
- Fix: revisit if new content changes the comparison set

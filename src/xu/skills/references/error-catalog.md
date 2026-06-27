# Error catalog

Central reference for every `error_class` the CLI may return. Append a new
entry whenever the Agent encounters a previously-unknown error, using this
format:

## <error_class>
- Trigger: <what user/system action causes it>
- Where: <which CLI subcommand / SOP>
- Response shape: <what `data` keys accompany it>
- Fix: <how the user / agent should respond>

**Empty by design.** Do not delete this file even when it has no entries —
its existence is a structural signal: "errors live here, not in
ad-hoc `error1.md` / `bug-2026-06-20.md` files.

Cross-references:
- JSON response shape (`status` / `data` / `message` / `hints` /
  `data.error_class`) → `SKILL.md §Reading the response`
- Process-layer audit carrying `error_class` → `SKILL.md §Process-layer audit log`

## CreationRefused
- Trigger: LLM decided not to create a List/Report after post-commit or
  post-query reflection, after checking for similar existing
  nodes (query-before-create). Not a CLI error — the agent weighed the
  evidence and chose not to create.
- Where: agent-side only. The CLI never sees this; it is the agent's
  internal acknowledgment that no `list create` / `report create` call
  was made.
- Response shape: N/A (no CLI call). Agent may later revisit the
  decision if new content is ingested or queried that changes the
  comparison set.

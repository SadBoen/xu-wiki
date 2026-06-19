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
ad-hoc `error1.md` / `bug-2026-06-20.md` files". See PRIN-SKILL-7 in
`design-docs/09-skill-architecture.md`.

Cross-references:
- JSON response shape (`status` / `data` / `message` / `hints` /
  `data.error_class`) → `SKILL.md §Reading the response`
- Process-layer audit carrying `error_class` → `SKILL.md §Process-layer audit log`

## CreationRefused
- Trigger: user explicitly declined an L2/L3 creation proposal that the
  agent raised during post-ingest or post-query reflection (PRIN-CR-1).
  Not a CLI error — this entry exists so the agent has a defined behavior
  for "user said no", independent of any CLI command.
- Where: agent-side only. The CLI never sees this; it is the agent's
  internal acknowledgment that the user rejected the proposal.
- Response shape: N/A (no CLI call). Agent-internal state:
  `{reflection_kind: "list"|"report", trigger: "ingest"|"query",
    declined_at: <ts>, proposal: {<the payload that was declined>}}`.
- Fix: respect the decision. Do NOT re-propose in this session for the
  same payload. Do NOT log to `audit.jsonl` (this is a soft refusal, not
  a CLI failure — keeping it out of audit avoids polluting the
  process-layer log with non-events). If the user later changes their
  mind, they will say so explicitly.

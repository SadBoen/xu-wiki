# Pitfalls

Non-obvious gotchas — things that look fine but fail in practice. Append a
new entry whenever the Agent encounters a previously-unknown pitfall,
using this format:

## <short title>
- Date: YYYY-MM-DD
- Context: <which command / scenario>
- Symptom: <what the user sees>
- Cause: <why it happens>
- Workaround: <how to avoid / recover>

**Empty by design.** Do not delete this file even when it has no entries —
its existence is a structural signal: "pitfalls live here, not scattered
in date-named `notes-2026-06-20.md` files". See PRIN-SKILL-7 in
`design-docs/09-skill-architecture.md`.

Cross-references:
- Cross-cutting hard rules (the "obvious" things) → `SKILL.md §Hard rules`
- SOP-specific gotchas (only relevant to one SOP) → in the SOP file itself,
  not here

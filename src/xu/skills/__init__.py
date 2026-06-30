"""Packaged agent-facing resources.

The skill ships as package data so the authoritative source travels with
`pip install xu-wiki`.

The CLI does NOT deploy skills to any agent. The agent uses its own skill
manager (Hermes / Trae / Claude Desktop / Cursor / etc.) to create an empty
skill, then copies the files listed in `ALL_SKILL_FILES` into it. Use
`xu skills path` to discover the on-disk location.
"""

from __future__ import annotations

from pathlib import Path

SKILL_NAME = "xu-wiki"
SKILL_SRC_DIR = Path(__file__).resolve().parent  # xu/skills/
SKILL_SRC = SKILL_SRC_DIR / "SKILL.md"  # entry-point (always present)
# Per-SOP task files. SKILL.md is the index; SOPs are self-contained
# (no cross-references between them). All in references/.
SOP_TASK_FILES = (
    "references/lifecycle.md",
    "references/ingest.md",
    "references/query.md",
    "references/doctor.md",
    "references/config.md",
)
# Reference files. Empty by design — their existence signals to the Agent
# "this kind of content lives here, do not scatter ad-hoc files".
REFERENCE_FILES = ("references/error-catalog.md",)
ALL_SKILL_FILES = ("SKILL.md",) + SOP_TASK_FILES + REFERENCE_FILES

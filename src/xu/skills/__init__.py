"""Packaged agent-facing resources (SKILL.md + 5 SOP task files + INSTALL.md).

The skill is split per design-docs/09-skill-architecture.md (PRIN-SKILL-1~6,
BAN-SKILL-1/2): one self-contained `.md` per SOP, plus SKILL.md as the only
index. They ship as package data so the authoritative source travels with
`pip install xu-wiki`.

The CLI does NOT deploy skills to any agent. The agent uses its own skill
manager (Hermes / Trae / Claude Desktop / Cursor / etc.) to create an empty
skill, then copies the files listed in `ALL_SKILL_FILES` into it. Use
`xu skills path` to discover the on-disk location.
"""
from __future__ import annotations

from pathlib import Path

SKILL_NAME = "xu-wiki"
SKILL_SRC_DIR = Path(__file__).resolve().parent          # xu/skills/
SKILL_SRC = SKILL_SRC_DIR / "SKILL.md"                   # entry-point (always present)
# Per-SOP task files. SKILL.md is the index; the 5 SOP files are loaded
# on-demand by the Agent per PRIN-SKILL-1 (self-contained, no cross-references).
SOP_TASK_FILES = ("create.md", "ingest.md", "query.md", "doctor.md", "config.md")
# Reference placeholder files. Empty by design (PRIN-SKILL-7) — their
# existence signals to the Agent "this kind of content lives here, do not
# scatter ad-hoc files". Paths are relative to SKILL_SRC_DIR.
REFERENCE_FILES = (
    "reference/error-catalog.md",
    "reference/pitfalls.md",
)
# Post-install checklist for the agent. Loaded by the Agent alongside
# the other 8 files when it first meets xu-wiki, so it knows the
# install/verify/deploy sequence instead of guessing.
INSTALL_FILES = ("INSTALL.md",)
ALL_SKILL_FILES = (("SKILL.md",) + SOP_TASK_FILES
                   + REFERENCE_FILES + INSTALL_FILES)

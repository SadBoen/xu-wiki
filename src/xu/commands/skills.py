"""`xu skills ...` — report the location of the bundled xu-wiki skill files.

The CLI does NOT deploy skills to any agent. The agent uses its own skill
manager to create an empty skill directory, then copies the files reported
here into it. This keeps the CLI a deterministic, network-free tool and
leaves skill lifecycle to each agent platform (Hermes / Trae / Claude
Desktop / Cursor / etc.).
"""
from __future__ import annotations

from ..skills import ALL_SKILL_FILES, SKILL_NAME, SKILL_SRC_DIR
from ..utils.response import success


def cmd_skills(args) -> dict:
    action = getattr(args, "skills_action", None)
    if action == "path":
        return success(
            {
                "skill_name": SKILL_NAME,
                "source_dir": str(SKILL_SRC_DIR),
                "file_count": len(ALL_SKILL_FILES),
            },
            f"{SKILL_NAME} skill bundle source path",
        )
    if action == "list":
        return success(
            {
                "skill_name": SKILL_NAME,
                "source_dir": str(SKILL_SRC_DIR),
                "files": [str(rel) for rel in ALL_SKILL_FILES],
            },
            f"{SKILL_NAME} skill bundle file list",
        )
    return success(
        {"skill_name": SKILL_NAME, "source_dir": str(SKILL_SRC_DIR)},
        "use `xu skills path` or `xu skills list`",
    )
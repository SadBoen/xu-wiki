"""`xu skills ...` — report the location of the bundled xu-wiki skill files.

The CLI does NOT deploy skills to any agent by itself (use
`xu deploy skill --target <agent>` for that). The agent uses its own
skill manager to create an empty skill directory, then copies the
files reported here into it. This keeps the CLI a deterministic,
network-free tool and leaves skill lifecycle to each agent platform
(Hermes / Trae / Claude Desktop / Cursor / etc.).

`ALL_SKILL_FILES` is curated; this module adds a defensive filter
that excludes any Python package artifacts (`__init__.py`,
`__pycache__/`, `.pyc`) which are accidentally present in the source
dir as a side effect of being a regular Python package.

The filter is here (NOT in `xu/skills/__init__.py`) so the
ALL_SKILL_FILES tuple can stay close to the source layout for
documentation purposes; this layer guarantees the agent only ever
sees pure-markdown files.
"""
from __future__ import annotations

from ..skills import ALL_SKILL_FILES, SKILL_NAME, SKILL_SRC_DIR
from ..utils.response import success


# Python package artifacts that MUST NOT ship in the agent's skill
# discovery dir. These are present in the source dir because the skills
# dir is a regular Python package; they would leak into the agent's
# discovery dir via a naive `cp -r`.
_PYTHON_ARTIFACTS_TOP = {"__init__.py", "__pycache__", ".pyc"}


def _filter_bundle_files(files) -> list[str]:
    """Defensive: drop any Python-artifact entries from the file list.

    Applied to ALL_SKILL_FILES at every output site. If a future
    contributor accidentally adds `"__init__.py"` to ALL_SKILL_FILES
    (because the skills dir literally contains one), this filter
    keeps the agent-facing output clean.
    """
    out = []
    for rel in files:
        rel_str = str(rel)
        # top-level artifact
        top = rel_str.split("/", 1)[0]
        if top in _PYTHON_ARTIFACTS_TOP:
            continue
        # any path component that is a __pycache__ dir
        if any(part == "__pycache__" for part in rel_str.split("/")):
            continue
        out.append(rel_str)
    return out


def cmd_skills(args) -> dict:
    action = getattr(args, "skills_action", None)
    if action == "path":
        return success(
            {
                "skill_name": SKILL_NAME,
                "source_dir": str(SKILL_SRC_DIR),
                "file_count": len(_filter_bundle_files(ALL_SKILL_FILES)),
            },
            f"{SKILL_NAME} skill bundle source path",
        )
    if action == "list":
        clean = _filter_bundle_files(ALL_SKILL_FILES)
        return success(
            {
                "skill_name": SKILL_NAME,
                "source_dir": str(SKILL_SRC_DIR),
                "files": clean,
            },
            f"{SKILL_NAME} skill bundle file list (Python artifacts filtered)",
        )
    return success(
        {"skill_name": SKILL_NAME, "source_dir": str(SKILL_SRC_DIR)},
        "use `xu skills path` / `xu skills list` / `xu deploy skill`",
    )
"""Packaged agent-facing resources (SKILL.md). Shipped as package data so the
authoritative skill source travels with `pip install`; `install` deploys a
copy into the Agent's discovery dir (.trae/skills/) per PRIN-INST-3."""
from __future__ import annotations

from pathlib import Path

SKILL_NAME = "xu-wiki"
SKILL_SRC = Path(__file__).resolve().parent / "SKILL.md"

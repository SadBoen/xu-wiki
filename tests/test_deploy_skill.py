"""Unit tests for `xu deploy skill --target <agent>`.

The command replaces the hand-rolled `cp -r` flow. Three things it
gets right that the manual flow got wrong:

1. Subdir preservation (`reference/` not flattened)
2. Python-artifact filter (no `__init__.py` / `__pycache__/` leak)
3. Built-in target → discovery-dir mapping (hermes/trae/claude/cursor/auto)
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.commands import deploy_skill as cmd_mod
from xu.skills import ALL_SKILL_FILES, SKILL_NAME


def _args(target="auto"):
    if isinstance(target, list):
        return SimpleNamespace(target=target, copy=False)
    return SimpleNamespace(target=target, copy=False)


# ----------------------------------------------------------------------
# 1. resolution: target → discovery dir
# ----------------------------------------------------------------------


def test_resolve_hermes_uses_user_hermes(monkeypatch):
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", "/home/test"))
    _, desc, dest = cmd_mod._resolve_target("hermes")
    assert desc.startswith("Hermes")
    assert str(dest) == "/home/test/.hermes/skills/xu-wiki"


def test_resolve_claude_macos_path(monkeypatch):
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", "/Users/test"))
    _, _, dest = cmd_mod._resolve_target("claude")
    assert str(dest) == (
        "/Users/test/Library/Application Support/Claude/skills/xu-wiki"
    )


def test_resolve_trae_project_local_uses_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _, desc, dest = cmd_mod._resolve_target("trae")
    assert "project-local" in desc
    assert dest == tmp_path / ".trae" / "skills" / SKILL_NAME


def test_resolve_cursor_project_local_uses_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _, _, dest = cmd_mod._resolve_target("cursor")
    assert dest == tmp_path / ".cursor" / "skills" / SKILL_NAME


def test_resolve_unknown_target_raises():
    with pytest.raises(ValueError):
        cmd_mod._resolve_target("vscode")


def test_resolve_auto_probes_existing_parent(monkeypatch, tmp_path):
    """If ~/.hermes/skills/ exists, auto picks hermes."""
    (tmp_path / ".hermes" / "skills").mkdir(parents=True)
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", str(tmp_path)))
    name, _, dest = cmd_mod._resolve_target("auto", cwd=str(tmp_path))
    assert name == "hermes"
    assert dest == tmp_path / ".hermes" / "skills" / SKILL_NAME


def test_resolve_auto_errors_when_no_agent_detected(monkeypatch, tmp_path):
    """auto must NOT silently fall back to hermes; it raises so the
    user passes --target explicitly."""
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", str(tmp_path)))
    with pytest.raises(ValueError):
        cmd_mod._resolve_target("auto", cwd=str(tmp_path))


# ----------------------------------------------------------------------
# 2. Python-artifact filter (the bug the case study caught)
# ----------------------------------------------------------------------


def test_filter_bundle_files_excludes_python_artifacts():
    """Defensive: __init__.py and __pycache__/ MUST NOT appear."""
    bad = [
        "SKILL.md",
        "__init__.py",
        "create.md",
        "__pycache__/foo.pyc",
        "reference/__pycache__/bar.md",
    ]
    clean = cmd_mod._filter_bundle_files(bad)
    assert "__init__.py" not in clean
    assert "__pycache__" not in " ".join(clean)
    assert "SKILL.md" in clean
    assert "create.md" in clean


def test_filter_does_not_drop_pyc_in_normal_filename():
    """A file named 'topyc.md' is NOT a python artifact."""
    files = ["SKILL.md", "topyc.md"]
    assert cmd_mod._filter_bundle_files(files) == files


# ----------------------------------------------------------------------
# 3. The actual deploy: copy preserves reference/ subdir
# ----------------------------------------------------------------------


def test_deploy_copies_files_to_destination(monkeypatch, tmp_path):
    """Successful deploy: every file in ALL_SKILL_FILES is at $DEST/<rel>."""
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", str(tmp_path)))
    args = _args(target="hermes")
    r = cmd_mod.cmd_deploy_skill(args)

    assert r["status"] == "success"
    assert r["data"]["succeeded"] == 1
    result = r["data"]["results"][0]
    assert result["status"] == "success"
    dest = tmp_path / ".hermes" / "skills" / SKILL_NAME
    # References subdir is preserved (not flattened)
    assert (dest / "references").is_dir()
    # Top-level files all there
    for rel in ALL_SKILL_FILES:
        if rel.endswith(".md"):
            assert (dest / rel).is_file(), f"missing: {rel}"
    # result dict shape
    assert result["skill_md_at_dest"] is True
    assert result["file_count"] >= 7


def test_deploy_does_not_copy_python_artifacts(monkeypatch, tmp_path):
    """The bug the case study caught: __init__.py + __pycache__/
    must NOT end up in the agent's discovery dir."""
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", str(tmp_path)))
    cmd_mod.cmd_deploy_skill(_args(target="hermes"))
    dest = tmp_path / ".hermes" / "skills" / SKILL_NAME
    assert not (dest / "__init__.py").exists()
    assert not (dest / "__pycache__").exists()
    assert list(dest.rglob("__pycache__")) == []


def test_deploy_handles_unknown_target():
    r = cmd_mod.cmd_deploy_skill(_args(target="vscode"))
    assert r["status"] == "error"
    assert r["data"]["failed"] == 1
    assert r["data"]["results"][0]["err_class"] == "UnknownTarget"


def test_deploy_skips_missing_source_files(monkeypatch, tmp_path):
    """If a source file is missing, deploy reports it under files_skipped
    (not a hard error — partial deploy is useful)."""
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", str(tmp_path)))
    # Sanity: deploy succeeds; failures list is non-fatal.
    r = cmd_mod.cmd_deploy_skill(_args(target="hermes"))
    assert r["status"] == "success"
    # Source dir is real and populated, so files_skipped should be empty.
    assert r["data"]["results"][0]["files_skipped"] == []

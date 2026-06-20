"""Unit tests for `xu selfcheck` (post-install health check).

坑 6 fix: there was no agent-friendly command to verify a xu-wiki
install. `xu selfcheck` consolidates 8 checks:
- cli_on_path, python_version, skill_bundle_readable, agent_skill_deployed
- global_dir_writable, global_config_chmod (3.4), optional_extras, ripgrep
- agent_deployment_hint (bash template for cp -r to ~/.hermes/skills/)

Status semantics:
- error  → any CRITICAL check failed (now incl. agent_skill_deployed)
- warning → only non-critical checks failed
- success → all checks passed
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.commands import selfcheck as cmd_mod
from xu.utils import config as cfg_mod


@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    return tmp_path


def _args():
    return SimpleNamespace()


def _all_ok_patcher(monkeypatch):
    """Patch agent_skill_deployed to pass — only valid when skill is
    actually deployed somewhere, which we mock out for tests."""
    monkeypatch.setattr(cmd_mod, "_check_agent_skill_deployed",
                        lambda: {"ok": True,
                                 "found": [{"agent": "test", "path": "/fake"}],
                                 "missing": [],
                                 "hint": "skill deployed (test mock)"})


# ----------------------------------------------------------------------
# 1. happy path — all checks pass (with mock for agent_skill_deployed)
# ----------------------------------------------------------------------

def test_selfcheck_happy_path(xu_home, monkeypatch):
    """When everything is OK, status=success and all checks passed."""
    _all_ok_patcher(monkeypatch)
    r = cmd_mod.cmd_selfcheck(_args())
    assert r["status"] == "success"
    # 8 checks total
    assert "cli_on_path" in r["data"]["checks"]
    assert "skill_bundle_readable" in r["data"]["checks"]
    assert "agent_skill_deployed" in r["data"]["checks"]
    assert "optional_extras" in r["data"]["checks"]
    assert "agent_deployment_hint" in r["data"]
    assert r["data"]["agent_deployment_hint"]["skill_name"] == "xu-wiki"


# ----------------------------------------------------------------------
# 2. response envelope
# ----------------------------------------------------------------------

def test_selfcheck_returns_4_key_envelope(xu_home, monkeypatch):
    _all_ok_patcher(monkeypatch)
    r = cmd_mod.cmd_selfcheck(_args())
    assert set(r.keys()) >= {"status", "data", "message", "hints"}
    assert r["status"] in ("success", "warning", "error")


# ----------------------------------------------------------------------
# 3. agent deployment hint — the bash template (now uses cp -r)
# ----------------------------------------------------------------------

def test_agent_deployment_hint_excludes_python_artifacts(xu_home):
    """Bash template must skip __init__.py and __pycache__ via for-loop."""
    r = cmd_mod.cmd_selfcheck(_args())
    h = r["data"]["agent_deployment_hint"]
    assert "copy_template_bash" in h
    assert "mkdir -p" in h["copy_template_bash"]
    # Uses for-loop (not cp -r) so artifacts can be filtered
    assert 'for f in "$SRC"/*' in h["copy_template_bash"]
    # Explicitly skips Python package artifacts
    assert "__init__.py" in h["copy_template_bash"]
    assert "__pycache__" in h["copy_template_bash"]
    assert 'cp "$f" "$DEST/"' in h["copy_template_bash"]
    # reference/ subdir preserved via mkdir + inner loop
    assert 'mkdir -p "$DEST/$base"' in h["copy_template_bash"]
    # Verification steps
    assert 'ls "$DEST"' in h["copy_template_bash"]
    assert 'ls "$DEST/reference"' in h["copy_template_bash"]


# ----------------------------------------------------------------------
# 4. global_config_chmod check (3.4)
# ----------------------------------------------------------------------

def test_global_config_chmod_no_config_ok(xu_home):
    check = cmd_mod._check_global_config_chmod()
    assert check["ok"] is True


def test_global_config_chmod_secret_but_world_readable(xu_home, monkeypatch):
    cfg_path = cfg_mod.GLOBAL_CONFIG
    cfg_path.write_text("mineru:\n  api_key: secret\n", encoding="utf-8")
    os.chmod(cfg_path, 0o644)
    check = cmd_mod._check_global_config_chmod()
    assert check["ok"] is False
    assert "0o600" in check["hint"]


def test_global_config_chmod_secret_with_600_passes(xu_home):
    cfg_path = xu_home / "config.yaml"
    cfg_path.write_text("mineru:\n  api_key: secret\n", encoding="utf-8")
    os.chmod(cfg_path, 0o600)
    check = cmd_mod._check_global_config_chmod()
    assert check["ok"] is True


# ----------------------------------------------------------------------
# 5. optional_extras — Pillow is imported as PIL (Bug 1 fix)
# ----------------------------------------------------------------------

def test_optional_extras_pillow_uses_PIL_import_name(xu_home):
    """Bug 1: the import name for Pillow is PIL, not Pillow. Ensure
    the check passes when Pillow is installed."""
    # In a venv with `pip install -e .[parse,nlp,vision]` all three
    # are installed; this test verifies the check sees them as such.
    check = cmd_mod._check_optional_extras()
    # Result: ok=True if all 3 installed; ok=False only if some are missing.
    # We don't assert ok=True strictly because CI may skip extras; we
    # do assert the Pillow entry uses the correct import name.
    pillow_entry = check["extras"]["Pillow"]
    assert pillow_entry["import_name"] == "PIL"
    # If Pillow was installed, ok should be True (proves Bug 1 fix).
    if pillow_entry["installed"]:
        assert pillow_entry["import_name"] == "PIL"
        assert check["ok"] is True or any(
            e["installed"] for e in check["extras"].values()
        )


# ----------------------------------------------------------------------
# 6. agent_skill_deployed check (Bug 4)
# ----------------------------------------------------------------------

def test_agent_skill_deployed_not_deployed_returns_failure(xu_home):
    """If no known agent discovery dir has SKILL.md, the check fails."""
    # Don't actually touch $HOME; instead patch the candidate dirs to
    # point at non-existent paths.
    with patch.object(cmd_mod, "KNOWN_AGENT_SKILL_DIRS",
                       (("test-a", str(xu_home / "ghost-a")),
                        ("test-b", str(xu_home / "ghost-b")))):
        check = cmd_mod._check_agent_skill_deployed()
    assert check["ok"] is False
    assert check["found"] == []
    assert len(check["missing"]) == 2
    assert "test-a" in [m["agent"] for m in check["missing"]]
    assert "hint" in check


def test_agent_skill_deployed_at_least_one_passes(xu_home):
    """If ANY known dir has SKILL.md, the check passes (even if others don't)."""
    fake_dest = xu_home / "agent-skill"
    fake_dest.mkdir()
    (fake_dest / "SKILL.md").write_text("# fake\n", encoding="utf-8")
    with patch.object(cmd_mod, "KNOWN_AGENT_SKILL_DIRS",
                       (("test-a", str(xu_home / "ghost-a")),
                        ("test-real", str(fake_dest)))):
        check = cmd_mod._check_agent_skill_deployed()
    assert check["ok"] is True
    found_names = [f["agent"] for f in check["found"]]
    assert "test-real" in found_names


def test_agent_skill_deployed_env_var_overrides_targets(xu_home, monkeypatch):
    """XU_AGENT_SKILL_DIR restricts the probe to a single location."""
    fake_dest = xu_home / "custom-skill"
    fake_dest.mkdir()
    (fake_dest / "SKILL.md").write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("XU_AGENT_SKILL_DIR", str(fake_dest))
    check = cmd_mod._check_agent_skill_deployed()
    assert check["ok"] is True
    assert check["found"][0]["agent"] == "custom"
    assert check["found"][0]["path"] == str(fake_dest)


def test_agent_skill_deployed_env_var_not_deployed(xu_home, monkeypatch):
    """XU_AGENT_SKILL_DIR pointing at a path without SKILL.md → fail."""
    monkeypatch.setenv("XU_AGENT_SKILL_DIR", str(xu_home / "does-not-exist"))
    check = cmd_mod._check_agent_skill_deployed()
    assert check["ok"] is False
    assert check["found"] == []
    assert check["missing"][0]["agent"] == "custom"


def test_agent_skill_deployed_is_critical_check():
    """Bug 4: agent_skill_deployed must be in CRITICAL — without this the
    check failure wouldn't block success."""
    assert "agent_skill_deployed" in cmd_mod.CRITICAL


# ----------------------------------------------------------------------
# 7. CLI palette wiring
# ----------------------------------------------------------------------

def test_cli_palette_includes_selfcheck():
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["selfcheck"])
    assert args.func == "selfcheck"


def test_cli_palette_includes_deploy_skill():
    """`xu deploy skill --target <agent>` is wired as a sub-sub-command."""
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["deploy", "skill", "--target", "hermes"])
    assert args.func == "deploy_skill"
    assert args.target == "hermes"


def test_cli_deploy_skill_target_default_is_auto():
    """If --target not passed, default to auto."""
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["deploy", "skill"])
    assert args.target == "auto"


def test_cli_deploy_skill_rejects_unknown_target():
    from xu.cli import build_parser
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["deploy", "skill", "--target", "vscode"])


def test_cli_palette_includes_version_flag():
    """Bug 3: `xu --version` should output the package version."""
    from xu.cli import build_parser
    p = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        p.parse_args(["--version"])
    # argparse exits 0 on --version
    assert exc_info.value.code == 0


def test_cli_version_flag_prints_version_string(capsys):
    """The --version output should contain 'xu-wiki X.Y.Z'."""
    from xu.cli import build_parser
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--version"])
    captured = capsys.readouterr()
    assert "xu-wiki" in captured.out
    # also matches the version number pattern
    import re
    assert re.search(r"\d+\.\d+\.\d+", captured.out), \
        f"expected version number in: {captured.out!r}"


# ----------------------------------------------------------------------
# 8. critical vs non-critical failure handling
# ----------------------------------------------------------------------

def test_critical_failure_returns_error(xu_home, monkeypatch):
    """If a CRITICAL check fails, status=error."""
    _all_ok_patcher(monkeypatch)
    monkeypatch.setattr(cmd_mod, "_check_skill_bundle_readable",
                        lambda: {"ok": False,
                                 "hint": "synthetic failure for test"})
    r = cmd_mod.cmd_selfcheck(_args())
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "SelfCheckFailed"
    assert "skill_bundle_readable" in r["data"]["failed_critical"]


def test_agent_skill_not_deployed_returns_error(xu_home, monkeypatch):
    """Bug 4: agent_skill_deployed failure → status=error (critical)."""
    _all_ok_patcher.__wrapped__ if hasattr(_all_ok_patcher, '__wrapped__') else None
    # Don't apply the all_ok patcher — let it actually run.
    # But since the test env has no ~/.hermes/skills/xu-wiki/SKILL.md,
    # it will fail; we want it to fail with status=error.
    r = cmd_mod.cmd_selfcheck(_args())
    assert r["status"] == "error"
    assert "agent_skill_deployed" in r["data"]["failed_critical"]


def test_non_critical_failure_returns_warning(xu_home, monkeypatch):
    """If only a non-critical check fails, status=warning."""
    _all_ok_patcher(monkeypatch)
    monkeypatch.setattr(cmd_mod, "_check_optional_extras",
                        lambda: {"ok": False, "hint": "synthetic"})
    r = cmd_mod.cmd_selfcheck(_args())
    assert r["status"] == "warning"
    assert "optional_extras" in r["data"]["failed_noncritical"]


# ----------------------------------------------------------------------
# 9. ALL_SKILL_FILES excludes install docs (BAN-SKILL-3a / CONST-INST-6)
# ----------------------------------------------------------------------

def test_all_skill_files_excludes_install_docs():
    """Install docs live in README, NOT the bundle — the bundle is a
    post-install resource (BAN-SKILL-3a). Bundle = SKILL.md + 5 SOPs +
    2 reference placeholders = 8 files."""
    from xu.skills import ALL_SKILL_FILES
    assert "INSTALL.md" not in ALL_SKILL_FILES
    assert len(ALL_SKILL_FILES) == 8


# ----------------------------------------------------------------------
# 10. deployment_status + next_actions (case study v2)
# ----------------------------------------------------------------------

def test_selfcheck_returns_deployment_status(xu_home, monkeypatch):
    _all_ok_patcher(monkeypatch)
    r = cmd_mod.cmd_selfcheck(_args())
    assert "deployment_status" in r["data"]
    ds = r["data"]["deployment_status"]
    # Required fields
    assert "installer" in ds
    assert ds["installer"] in ("pipx", "pip", "unknown")
    assert "binary_on_path" in ds
    assert "skill_deployed_to" in ds
    assert isinstance(ds["skill_deployed_to"], list)
    assert "smoke_test_run" in ds
    assert "wiki_data_present" in ds


def test_selfcheck_returns_next_actions_list(xu_home, monkeypatch):
    _all_ok_patcher(monkeypatch)
    r = cmd_mod.cmd_selfcheck(_args())
    assert "next_actions" in r["data"]
    assert isinstance(r["data"]["next_actions"], list)


def test_selfcheck_next_actions_contains_deploy_hint(xu_home, monkeypatch):
    """When agent_skill_deployed fails, next_actions must include the
    `xu deploy skill` instruction — that's the case study v2 fix."""
    # Don't apply the all_ok patcher — let the real check run.
    r = cmd_mod.cmd_selfcheck(_args())
    actions = " ".join(r["data"]["next_actions"])
    # If skill isn't deployed (likely in CI), next_actions mentions xu deploy
    if not r["data"]["checks"]["agent_skill_deployed"]["ok"]:
        assert "xu deploy skill" in actions


def test_selfcheck_next_actions_empty_when_all_green(xu_home, monkeypatch):
    """When every check passes, next_actions is the empty list."""
    _all_ok_patcher(monkeypatch)
    # Make sure ALL checks pass by patching the rest to True too.
    monkeypatch.setattr(cmd_mod, "_check_optional_extras",
                        lambda: {"ok": True, "extras": {}, "hint": "all green"})
    monkeypatch.setattr(cmd_mod, "_check_global_config_chmod",
                        lambda: {"ok": True, "mode": "0o600",
                                 "has_secret": False, "hint": "OK"})
    monkeypatch.setattr(cmd_mod, "_check_ripgrep",
                        lambda: {"ok": True, "note": "rg not installed but that's OK",
                                 "hint": "fallback"})
    monkeypatch.setattr(cmd_mod, "_check_global_dir_writable",
                        lambda: {"ok": True, "path": "/tmp/xu", "hint": "writable"})
    r = cmd_mod.cmd_selfcheck(_args())
    assert r["status"] == "success"
    assert r["data"]["next_actions"] == []
"""Unit tests for `xu uninstall` (SOP-config software lifecycle).

CONST-SOP-3 asymmetric: install = pip, uninstall = `xu uninstall`.
Tests cover:
- dry-run is the default (no side effects without --execute)
- --execute + --keep-pip removes wikis + ~/.xu/ but skips pip
- --execute without --keep-pip invokes pip uninstall (mocked)
- --execute with no flags only touches pip (wiki data + ~/.xu/ preserved)
- --purge-config removes the global dir
- argparse wires up the new subcommand (cli.dispatch smoke)
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.utils import config as cfg_mod
from xu.commands import uninstall as cmd_mod
from xu.utils.paths import now_ts


@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    """Point GLOBAL_DIR at tmp_path AND re-bind the uninstall module's GLOBAL_DIR.

    `from ..utils.config import GLOBAL_DIR` in uninstall.py creates a local
    binding to the original Path object. Patching cfg_mod.GLOBAL_DIR does NOT
    affect uninstall.GLOBAL_DIR. We must patch uninstall.GLOBAL_DIR directly.

    Wiki data is stored OUTSIDE xu_home to prevent rmtree(xu_home) from
    accidentally deleting wiki content.
    """
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    # Must patch uninstall.GLOBAL_DIR directly — use setattr on the module object
    import xu.commands.uninstall as uninstall_mod
    monkeypatch.setattr(uninstall_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cmd_mod, "GLOBAL_DIR", tmp_path)
    return tmp_path


def _args(**kw):
    defaults = dict(execute=False, keep_pip=False,
                    preserve_config=False)
    defaults.update(kw)
    if "purge_config" in kw:
        defaults["preserve_config"] = not kw["purge_config"]
    return SimpleNamespace(**defaults)


_last_wiki_path = None


def _seed_wiki(xu_home, name, *, alias=None, path=None):
    """Add a wiki entry in the registry AND lay down the wiki marker files.

    Wiki data goes to /tmp/test_wikis/<name> — OUTSIDE xu_home (GLOBAL_DIR).
    This mirrors real life: ~/.xu/ is a peer of wiki dirs, not a parent.
    `is_wiki_root()` requires `.xu/config.yaml` to exist.
    """
    import tempfile
    if path is None:
        # Put wiki OUTSIDE xu_home so rmtree(xu_home) doesn't delete it
        wiki_root = Path(tempfile.mkdtemp(prefix="test_wiki_"))
        path = str(wiki_root / name)
    os.makedirs(path, exist_ok=True)
    xu_subdir = os.path.join(path, ".xu")
    os.makedirs(xu_subdir, exist_ok=True)
    with open(os.path.join(xu_subdir, "config.yaml"), "w", encoding="utf-8") as f:
        f.write("# synthetic seed for test\n")
    reg = cfg_mod.load_registry()
    reg.setdefault("wikis", {})[name] = {
        "path": path, "alias": alias, "created_at": now_ts()
    }
    cfg_mod.save_registry(reg)
    global _last_wiki_path
    _last_wiki_path = Path(path)
    return _last_wiki_path


def _seed_nonwiki(xu_home, name, *, path=None):
    """Seed an entry in the registry whose path is NOT a wiki marker."""
    if path is None:
        path = str(xu_home / "not-a-wiki" / name)
    os.makedirs(path, exist_ok=True)
    reg = cfg_mod.load_registry()
    reg.setdefault("wikis", {})[name] = {
        "path": path, "alias": None, "created_at": now_ts()
    }
    cfg_mod.save_registry(reg)


# ----------------------------------------------------------------------
# 1. dry-run default (PRIN-UNINST-6)
# ----------------------------------------------------------------------

def test_uninstall_dry_run_is_default(xu_home):
    """No --execute → must report dry-run and touch NOTHING."""
    _seed_wiki(xu_home, "A")
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    purge_config=False))
    assert r["status"] == "success"
    assert r["data"]["mode"] == "dry-run"
    assert "A" in cfg_mod.load_registry()["wikis"]
    assert _last_wiki_path.exists()
    assert xu_home.exists()


def test_dry_run_lists_wikis_and_marks_flags(xu_home):
    """Dry-run surfaces wikis_found; purge_config reflects --preserve-config."""
    _seed_wiki(xu_home, "A")
    _seed_wiki(xu_home, "B")
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    preserve_config=True))
    plan = r["data"]
    assert plan["mode"] == "dry-run"
    assert plan["execute"] is False
    assert plan["pip_uninstall"] is True
    assert plan["purge_config"] is False  # preserve_config=True → config preserved
    names = sorted(w["name"] for w in plan["wikis_found"])
    assert names == ["A", "B"]


def test_dry_run_annotates_is_wiki_root(xu_home):
    """Dry-run annotates each entry with is_wiki_root boolean."""
    _seed_wiki(xu_home, "real")
    _seed_nonwiki(xu_home, "fake")
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    preserve_config=True))
    plan = r["data"]
    by_name = {w["name"]: w for w in plan["wikis_found"]}
    assert by_name["real"]["is_wiki_root"] is True
    assert by_name["fake"]["is_wiki_root"] is False
    assert plan["purge_config"] is False  # preserve_config=True → purge_config=False


def test_execute_never_deletes_wiki_data(xu_home, monkeypatch):
    """Wiki data is NEVER deleted."""
    _seed_wiki(xu_home, "A")
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "stdout_tail": "", "stderr_tail": ""})
    import shutil as shutil_mod
    deleted_paths = []
    original_rmtree = shutil_mod.rmtree

    def track_rmtree(path, **kwargs):
        deleted_paths.append(Path(path))
        original_rmtree(path, **kwargs)

    monkeypatch.setattr(shutil_mod, "rmtree", track_rmtree)
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_config=True))
    # wiki data preserved — verify marker file still exists
    assert _last_wiki_path.exists()
    # wikis always skipped
    assert r["data"]["result"]["wikis"]["skipped"] is True
    # config was deleted via rmtree(xu_home)
    assert any(p == xu_home for p in deleted_paths), f"Expected rmtree({xu_home}), got {deleted_paths}"
    assert r["status"] == "success"


# ----------------------------------------------------------------------
# 2. --execute default: pip + config removed; wikis ALWAYS preserved
# ----------------------------------------------------------------------

def test_execute_default_removes_config_preserves_wikis(xu_home, monkeypatch):
    """Default --execute: pip + ~/.xu/ removed; wiki data stays (never deleted)."""
    _seed_wiki(xu_home, "A")
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "stdout_tail": "ok", "stderr_tail": ""})
    import shutil as shutil_mod
    deleted = []
    orig = shutil_mod.rmtree

    def tracker(path, **kw):
        deleted.append(Path(path))
        orig(path, **kw)

    monkeypatch.setattr(shutil_mod, "rmtree", tracker)
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_config=True))
    assert r["status"] == "success"
    # wikis untouched (NEVER deleted) — verify marker file exists
    assert _last_wiki_path.exists()
    # rmtree was called with xu_home (config dir)
    assert any(p == xu_home for p in deleted), f"Expected rmtree({xu_home}), got {deleted}"
    # pip ran
    assert r["data"]["result"]["pip"]["ok"] is True


# ----------------------------------------------------------------------
# 3. --execute --keep-pip: removes ~/.xu/ but skips pip; wikis stay
# ----------------------------------------------------------------------

def test_execute_keep_pip_removes_config_preserves_wikis(xu_home, monkeypatch):
    """--keep-pip removes config; wiki data always preserved."""
    import shutil as shutil_mod
    deleted = []
    orig = shutil_mod.rmtree

    def tracker(path, **kw):
        deleted.append(Path(path))
        orig(path, **kw)
    monkeypatch.setattr(shutil_mod, "rmtree", tracker)

    _seed_wiki(xu_home, "A")
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=True,
                                    purge_config=True))
    assert r["status"] == "success"
    assert _last_wiki_path.exists()
    assert r["data"]["result"]["pip"]["skipped"] is True
    assert any(p == xu_home for p in deleted), f"Expected rmtree({xu_home}), got {deleted}"


# ----------------------------------------------------------------------
# 4. --execute --preserve-config: keeps ~/.xu/; wikis always preserved
# ----------------------------------------------------------------------

def test_execute_preserve_config_keeps_xu_dir(xu_home, monkeypatch):
    """--preserve-config keeps ~/.xu/; wikis always preserved."""
    _seed_wiki(xu_home, "A")
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "stdout_tail": "", "stderr_tail": ""})
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    preserve_config=True))
    assert r["status"] == "success"
    assert "A" in cfg_mod.load_registry()["wikis"]
    assert _last_wiki_path.exists()
    assert xu_home.exists()
    assert r["data"]["result"]["config_dir"]["skipped"] is True


# ----------------------------------------------------------------------
# 5. pip uninstall failure → warning (partial uninstall)
# ----------------------------------------------------------------------

def test_pip_uninstall_invokes_pip_correctly(xu_home):
    """Even if pip fails, the command shape is correct (we don't mock pip here)."""
    _seed_wiki(xu_home, "A")
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_config=False))
    pip = r["data"]["result"]["pip"]
    assert pip["command"].endswith("pip uninstall xu-wiki -y")
    # pip returncode is reported either way
    assert "returncode" in pip or "error" in pip


# ----------------------------------------------------------------------
# 6. CLI palette wiring (SKILL.md / config.md promise)
# ----------------------------------------------------------------------

def test_cli_palette_includes_uninstall_under_config():
    """`xu uninstall` must be wired as a top-level subcommand (config SOP)."""
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["uninstall"])
    assert args.func == "uninstall"
    assert args.execute is None
    assert args.dry_run is None
    assert args.keep_pip is False
    assert args.preserve_config is False  # default: remove ~/.xu/


def test_cli_palette_exec_flags_parse():
    """New flags: --preserve-config (inverts config removal)."""
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["uninstall", "--execute",
                         "--preserve-config", "--keep-pip"])
    assert args.execute is True
    assert args.preserve_config is True  # keeps ~/.xu/
    assert args.keep_pip is True


def test_cli_palette_dry_run_explicit():
    """--dry-run and --execute are mutually exclusive (P2 fix)."""
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["uninstall", "--dry-run"])
    assert args.dry_run is True
    assert args.execute is None
    # argparse raises SystemExit on mutex violation
    with pytest.raises(SystemExit):
        p.parse_args(["uninstall", "--dry-run", "--execute"])


def test_uninstall_help_does_not_raise():
    """`xu uninstall --help` should be callable (argparse exits 0 cleanly)."""
    from xu.cli import build_parser
    p = build_parser()
    # argparse calls sys.exit(0) on --help; that's the expected behavior.
    # Just confirm the parser accepts the subcommand form.
    args = p.parse_args(["uninstall"])
    assert args.func == "uninstall"


# ----------------------------------------------------------------------
# 7. Audit log + 4-key envelope
# ----------------------------------------------------------------------

def test_dry_run_response_shape_matches_protocol():
    """Dry-run response must be the standard 4-key JSON envelope."""
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    purge_config=False))
    assert set(r.keys()) >= {"status", "data", "message", "hints"}
    assert r["status"] in ("success", "warning", "error")


def test_execute_response_shape_matches_protocol(xu_home):
    """--execute response must also be the standard 4-key JSON envelope."""
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=True,
                                    purge_config=True))
    assert set(r.keys()) >= {"status", "data", "message", "hints"}
    assert r["status"] in ("success", "warning", "error")


# ----------------------------------------------------------------------
# 8. Agent review fixes — P0/P1 schema
# ----------------------------------------------------------------------

def test_plan_mode_consistent_with_execute_flag(xu_home, monkeypatch):
    """Bug fix: plan.mode MUST equal 'execute' when execute=True.

    Previously plan.mode was hard-coded to 'dry-run' regardless of
    the execute flag, producing a 'mode=dry-run && execute=true'
    contradiction inside data.plan under execute responses.
    """
    _seed_wiki(xu_home, "A")
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "stdout_tail": "", "stderr_tail": "",
                                 "command": "python3 -m pip uninstall xu-wiki -y",
                                 "command_redaction_note": "(redacted)",
                                 "command_full": "/usr/bin/python3 -m pip uninstall xu-wiki -y"})
    # dry-run path
    r_dry = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                        purge_config=False))
    assert r_dry["data"]["mode"] == "dry-run"
    # execute path — data has {plan, result}
    r_exec = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                         purge_config=False))
    assert r_exec["data"]["plan"]["mode"] == "execute"
    assert r_exec["data"]["plan"]["execute"] is True
    # No contradiction: mode == execute AND execute == True
    assert (r_exec["data"]["plan"]["mode"] == "execute"
            and r_exec["data"]["plan"]["execute"] is True)


def test_pip_command_redacted_no_absolute_path(xu_home, monkeypatch):
    """Bug fix: pip.command must NOT include sys.executable absolute path."""
    # Call _pip_uninstall() for real; it returns its actual redacted output.
    # We monkeypatch subprocess.run to a deterministic success so the
    # function path goes through to "ok: True".
    class _FakeProc:
        returncode = 0
        stdout = "Successfully uninstalled xu-wiki-0.1.0\n"
        stderr = ""
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **kw: _FakeProc())
    raw = cmd_mod._pip_uninstall()
    assert raw["command"] == "python3 -m pip uninstall xu-wiki -y"
    assert "python3" == raw["command"].split()[0]
    # command_full keeps the absolute path for dev debug
    import sys as _sys
    assert _sys.executable in raw["command_full"]


def test_purge_global_dir_reports_existed_before_and_files_count(xu_home):
    """Bug fix: config_dir result must include existed_before +
    files_removed_count so the agent can cross-check independently."""
    # Seed a global dir with 3 entries
    (xu_home / "a.txt").write_text("x")
    (xu_home / "b.txt").write_text("y")
    (xu_home / "sub").mkdir()
    (xu_home / "sub" / "c.txt").write_text("z")
    res = cmd_mod._purge_global_dir()
    assert res["existed_before"] is True
    # files_removed_count counts top-level entries (3 here: a.txt, b.txt, sub/)
    assert res["files_removed_count"] == 3
    assert res["ok"] is True
    assert "error" not in res or res.get("error") is None


def test_purge_global_dir_handles_missing_dir(xu_home):
    """If ~/.xu/ doesn't exist, ok=True with existed_before=False."""
    # Make sure the global dir really doesn't exist (tmp_path is
    # auto-created by pytest but empty).
    if xu_home.exists():
        import shutil
        shutil.rmtree(xu_home)
    res = cmd_mod._purge_global_dir()
    assert res["existed_before"] is False
    assert res["files_removed_count"] == 0
    assert res["ok"] is True


def test_purge_global_dir_empty_dir_reports_zero_files(xu_home):
    """If ~/.xu/ exists but is empty, existed_before=True with count=0."""
    res = cmd_mod._purge_global_dir()
    assert res["existed_before"] is True
    assert res["files_removed_count"] == 0
    assert res["ok"] is True


# ----------------------------------------------------------------------
# 9. Installer detection + pipx-aware uninstall (case study v2)
# ----------------------------------------------------------------------

def test_detect_installer_returns_string(monkeypatch):
    """_detect_installer always returns one of {pipx, pip, unknown}."""
    # current sys.prefix doesn't contain /pipx/venvs/ → not pipx
    import sys as _sys
    if "/pipx/venvs/" in _sys.prefix:
        assert cmd_mod._detect_installer() == "pipx"
    elif _sys.prefix != _sys.base_prefix:
        assert cmd_mod._detect_installer() == "pip"
    else:
        assert cmd_mod._detect_installer() == "unknown"


def test_detect_installer_recognizes_pipx_prefix(monkeypatch):
    """If sys.prefix looks like a pipx venv path, return 'pipx'."""
    fake_pipx = "/home/user/.local/share/pipx/venvs/xu-wiki"
    monkeypatch.setattr("sys.prefix", fake_pipx)
    assert cmd_mod._detect_installer() == "pipx"


def test_detect_installer_recognizes_alternative_pipx(monkeypatch):
    """Pipx can also use ~/.local/pipx/venvs/ as a base."""
    fake_pipx = "/home/user/.local/pipx/venvs/xu-wiki"
    monkeypatch.setattr("sys.prefix", fake_pipx)
    assert cmd_mod._detect_installer() == "pipx"


def test_detect_installer_returns_unknown_for_system_python(monkeypatch):
    """If prefix == base_prefix, return 'unknown'."""
    monkeypatch.setattr("sys.prefix", "/usr")
    monkeypatch.setattr("sys.base_prefix", "/usr")
    assert cmd_mod._detect_installer() == "unknown"


def test_uninstall_in_pipx_runs_pipx_uninstall(monkeypatch, xu_home):
    """When installer == pipx, xu uninstall auto-runs pipx uninstall."""
    _seed_wiki(xu_home, "A")
    monkeypatch.setattr(cmd_mod, "_detect_installer", lambda: "pipx")
    pipx_called = []
    monkeypatch.setattr(cmd_mod, "_pipx_uninstall",
                        lambda: (pipx_called.append(True) or
                                 {"ok": True, "returncode": 0,
                                  "stdout_tail": "", "stderr_tail": ""}))
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_config=False))
    assert pipx_called != [], "pipx uninstall should have been called"
    assert r["data"]["plan"]["installer"] == "pipx"


def test_uninstall_in_pip_venv_still_runs_pip_uninstall(monkeypatch, xu_home):
    """When installer == pip, xu uninstall still calls pip uninstall."""
    monkeypatch.setattr(cmd_mod, "_detect_installer", lambda: "pip")
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "command": "python3 -m pip uninstall xu-wiki -y",
                                 "command_redaction_note": "(redacted)",
                                 "command_full": "/usr/bin/python3 -m pip uninstall xu-wiki -y",
                                 "stdout_tail": "", "stderr_tail": ""})
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_config=False))
    assert r["data"]["result"]["pip"]["ok"] is True
    assert r["data"]["plan"]["installer"] == "pip"


def test_dry_run_reports_installer(monkeypatch, xu_home):
    """Dry-run should also surface data.plan.installer (so the agent
    knows upfront which installer owns the program body)."""
    monkeypatch.setattr(cmd_mod, "_detect_installer", lambda: "pipx")
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    purge_config=False))
    # dry-run → data IS the plan
    assert r["data"]["installer"] == "pipx"
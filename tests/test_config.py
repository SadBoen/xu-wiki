"""Unit tests for SOP-config commands (alias / register / unregister / config).

Tests use isolated XU_HOME via monkeypatch on the captured GLOBAL_DIR module
attributes (set at import time from XU_HOME env). The test wiki is seeded
directly into the registry yaml — no real filesystem wiki is required for
config SOP, since the SOP touches only the global registry + global config.
"""
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.utils import config as cfg_mod
from xu.commands import config as cmd_mod
from xu.utils.paths import now_ts


@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    """Point xu.utils.config.GLOBAL_DIR at tmp_path."""
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg_mod, "REGISTRY_FILE", tmp_path / "registry.yaml")
    monkeypatch.setattr(cmd_mod, "GLOBAL_DIR", tmp_path)
    return tmp_path


def _seed_wiki(xu_home, name, *, alias=None, path=None):
    """Write a registry.yaml with one wiki entry."""
    if path is None:
        path = str(xu_home / "wikis" / name)
    registry = {"wikis": {name: {"path": path, "alias": alias, "created_at": now_ts()}}}
    cfg_mod.save_registry(registry)


def _args(**kw):
    """Build a SimpleNamespace with only the fields a command expects."""
    return SimpleNamespace(**kw)


def test_alias_set_happy(xu_home):
    _seed_wiki(xu_home, "NepTune")
    r = cmd_mod.cmd_alias_set(_args(wiki="NepTune", alias="NB"))
    assert r["status"] == "success"
    assert r["data"]["name"] == "NepTune"
    assert r["data"]["alias"] == "NB"
    assert r["data"]["previous_alias"] is None


def test_alias_set_changes_existing(xu_home):
    _seed_wiki(xu_home, "NepTune", alias="NB")
    r = cmd_mod.cmd_alias_set(_args(wiki="NepTune", alias="Neptune"))
    assert r["status"] == "success"
    assert r["data"]["previous_alias"] == "NB"
    assert r["data"]["alias"] == "Neptune"


def test_alias_set_by_alias_works(xu_home):
    _seed_wiki(xu_home, "NepTune", alias="NB")
    r = cmd_mod.cmd_alias_set(_args(wiki="NB", alias="New"))
    assert r["status"] == "success"
    assert r["data"]["name"] == "NepTune"


def test_alias_set_conflict(xu_home):
    cfg_mod.save_registry({
        "wikis": {
            "A": {"path": "/tmp/a", "alias": None, "created_at": now_ts()},
            "B": {"path": "/tmp/b", "alias": "X", "created_at": now_ts()},
        }
    })
    r = cmd_mod.cmd_alias_set(_args(wiki="A", alias="X"))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "AliasConflict"
    assert r["data"]["conflicting_wiki"] == "B"


def test_alias_set_invalid_name(xu_home):
    _seed_wiki(xu_home, "A")
    r = cmd_mod.cmd_alias_set(_args(wiki="A", alias="bad name!"))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "InvalidName"


def test_alias_set_not_found(xu_home):
    r = cmd_mod.cmd_alias_set(_args(wiki="ghost", alias="x"))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "NameNotFound"


def test_alias_unset_happy(xu_home):
    _seed_wiki(xu_home, "A", alias="X")
    r = cmd_mod.cmd_alias_unset(_args(wiki="A"))
    assert r["status"] == "success"
    assert r["data"]["previous_alias"] == "X"


def test_alias_unset_no_alias_is_warning(xu_home):
    _seed_wiki(xu_home, "A")
    r = cmd_mod.cmd_alias_unset(_args(wiki="A"))
    assert r["status"] == "warning"


def test_alias_show(xu_home):
    _seed_wiki(xu_home, "A", alias="X")
    r = cmd_mod.cmd_alias_show(_args(wiki="A"))
    assert r["status"] == "success"
    assert r["data"]["alias"] == "X"
    assert r["data"]["name"] == "A"


def test_register_happy(xu_home, tmp_path):
    target = tmp_path / "wiki_dir"
    target.mkdir()
    r = cmd_mod.cmd_register(_args(name="MyWiki", path=str(target)))
    assert r["status"] == "success"
    assert r["data"]["name"] == "MyWiki"
    assert r["data"]["path"] == str(target.resolve())
    assert r["data"]["alias"] is None
    # registry was actually written
    reg = cfg_mod.load_registry()
    assert "MyWiki" in reg["wikis"]


def test_register_with_alias(xu_home, tmp_path):
    target = tmp_path / "wiki_dir"
    target.mkdir()
    r = cmd_mod.cmd_register(_args(name="MyWiki", path=str(target), alias="MW"))
    assert r["status"] == "success"
    assert r["data"]["alias"] == "MW"


def test_register_idempotent_warns(xu_home, tmp_path):
    target = tmp_path / "wiki_dir"
    target.mkdir()
    _seed_wiki(xu_home, "MyWiki", path=str(target))
    r = cmd_mod.cmd_register(_args(name="MyWiki", path=str(target)))
    assert r["status"] == "warning"
    assert "idempotent" in r["message"]


def test_register_path_not_found(xu_home):
    r = cmd_mod.cmd_register(_args(name="MyWiki", path="/nonexistent/path/xyz"))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "PathNotFound"


def test_register_already_wiki_refuses(xu_home, tmp_path):
    target = tmp_path / "wiki_dir"
    target.mkdir()
    (target / ".xu").mkdir()
    (target / ".xu" / "config.yaml").write_text("version: 1\n")
    (target / ".xu" / "wiki.db").touch()
    r = cmd_mod.cmd_register(_args(name="MyWiki", path=str(target)))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "AlreadyWiki"


def test_register_alias_conflict_warns(xu_home, tmp_path):
    t1 = tmp_path / "w1"
    t1.mkdir()
    t2 = tmp_path / "w2"
    t2.mkdir()
    _seed_wiki(xu_home, "First", path=str(t1), alias="Shared")
    r = cmd_mod.cmd_register(_args(name="Second", path=str(t2), alias="Shared"))
    assert r["status"] == "warning"
    assert r["data"]["alias"] is None


def test_unregister_happy(xu_home):
    _seed_wiki(xu_home, "A", alias="X", path="/tmp/a")
    r = cmd_mod.cmd_unregister(_args(name="A"))
    assert r["status"] == "success"
    assert r["data"]["name"] == "A"
    assert r["data"]["removed_path"] == "/tmp/a"
    # registry no longer has A
    assert "A" not in cfg_mod.load_registry()["wikis"]


def test_unregister_by_alias(xu_home):
    _seed_wiki(xu_home, "A", alias="X")
    r = cmd_mod.cmd_unregister(_args(name="X"))
    assert r["status"] == "success"
    assert r["data"]["name"] == "A"


def test_unregister_not_found(xu_home):
    r = cmd_mod.cmd_unregister(_args(name="ghost"))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "NameNotFound"


def test_config_set_mineru_key_missing_env(xu_home, monkeypatch):
    monkeypatch.delenv("MINERU_API_KEY", raising=False)
    r = cmd_mod.cmd_config_set_mineru_key(_args())
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "MissingKey"


def test_config_set_mineru_key_happy(xu_home, monkeypatch):
    monkeypatch.setenv("MINERU_API_KEY", "secret-token-1234567890abcdef")
    r = cmd_mod.cmd_config_set_mineru_key(_args())
    assert r["status"] == "success"
    assert r["data"]["scope"] == "global"
    saved = cfg_mod.load_global_config()
    assert saved["mineru"]["api_key"] == "secret-token-1234567890abcdef"
    show = cmd_mod.cmd_config_show(_args())
    # full secret must never appear in masked output
    assert "secret-token-1234567890abcdef" not in str(show)
    assert show["data"]["mineru"]["api_key_set"] is True


def test_config_show_masks_short_key(xu_home, monkeypatch):
    monkeypatch.setenv("MINERU_API_KEY", "abc")
    cmd_mod.cmd_config_set_mineru_key(_args())
    show = cmd_mod.cmd_config_show(_args())
    assert show["data"]["mineru"]["api_key_masked"] == "***"


def test_config_path(xu_home):
    r = cmd_mod.cmd_config_path(_args())
    assert r["status"] == "success"
    assert r["data"]["global_dir"] == str(xu_home)


def test_cli_dispatch_routes_new_commands():
    """Smoke: cli.build_parser accepts every new subcommand form."""
    from xu.cli import build_parser

    p = build_parser()
    forms = [
        ["alias", "set", "--wiki", "A", "--alias", "B"],
        ["alias", "unset", "--wiki", "A"],
        ["alias", "show", "--wiki", "A"],
        ["register", "--name", "A", "--path", "/tmp/x"],
        ["unregister", "--name", "A"],
        ["config", "set-mineru-key"],
        ["config", "show"],
        ["config", "path"],
    ]
    for argv in forms:
        args = p.parse_args(argv)
        assert args.func.startswith(("alias_", "register", "unregister", "config_"))

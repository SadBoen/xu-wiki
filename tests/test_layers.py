"""Unit tests for L2 List and L3 Report layer commands."""
import os
import sys
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.utils import config as cfg_mod
from xu.commands import create as create_mod
from xu.commands.layers import _list_create, _list_show
from xu.utils.frontmatter import render as fm_render, parse as fm_parse
from xu.utils.wiki import resolve_wiki
from xu.utils.paths import now_ts


@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    """Point global config dir at tmp_path."""
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    return tmp_path


@pytest.fixture
def wiki(xu_home):
    """Create a fresh empty wiki and return its name + root path."""
    name = "list-test-wiki"
    root = xu_home / "wikis" / name
    r = create_mod.cmd_create(SimpleNamespace(
        name=name, path=str(root), alias=None,
    ))
    assert r["status"] == "success", r
    return name, root


def _args(**kw) -> SimpleNamespace:
    return SimpleNamespace(**kw)


def _write_page(ctx, uid, title, layer="Page"):
    """Write a minimal page node file and return (frontmatter, body)."""
    page_dir = ctx.page_dir
    page_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = {"uid": uid, "title": title, "layer": layer, "created_at": "1", "updated_at": "1"}
    body = f"Body of {title}"
    path = page_dir / f"{uid}.md"
    path.write_text(fm_render(frontmatter, body), encoding="utf-8")
    return frontmatter, body


# ---------------------------------------------------------------------------
# List create
# ---------------------------------------------------------------------------

def test_list_create_body_is_yaml_list(wiki):
    """List body must be a YAML list of dicts, not markdown table."""
    name, root = wiki
    ctx = resolve_wiki(name)

    _write_page(ctx, "PAGE0001", "Test Page 1")
    _write_page(ctx, "PAGE0002", "Test Page 2")

    r = _list_create(_args(
        wiki=name, title="My List", dimension="by-type",
        members="PAGE0001,PAGE0002",
    ))
    assert r["status"] == "success", r
    list_uid = r["data"]["uid"]
    node_path = "my-list"

    text = (ctx.list_dir / f"{node_path}.md").read_text()
    _, body = fm_parse(text)
    body = body.strip()
    assert body.startswith("- "), f"body should be YAML list, got: {body[:60]}"
    items = yaml.safe_load(body)
    assert isinstance(items, list)
    assert len(items) == 2
    assert items[0]["uid"] == "PAGE0001"
    assert items[0]["title"] == "Test Page 1"
    assert items[0]["layer"] == "Page"
    assert items[0]["note"] == ""
    assert items[1]["uid"] == "PAGE0002"


def test_list_create_frontmatter_has_no_members_array(wiki):
    """frontmatter must not contain a members[] array."""
    name, root = wiki
    ctx = resolve_wiki(name)

    _write_page(ctx, "PAGE0001", "Page 1")
    r = _list_create(_args(wiki=name, title="List No Members",
                            dimension="by-type", members="PAGE0001"))
    assert r["status"] == "success"
    list_uid = r["data"]["uid"]
    node_path = "list-no-members"

    text = (ctx.list_dir / f"{node_path}.md").read_text()
    frontmatter, _ = fm_parse(text)
    assert "members" not in frontmatter
    assert frontmatter["uid"] == list_uid
    assert frontmatter["title"] == "List No Members"
    assert frontmatter["dimension"] == "by-type"
    assert frontmatter["layer"] == "List"
    assert frontmatter["split_index"] == 1
    assert frontmatter["parent_uid"] == list_uid

# ---------------------------------------------------------------------------
# List show
# ---------------------------------------------------------------------------

def test_list_show_returns_members_from_body_yaml(wiki):
    """list show must read members from YAML body, not frontmatter members array."""
    name, root = wiki
    ctx = resolve_wiki(name)

    # Manually create a list file with YAML body
    uid = "LISTEST1"
    ctx.list_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "uid": uid, "title": "Test List", "layer": "List",
        "dimension": "by-type", "created_at": "1", "updated_at": "1",
    }
    body = yaml.dump([
        {"uid": "PAGE0001", "title": "Page 1", "layer": "Page", "note": ""},
        {"uid": "PAGE0002", "title": "Page 2", "layer": "Page", "note": "important"},
    ])
    path = ctx.list_dir / f"{uid}.md"
    path.write_text(fm_render(frontmatter, body), encoding="utf-8")

    r = _list_show(_args(wiki=name, uid=uid))
    assert r["status"] == "success"
    assert r["data"]["member_count"] == 2
    assert [m["uid"] for m in r["data"]["members"]] == ["PAGE0001", "PAGE0002"]
    assert [m["note"] for m in r["data"]["members"]] == ["", "important"]
    assert r["data"]["dimension"] == "by-type"


def test_list_show_dimension_from_frontmatter(wiki):
    """dimension field comes from frontmatter, not body."""
    name, root = wiki
    ctx = resolve_wiki(name)

    uid = "LISTDIMEN1"
    ctx.list_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "uid": uid, "title": "Dim List", "layer": "List",
        "dimension": "by-owner", "created_at": "1", "updated_at": "1",
    }
    body = yaml.dump([{"uid": "PAGE0001", "title": "Page 1", "layer": "Page", "note": ""}])
    (ctx.list_dir / f"{uid}.md").write_text(fm_render(frontmatter, body), encoding="utf-8")

    r = _list_show(_args(wiki=name, uid=uid))
    assert r["data"]["dimension"] == "by-owner"

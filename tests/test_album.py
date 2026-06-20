"""Unit tests for the album CLI (M7: ingest-album sub-flow of SOP-ingest).

Covers PRIN-ING-13 (body-form) and PRIN-ING-14 (single-shot). The album CLI
takes N images → 1 L1 Page with table or list body, copying each source
file to raws/, hashing for dedup, and rendering metadata from Pillow
when available (graceful degradation when Pillow is missing).
"""
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.commands import album as album_mod
from xu.commands import create as create_mod
from xu.utils import config as cfg_mod
from xu.utils import frontmatter as fm
from xu.utils.wiki import resolve_wiki


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    """Point global config dir at tmp_path."""
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    return tmp_path


@pytest.fixture
def wiki(xu_home):
    """Create a fresh empty wiki and return its name + root path."""
    name = "album-test-wiki"
    root = xu_home / "wikis" / name
    r = create_mod.cmd_create(SimpleNamespace(
        name=name, path=str(root), alias=None,
    ))
    assert r["status"] == "success", r
    return name, root


def _write_fake_jpeg(path: Path, *, body: bytes = b"\xff\xd8\xff\xe0fake-jpeg") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _args(**kw) -> SimpleNamespace:
    return SimpleNamespace(**kw)


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------

def test_album_happy_table(wiki, tmp_path):
    name, root = wiki
    files = []
    for n in ("001.jpeg", "002.jpeg", "003.jpeg"):
        p = tmp_path / "photos" / n
        _write_fake_jpeg(p, body=f"image-{n}".encode())
        files.append(str(p))

    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="SGW001 第一次岸上系统部署完工",
        files=",".join(files), node_path="船舶/SGW001/照片",
        layout="table", vision=False, captions="",
        digest="D-album-happy", author="tester",
    ))
    assert r["status"] == "success", r
    data = r["data"]
    assert data["layout"] == "table"
    assert data["count"] == 3
    # 3 source files copied into raws/
    raws_dir = root / "raws" / "船舶" / "SGW001" / "照片"
    assert raws_dir.is_dir()
    assert sorted(p.name for p in raws_dir.iterdir()) == ["001.jpeg", "002.jpeg", "003.jpeg"]
    # 1 L1 page written
    md = root / data["md_path"]
    assert md.is_file()
    front, body = fm.parse(md.read_text(encoding="utf-8"))
    assert front["title"] == "SGW001 第一次岸上系统部署完工"
    assert front["layer"] == "Page"
    assert front["template"] == "gallery"
    assert front["digest"] == "D-album-happy"
    assert front["source_hash"]  # first source's hash recorded on the L1
    # body has 7-column table header
    assert "| # | Filename | Path | Resolution | GPS | Captured | Description |" in body
    assert "| 1 | 001.jpeg |" in body
    assert "| 2 | 002.jpeg |" in body
    assert "| 3 | 003.jpeg |" in body
    # xu-album marker
    assert "<!-- xu-album layout=table count=3 vision=no -->" in body

    # attrs.album.sources stored: verify via SQL (raw JSON column)
    ctx = resolve_wiki(name)
    conn = ctx.connect()
    row = conn.execute(
        "SELECT attrs FROM nodes WHERE uid=?", (data["uid"],),
    ).fetchone()
    conn.close()
    assert row is not None
    attrs_obj = json.loads(row["attrs"])
    assert attrs_obj["album"]["layout"] == "table"
    assert attrs_obj["album"]["count"] == 3
    assert attrs_obj["album"]["vision"] is False
    assert len(attrs_obj["album"]["sources"]) == 3
    assert attrs_obj["album"]["sources"][0]["filename"] == "001.jpeg"
    assert attrs_obj["album"]["sources"][0]["source_hash"]  # sha256 present


def test_album_happy_list(wiki, tmp_path):
    name, root = wiki
    files = []
    for n in ("a.png", "b.png"):
        p = tmp_path / "pics" / n
        _write_fake_jpeg(p, body=f"img-{n}".encode())
        files.append(str(p))

    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="List layout album",
        files=",".join(files), node_path="",
        layout="list", vision=False, captions="",
        digest="D-album-list", author="tester",
    ))
    assert r["status"] == "success", r
    md = root / r["data"]["md_path"]
    body = fm.parse(md.read_text(encoding="utf-8"))[1]
    # list layout: no pipe table header, has **filename** bold entries
    assert "| # | Filename" not in body
    assert "- **a.png**" in body
    assert "- **b.png**" in body
    assert "<!-- xu-album layout=list count=2 vision=no -->" in body


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def test_album_missing_wiki(xu_home, tmp_path):
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r = album_mod.cmd_ingest_album(_args(
        wiki="no-such-wiki", title="t", files=str(p), node_path="",
        layout="table", vision=False, captions="",
        digest="", author="tester",
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "WikiNotFound"


def test_album_missing_title(wiki, tmp_path):
    name, _ = wiki
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="", files=str(p), node_path="",
        layout="table", vision=False, captions="",
        digest="", author="tester",
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "MissingTitle"
    assert "title" in r["data"].get("missing", [])


def test_album_missing_files(wiki):
    name, _ = wiki
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="t", files="", node_path="",
        layout="table", vision=False, captions="",
        digest="", author="tester",
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "MissingFiles"


def test_album_relative_path(wiki, tmp_path):
    name, _ = wiki
    rel = tmp_path / "x.jpeg"
    _write_fake_jpeg(rel)
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="t", files=f"./{rel.name}", node_path="",
        layout="table", vision=False, captions="",
        digest="", author="tester",
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "PathNotAbsolute"


def test_album_invalid_layout(wiki, tmp_path):
    name, _ = wiki
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="t", files=str(p), node_path="",
        layout="yaml", vision=False, captions="",
        digest="", author="tester",
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "InvalidLayout"


def test_album_file_not_found(wiki, tmp_path):
    name, _ = wiki
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="t",
        files=str(tmp_path / "missing.jpeg"),
        node_path="", layout="table", vision=False, captions="",
        digest="", author="tester",
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "FileNotFound"


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------

def test_album_source_collision_rejected(wiki, tmp_path):
    """If a source file's hash is already in the DB, the whole album rejects."""
    name, root = wiki

    # First commit a single Page with a known source_hash by running
    # ingest-album on a 1-photo album.
    p1 = tmp_path / "first.jpeg"
    _write_fake_jpeg(p1, body=b"uniquely-stable-bytes-for-collision-test")
    r1 = album_mod.cmd_ingest_album(_args(
        wiki=name, title="first album", files=str(p1),
        node_path="", layout="table", vision=False, captions="",
        digest="D1", author="tester",
    ))
    assert r1["status"] == "success", r1
    first_hash = r1["data"]["sources"][0]["source_hash"]

    # Second album: include the SAME physical file (will hash the same).
    p2 = tmp_path / "second.jpeg"
    _write_fake_jpeg(p2, body=b"different-content-not-colliding")
    r2 = album_mod.cmd_ingest_album(_args(
        wiki=name, title="second album collision",
        files=f"{p1},{p2}", node_path="",
        layout="table", vision=False, captions="",
        digest="D2", author="tester",
    ))
    assert r2["status"] == "warning", r2
    assert r2["data"]["checked"] == 2
    assert any(
        c["source_hash"] == first_hash and c["filename"] == "first.jpeg"
        for c in r2["data"]["collisions"]
    )


# ---------------------------------------------------------------------------
# captions + vision
# ---------------------------------------------------------------------------

def test_album_captions_inline_json(wiki, tmp_path):
    name, root = wiki
    files = []
    for n in ("c1.jpeg", "c2.jpeg"):
        p = tmp_path / n
        _write_fake_jpeg(p, body=f"img-{n}".encode())
        files.append(str(p))
    captions = json.dumps({"c1.jpeg": "船头整体完工", "c2.jpeg": "侧视图"})

    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="captions test", files=",".join(files),
        node_path="", layout="table", vision=False,
        captions=captions, digest="D-cap", author="tester",
    ))
    assert r["status"] == "success", r
    md = root / r["data"]["md_path"]
    body = fm.parse(md.read_text(encoding="utf-8"))[1]
    assert "船头整体完工" in body
    assert "侧视图" in body


def test_album_captions_bad_json(wiki, tmp_path):
    name, _ = wiki
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="t", files=str(p), node_path="",
        layout="table", vision=False, captions="{not-json",
        digest="", author="tester",
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "BadCaptionsJSON"


def test_album_vision_flag_recorded(wiki, tmp_path):
    """--vision must produce marker 'vision=yes' and a hint about backend."""
    name, root = wiki
    p = tmp_path / "v.jpeg"
    _write_fake_jpeg(p)
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="vision test", files=str(p), node_path="",
        layout="table", vision=True, captions="",
        digest="D-vision", author="tester",
    ))
    assert r["status"] == "success", r
    md = root / r["data"]["md_path"]
    body = fm.parse(md.read_text(encoding="utf-8"))[1]
    assert "<!-- xu-album layout=table count=1 vision=yes -->" in body
    assert "vision 意图已标记" in body
    # hint surfaces the deferred-caption expectation
    assert any("vision" in h for h in r["hints"])


# ---------------------------------------------------------------------------
# Pillow graceful degradation
# ---------------------------------------------------------------------------

def test_album_runs_without_pillow(wiki, tmp_path, monkeypatch):
    """Force image_meta._PILLOW_OK = False; album must still commit with '—'."""
    from xu.parsers import image_meta

    name, root = wiki
    p = tmp_path / "n.jpeg"
    _write_fake_jpeg(p, body=b"some-bytes")

    monkeypatch.setattr(image_meta, "_PILLOW_OK", False)
    # also reload the image_meta module attribute inside the album module
    # (the album module imported read_image_meta by reference, so monkeypatching
    # the module attr is enough)
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="no pillow test", files=str(p), node_path="",
        layout="table", vision=False, captions="",
        digest="D-np", author="tester",
    ))
    assert r["status"] == "success", r
    src = r["data"]["sources"][0]
    assert src["width"] is None
    assert src["height"] is None
    assert src["gps"] is None
    assert src["captured"] is None
    md = root / r["data"]["md_path"]
    body = fm.parse(md.read_text(encoding="utf-8"))[1]
    # resolution cell falls back to "—"
    assert "| — |" in body
    monkeypatch.undo()


# ---------------------------------------------------------------------------
# sources copied to raws/ (PRIN-ING-6)
# ---------------------------------------------------------------------------

def test_album_sources_copied_to_raws(wiki, tmp_path):
    name, root = wiki
    p1 = tmp_path / "raw1.jpeg"
    p2 = tmp_path / "raw2.jpeg"
    _write_fake_jpeg(p1, body=b"raw-bytes-1")
    _write_fake_jpeg(p2, body=b"raw-bytes-2")
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="raws copy test",
        files=f"{p1},{p2}", node_path="嵌套/路径/段",
        layout="table", vision=False, captions="",
        digest="D-raws", author="tester",
    ))
    assert r["status"] == "success", r
    raws_root = root / "raws" / "嵌套" / "路径" / "段"
    assert raws_root.is_dir()
    files = sorted(p.name for p in raws_root.iterdir())
    assert files == ["raw1.jpeg", "raw2.jpeg"]


# ---------------------------------------------------------------------------
# resolve_wiki round-trip
# ---------------------------------------------------------------------------

def test_resolve_wiki_after_album_creation(wiki, tmp_path):
    name, _ = wiki
    ctx = resolve_wiki(name)
    assert ctx is not None
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r = album_mod.cmd_ingest_album(_args(
        wiki=name, title="resolve test", files=str(p), node_path="",
        layout="table", vision=False, captions="",
        digest="D-res", author="tester",
    ))
    assert r["status"] == "success", r
    # Re-resolve and confirm the L1 is queryable via raw SQL
    conn = ctx.connect()
    row = conn.execute(
        "SELECT uid, title, layer, template FROM nodes WHERE title=?",
        ("resolve test",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["title"] == "resolve test"
    assert row["layer"] == "Page"
    assert row["template"] == "gallery"

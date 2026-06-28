"""Unit tests for gallery/album ingestion via the two-phase ingest flow.

Covers PRIN-ING-13 (body-form), PRIN-ING-14 (merged into two-phase),
PRIN-ING-3a (SHA256 three-way). The gallery flow goes:
  Phase 1: ingest-file --files img1,img2,... --title T --node-path P
  Phase 2: ingest-commit --temp <path> --title T --content-type gallery

Tests: Phase 1, Phase 2, dedup, captions, vision, Pillow degradation,
raws/ copy, and integration (resolve_wiki round-trip).
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.commands import ingest as ingest_mod
from xu.commands import create as create_mod
from xu.utils import config as cfg_mod
from xu.utils import frontmatter as fm
from xu.utils.wiki import resolve_wiki


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    return tmp_path


@pytest.fixture
def wiki(xu_home):
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
# helpers
# ---------------------------------------------------------------------------

def _phase1(wiki_name, title, files, node_path="", layout="table",
            vision=False, captions="", author="agent"):
    """Run Phase 1: ingest-file with --files (gallery mode)."""
    r1 = ingest_mod.cmd_ingest_file(_args(
        wiki=wiki_name, title=title, files=files,
        node_path=node_path, layout=layout, vision=vision,
        captions=captions, author=author,
        file=None,
    ))
    return r1


def _phase2(wiki_name, temp, title, content_type="gallery", author="agent"):
    """Run Phase 2: ingest-commit with temp file."""
    r2 = ingest_mod.cmd_ingest_commit(_args(
        wiki=wiki_name, temp=temp, title=title,
        content_type=content_type, author=author,
        native=None, source=None, node_path="", relations="",
    ))
    return r2


def _two_phase(wiki_name, title, files, node_path="", layout="table",
                vision=False, captions="", author="agent"):
    """Full two-phase album commit."""
    r1 = _phase1(wiki_name, title, files, node_path, layout, vision, captions, author)
    if r1["status"] != "success":
        return r1
    temp = r1["data"]["temp"]
    r2 = _phase2(wiki_name, temp, title, "gallery", author)
    return r2


# ---------------------------------------------------------------------------
# happy path: table layout
# ---------------------------------------------------------------------------

def test_album_happy_table(wiki, tmp_path):
    name, root = wiki
    for n in ("001.jpeg", "002.jpeg", "003.jpeg"):
        p = tmp_path / "photos" / n
        _write_fake_jpeg(p, body=f"image-{n}".encode())
    files_str = ",".join(str(tmp_path / "photos" / n) for n in ("001.jpeg", "002.jpeg", "003.jpeg"))

    r = _two_phase(name, "SGW001 第一次岸上系统部署完工", files_str,
                   node_path="船舶/SGW001/照片", layout="table")
    assert r["status"] == "success", r
    data = r["data"]
    assert data["layout"] == "table"
    assert data["count"] == 3

    # raws/ copied
    raws_dir = root / "raws" / "船舶" / "SGW001" / "照片"
    assert raws_dir.is_dir()
    assert sorted(p.name for p in raws_dir.iterdir()) == ["001.jpeg", "002.jpeg", "003.jpeg"]

    # Page written
    md = root / data["md_path"]
    assert md.is_file()
    front, body = fm.parse(md.read_text(encoding="utf-8"))
    assert front["title"] == "SGW001 第一次岸上系统部署完工"
    assert front["layer"] == "Page"
    assert front["content_type"] == "gallery"
    assert front["source_hashes"]
    assert len(front["source_hashes"]) == 3
    assert front["attrs"]["album"]["layout"] == "table"
    assert front["attrs"]["album"]["count"] == 3
    assert front["attrs"]["album"]["vision"] is False
    assert len(front["attrs"]["album"]["sources"]) == 3

    # body is YAML list
    assert body.startswith("- filename:")
    items = yaml.safe_load(body)
    assert len(items) == 3
    assert [i["filename"] for i in items] == ["001.jpeg", "002.jpeg", "003.jpeg"]
    assert items[0]["raw_rel_path"] == "raws/船舶/SGW001/照片/001.jpeg"


def test_album_happy_list(wiki, tmp_path):
    name, _ = wiki
    for n in ("a.png", "b.png"):
        p = tmp_path / "pics" / n
        _write_fake_jpeg(p, body=f"img-{n}".encode())
    files_str = ",".join(str(tmp_path / "pics" / n) for n in ("a.png", "b.png"))

    r = _two_phase(name, "List layout album", files_str, layout="list")
    assert r["status"] == "success", r
    assert r["data"]["layout"] == "list"
    assert r["data"]["count"] == 2


# ---------------------------------------------------------------------------
# Phase 1 validation
# ---------------------------------------------------------------------------

def test_album_phase1_missing_wiki(xu_home, tmp_path):
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r = ingest_mod.cmd_ingest_file(_args(
        wiki="no-such-wiki", title="t", files=str(p),
        node_path="", layout="table", vision=False, captions="",
        author="agent", file=None,
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "WikiNotFound"


def test_album_phase1_missing_files(wiki):
    name, _ = wiki
    r = ingest_mod.cmd_ingest_file(_args(
        wiki=name, title="t", files=None,
        node_path="", layout="table", vision=False, captions="",
        author="agent", file=None,
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "FileNotFound"


def test_album_phase1_relative_path(wiki, tmp_path):
    name, _ = wiki
    rel = tmp_path / "x.jpeg"
    _write_fake_jpeg(rel)
    r = ingest_mod.cmd_ingest_file(_args(
        wiki=name, title="t",
        files=f"./{rel.name}",          # relative — must be rejected
        node_path="", layout="table", vision=False, captions="",
        author="agent", file=None,
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "PathNotAbsolute"


def test_album_phase1_file_not_found(wiki, tmp_path):
    name, _ = wiki
    r = ingest_mod.cmd_ingest_file(_args(
        wiki=name, title="t",
        files=str(tmp_path / "missing.jpeg"),
        node_path="", layout="table", vision=False, captions="",
        author="agent", file=None,
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "FileNotFound"


def test_album_phase1_invalid_layout(wiki, tmp_path):
    name, _ = wiki
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r = ingest_mod.cmd_ingest_file(_args(
        wiki=name, title="t", files=str(p),
        node_path="", layout="yaml", vision=False, captions="",
        author="agent", file=None,
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "InvalidLayout"


# ---------------------------------------------------------------------------
# Phase 2 validation
# ---------------------------------------------------------------------------

def test_album_phase2_temp_not_found(wiki, tmp_path):
    name, _ = wiki
    r = ingest_mod.cmd_ingest_commit(_args(
        wiki=name, temp=str(tmp_path / "nonexistent.pending"),
        title="t", content_type="gallery", author="agent",
        native=None, source=None, node_path="", relations="",
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "TempNotFound"


def test_album_phase2_invalid_content_type(wiki, tmp_path):
    name, _ = wiki
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r1 = _phase1(name, "t", str(p))
    assert r1["status"] == "success"
    r2 = ingest_mod.cmd_ingest_commit(_args(
        wiki=name, temp=r1["data"]["temp"],
        title="t", content_type="invalid_type", author="agent",
        native=None, source=None, node_path="", relations="",
    ))
    assert r2["status"] == "error"
    assert r2["data"]["error_class"] == "InvalidContentType"


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------

def test_album_source_collision_skipped(wiki, tmp_path):
    """If a source file's hash already exists, Phase 1 skips it (no I/O waste)."""
    name, root = wiki
    p1 = tmp_path / "first.jpeg"
    _write_fake_jpeg(p1, body=b"uniquely-stable-bytes-for-collision-test")

    # First album: 1 photo
    r1 = _two_phase(name, "first album", str(p1))
    assert r1["status"] == "success", r1
    first_hash = r1["data"]["sources"][0]["source_hash"]

    # Second: same photo (duplicate) + new photo
    p2 = tmp_path / "second.jpeg"
    _write_fake_jpeg(p2, body=b"different-content-not-colliding")

    # Phase 1 catches duplicate
    r1b = _phase1(name, "second album", f"{p1},{p2}")
    assert r1b["status"] == "success", r1b
    assert r1b["data"]["images"] == 1               # only p2 is new
    assert len(r1b["data"]["skipped"]) == 1        # p1 is duplicate
    assert r1b["data"]["skipped"][0]["source_hash"] == first_hash
    assert r1b["data"]["skipped"][0]["filename"] == "first.jpeg"

    # Phase 2 sees only new image → no further dedup needed
    r2 = _phase2(name, r1b["data"]["temp"], "second album", "gallery")
    assert r2["status"] == "success", r2
    assert r2["data"]["count"] == 1
    assert len(r2["data"]["skipped"]) == 0          # Phase 1 already deduped


# ---------------------------------------------------------------------------
# captions + vision
# ---------------------------------------------------------------------------

def test_album_captions_inline_json(wiki, tmp_path):
    name, root = wiki
    for n in ("c1.jpeg", "c2.jpeg"):
        p = tmp_path / n
        _write_fake_jpeg(p, body=f"img-{n}".encode())
    files_str = ",".join(str(tmp_path / n) for n in ("c1.jpeg", "c2.jpeg"))
    captions = json.dumps({"c1.jpeg": "船头整体完工", "c2.jpeg": "侧视图"})

    r = _two_phase(name, "captions test", files_str, captions=captions)
    assert r["status"] == "success", r
    md_path = root / r["data"]["md_path"]
    _, body_text = fm.parse(md_path.read_text(encoding="utf-8"))
    assert "船头整体完工" in body_text
    assert "侧视图" in body_text


def test_album_captions_bad_json(wiki, tmp_path):
    name, _ = wiki
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)
    r = ingest_mod.cmd_ingest_file(_args(
        wiki=name, title="t", files=str(p),
        node_path="", layout="table", vision=False,
        captions="{not-json",
        author="agent", file=None,
    ))
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "BadCaptionsJSON"


def test_album_vision_flag_recorded(wiki, tmp_path):
    """--vision intent is stored in attrs.album.vision."""
    name, root = wiki
    p = tmp_path / "v.jpeg"
    _write_fake_jpeg(p)

    r = _two_phase(name, "vision test", str(p), vision=True)
    assert r["status"] == "success", r

    # Read back and check attrs.album.vision
    uid = r["data"]["uid"]
    ctx = resolve_wiki(name)
    for md_path in ctx.page_dir.rglob("*.md"):
        fd, _ = fm.parse(md_path.read_text(encoding="utf-8"))
        if fd.get("uid") == uid:
            attrs_obj = fd.get("attrs", {})
            assert attrs_obj["album"]["vision"] is True
            break
    else:
        pytest.fail(f"uid {uid} not found")

    assert any("vision" in h for h in r["hints"])


# ---------------------------------------------------------------------------
# Pillow graceful degradation
# ---------------------------------------------------------------------------

def test_album_runs_without_pillow(wiki, tmp_path, monkeypatch):
    """Force image_meta._PILLOW_OK = False; album still commits with null meta."""
    from xu.parsers import image_meta

    name, _ = wiki
    p = tmp_path / "n.jpeg"
    _write_fake_jpeg(p, body=b"some-bytes")

    monkeypatch.setattr(image_meta, "_PILLOW_OK", False)
    r = _two_phase(name, "no pillow test", str(p))
    assert r["status"] == "success", r
    src = r["data"]["sources"][0]
    assert src["width"] is None
    assert src["height"] is None
    assert src["gps"] is None
    assert src["captured"] is None
    monkeypatch.undo()


# ---------------------------------------------------------------------------
# raws/ copy (PRIN-ING-6)
# ---------------------------------------------------------------------------

def test_album_sources_copied_to_raws(wiki, tmp_path):
    """All source images are copied to raws/<node-path>/ before Phase 2."""
    name, root = wiki
    p1 = tmp_path / "raw1.jpeg"
    p2 = tmp_path / "raw2.jpeg"
    _write_fake_jpeg(p1, body=b"raw-bytes-1")
    _write_fake_jpeg(p2, body=b"raw-bytes-2")
    files_str = f"{p1},{p2}"

    # Phase 1 alone must copy to raws/
    r1 = _phase1(name, "raws copy test", files_str,
                  node_path="嵌套/路径/段")
    assert r1["status"] == "success", r1

    raws_root = root / "raws" / "嵌套" / "路径" / "段"
    assert raws_root.is_dir()
    assert sorted(p.name for p in raws_root.iterdir()) == ["raw1.jpeg", "raw2.jpeg"]


# ---------------------------------------------------------------------------
# resolve_wiki round-trip
# ---------------------------------------------------------------------------

def test_resolve_wiki_after_album_creation(wiki, tmp_path):
    """Created Page is queryable via resolve_wiki after commit."""
    name, root = wiki
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)

    r = _two_phase(name, "resolve test", str(p))
    assert r["status"] == "success", r

    uid = r["data"]["uid"]
    ctx = resolve_wiki(name)
    assert ctx is not None
    found = None
    for md_path in ctx.page_dir.rglob("*.md"):
        fd, _ = fm.parse(md_path.read_text(encoding="utf-8"))
        if fd.get("uid") == uid:
            found = fd
            break
    assert found is not None
    assert found["title"] == "resolve test"
    assert found["layer"] == "Page"
    assert found["content_type"] == "gallery"


# ---------------------------------------------------------------------------
# temp file deleted after success (PRIN-ING-7)
# ---------------------------------------------------------------------------

def test_album_temp_deleted_after_commit(wiki, tmp_path):
    """Temp file is deleted after Phase 2 success."""
    name, _ = wiki
    p = tmp_path / "x.jpeg"
    _write_fake_jpeg(p)

    r1 = _phase1(name, "temp delete test", str(p))
    assert r1["status"] == "success", r1
    temp_path = Path(r1["data"]["temp"])
    assert temp_path.exists(), "Phase 1 temp file should exist before Phase 2"

    r2 = _phase2(name, str(temp_path), "temp delete test")
    assert r2["status"] == "success", r2
    assert not temp_path.exists(), "Temp file should be deleted after Phase 2 success"


# ---------------------------------------------------------------------------
# article large-body ingest-verify (≥1.7 KB body triggers OSError before fix)
# ---------------------------------------------------------------------------

def _phase1_article(wiki_name, title, file_path, node_path=""):
    """Run Phase 1: ingest-file with --file (article mode)."""
    r = ingest_mod.cmd_ingest_file(_args(
        wiki=wiki_name, title=title, file=file_path,
        node_path=node_path, files=None,
    ))
    return r


def _phase2_article(wiki_name, temp, title, content_type="article"):
    """Run Phase 2: ingest-commit with temp file (article mode)."""
    r = ingest_mod.cmd_ingest_commit(_args(
        wiki=wiki_name, temp=temp, title=title,
        content_type=content_type, author="agent",
        native=None, source=None, node_path="", relations="",
    ))
    return r


def test_ingest_verify_large_body_no_oserror(wiki, tmp_path):
    """ingest-verify must not raise OSError on body ≥1.7 KB (split pages).

    Regression test for: _raw_path_checks passed body string to os.stat()
    instead of frontmatter['raw_path'] — fixed with isinstance guard + OSError
    handling.  The bug triggered on every verify call because split pages carry
    large bodies in frontmatter, and Linux filename length is unbounded so the
    OSError only appeared on specific FS/path conditions; the real fix is the
    type-safe rewrite that never passes body to file operations.
    """
    name, _root = wiki

    # Generate a file large enough to create ≥2 split pages (1000 lines × 100
    # chars ≈ 100 KB, well above the 300-line split threshold).
    large_file = tmp_path / "large_doc.txt"
    large_file.write_text("\n".join(f"line {i:04d} " + "x" * 90 for i in range(1000)),
                          encoding="utf-8")
    assert large_file.stat().st_size > 90_000, "sanity: file must be ≥90 KB"

    r1 = _phase1_article(name, "large body test", str(large_file))
    assert r1["status"] == "success", r1
    temp_path = Path(r1["data"]["temp"])
    assert temp_path.exists()

    r2 = _phase2_article(name, str(temp_path), "large body test")
    assert r2["status"] == "success", r2

    created = r2["data"]["created"]
    assert len(created) >= 2, f"expected ≥2 split pages, got {len(created)}"

    # Verify every created UID — none should raise OSError
    for item in created:
        uid = item["uid"]
        vr = ingest_mod.cmd_ingest_verify(_args(wiki=name, uid=uid))
        assert vr["status"] == "success", f"verify failed for uid={uid}: {vr}"
        assert not any(
            "OSError" in str(c) for c in vr.get("data", {}).get("checks", [])
        ), f"OSError found in verify checks for uid={uid}"

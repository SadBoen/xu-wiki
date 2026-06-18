"""Unit tests for deterministic core logic (CLI determinism, PRIN-QRY-3)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.ingest.splitter import split_pages, extract_nouns  # noqa: E402
from xu.query.slicing import make_slice, merge_slices  # noqa: E402
from xu.utils import frontmatter as fm  # noqa: E402
from xu.utils.paths import gen_uid, is_valid_uid, sha256_text  # noqa: E402
from xu.utils import db  # noqa: E402
from xu.ingest.relations_lru import add_relation, list_relations, touch_relation  # noqa: E402


def test_uid_format():
    uid = gen_uid(2026)
    assert is_valid_uid(uid)
    assert uid.startswith("2026-")
    assert len({gen_uid() for _ in range(1000)}) == 1000  # uniqueness


def test_split_remainder_rule():
    text = "\n".join(f"line {i}" for i in range(720))
    pages = split_pages(text, max_lines=300)
    assert len(pages) == 3
    assert len(pages[2].splitlines()) == 120  # trailing remainder is its own page


def test_split_small_single_page():
    assert len(split_pages("a\nb\nc", max_lines=300)) == 1


def test_frontmatter_roundtrip():
    fmd = {"uid": "2026-ABCD1234", "active": True, "layer": "Page"}
    doc = fm.render(fmd, "hello body")
    parsed, body = fm.parse(doc)
    assert parsed["uid"] == "2026-ABCD1234"
    assert parsed["active"] is True
    assert "hello body" in body


def test_sha256_dedup_stable():
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abd")


def test_slice_respects_hard_limit():
    text = "x" * 500
    s, e, snip = make_slice(text, 250, 251, soft_limit=80, hard_limit=150)
    assert (e - s) <= 301  # both sides hard-bounded


def test_merge_adjacent_slices():
    slices = [
        {"start": 0, "end": 50, "text": "a", "hits": {"k1"}, "line": 1},
        {"start": 60, "end": 100, "text": "b", "hits": {"k2"}, "line": 2},
        {"start": 500, "end": 540, "text": "c", "hits": {"k1"}, "line": 9},
    ]
    merged = merge_slices(slices, radius=80)
    assert len(merged) == 2
    assert merged[0]["hits"] == {"k1", "k2"}


def test_extract_nouns_nonempty():
    nouns = extract_nouns("convolutional neural network architecture design")
    assert len(nouns) >= 1


def _mkdb():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db.init_schema(tmp.name)
    conn = db.connect(tmp.name)
    for i in range(60):
        conn.execute(
            "INSERT INTO nodes(uid,layer,template,title,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (f"2026-N{i:07d}", "Page", "article", f"n{i}", 0, 0),
        )
    conn.commit()
    return conn


def test_lru_cap_50_and_eviction():
    conn = _mkdb()
    src = "2026-N0000000"
    for i in range(1, 56):
        add_relation(conn, src, f"2026-N{i:07d}", "related")
    conn.commit()
    rels = list_relations(conn, src)
    assert len(rels) == 50  # cap enforced (PRIN-ARCH-7)
    # most recent insert is at head
    assert rels[0]["to_uid"] == "2026-N0000055"
    positions = [r["position"] for r in rels]
    assert positions == list(range(50))  # contiguous renumber


def test_lru_touch_moves_forward():
    conn = _mkdb()
    src = "2026-N0000000"
    for i in range(1, 6):
        add_relation(conn, src, f"2026-N{i:07d}", "related")
    conn.commit()
    rels = list_relations(conn, src)
    tail_uid = rels[-1]["to_uid"]
    touch_relation(conn, src, tail_uid)
    conn.commit()
    rels2 = list_relations(conn, src)
    new_pos = next(r["position"] for r in rels2 if r["to_uid"] == tail_uid)
    assert new_pos == len(rels2) - 2  # moved forward by one


if __name__ == "__main__":
    import traceback
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for f in funcs:
        try:
            f()
            print(f"PASS {f.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {f.__name__}")
            traceback.print_exc()
    print(f"\n{len(funcs)-failed}/{len(funcs)} passed")
    sys.exit(1 if failed else 0)

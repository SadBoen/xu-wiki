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
from xu.commands.doctor import _summarize  # noqa: E402


def test_uid_format():
    uid = gen_uid()
    assert is_valid_uid(uid)
    assert len(uid) == 8
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


def test_merge_recomputes_text_from_document():
    doc = "X" * 120
    slices = [
        {"start": 0, "end": 40, "text": doc[0:40], "hits": {"k1"}, "line": 1},
        {"start": 60, "end": 110, "text": doc[60:110], "hits": {"k2"}, "line": 2},
    ]
    merged = merge_slices(slices, radius=80, text=doc)
    assert len(merged) == 1
    assert merged[0]["start"] == 0 and merged[0]["end"] == 110
    assert merged[0]["text"] == doc[0:110]  # spans the whole merged region (PRIN-QRY-9)


def test_extract_nouns_nonempty():
    nouns = extract_nouns("convolutional neural network architecture design")
    assert len(nouns) >= 1


def test_lru_cap_50_and_eviction():
    fm = {"uid": "2026-N0000000", "relations": []}
    src = "2026-N0000000"
    for i in range(1, 56):
        add_relation(fm, src, f"2026-N{i:07d}", "related")
    rels = list_relations(fm, src)
    assert len(rels) == 50  # cap enforced (PRIN-ARCH-7)
    assert rels[0]["to_uid"] == "2026-N0000055"  # most recent at head


def test_lru_touch_moves_forward():
    fm = {"uid": "2026-N0000000", "relations": []}
    src = "2026-N0000000"
    for i in range(1, 6):
        add_relation(fm, src, f"2026-N{i:07d}", "related")
    rels = list_relations(fm, src)
    tail_uid = rels[-1]["to_uid"]
    touch_relation(fm, src, tail_uid)
    rels2 = list_relations(fm, src)
    tail_entry = next(r for r in rels2 if r["to_uid"] == tail_uid)
    assert tail_entry["position"] == 3  # moved forward by one (from 4 to 3)


def test_doctor_summarize_by_layer_and_fixability():
    report = {
        "doctor-files": {"issues": [{"layer": "Page", "fixable": True}]},
        "doctor-report-evidence": {"issues": [
            {"layer": "Report", "fixable": False},
            {"layer": "Report", "fixable": False},
        ]},
        "doctor-idf": {"issues": [{"layer": "cross", "fixable": True}]},
    }
    s = _summarize(report)
    assert s["total_issues"] == 4
    assert s["by_layer"] == {"Page": 1, "List": 0, "Report": 2, "Entity": 0, "cross": 1}
    assert s["auto_fixable"] == 2
    assert s["read_only"] == 2


def test_touch_relation_no_rotation_multi_relname():
    fm = {"uid": "2026-N0000000", "relations": [
        {"to_uid": "2026-N0000001", "relation_name": "r1", "comment": "", "created_at": 0, "position": 0},
        {"to_uid": "2026-N0000001", "relation_name": "r2", "comment": "", "created_at": 0, "position": 1},
        {"to_uid": "2026-N0000001", "relation_name": "r3", "comment": "", "created_at": 0, "position": 2},
    ]}
    src = "2026-N0000000"
    touch_relation(fm, src, "2026-N0000001")
    order = [r["relation_name"] for r in list_relations(fm, src)]
    assert order == ["r1", "r2", "r3"]  # stable, not rotated (BUG-16)


def test_touch_relation_advances_one_slot():
    fm = {"uid": "2026-N0000000", "relations": [
        {"to_uid": "2026-N0000001", "relation_name": "a", "comment": "", "created_at": 0, "position": 0},
        {"to_uid": "2026-N0000002", "relation_name": "b", "comment": "", "created_at": 0, "position": 1},
        {"to_uid": "2026-N0000003", "relation_name": "c", "comment": "", "created_at": 0, "position": 2},
    ]}
    src = "2026-N0000000"
    touch_relation(fm, src, "2026-N0000003")
    order = [r["to_uid"] for r in list_relations(fm, src)]
    assert order == ["2026-N0000001", "2026-N0000003", "2026-N0000002"]  # c moved up one


def test_extract_nouns_cjk_bigram_fallback(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_jieba(name, *a, **k):
        if name.startswith("jieba"):
            raise ImportError("blocked")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_jieba)
    nouns = extract_nouns("中文搜索词")
    assert "中文" in nouns and "搜索" in nouns  # short CJK terms become findable (BUG-2)
    assert "中文搜索词" not in nouns  # whole run is no longer swallowed


def test_safe_node_path_blocks_traversal():
    from xu.utils.paths import safe_node_path
    assert safe_node_path("papers/ml") == "papers/ml"
    assert safe_node_path("/papers/ml/") == "papers/ml"
    assert safe_node_path("") == ""
    assert safe_node_path("/abs/path") == "abs/path"  # leading slash stripped, stays in-tree
    for bad in ("../etc", "a/../../b", "../../tmp/evil"):
        try:
            safe_node_path(bad)
            assert False, f"should reject {bad!r}"
        except ValueError:
            pass


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

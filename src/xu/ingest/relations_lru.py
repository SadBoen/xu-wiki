"""Relation LRU operations (PRIN-ARCH-7~10, CONST-ARCH-4).

A node's out-edges form one ordered list (max 50). Stored as a YAML list in
the node's frontmatter `relations` field:
  relations:
    - {to_uid: X, relation_name: "参访", comment: "", created_at: "..."}
    - ...

Position = list index (head = 0). No SQLite; frontmatter is the sole store.
"""
from __future__ import annotations

from ..utils.constants import FM_RELATIONS, MAX_EDGES
from ..utils.paths import now_ts


def _load_relations(fm: dict) -> list[dict]:
    raw = fm.get(FM_RELATIONS, [])
    if not isinstance(raw, list):
        return []
    return [dict(r) for r in raw]


def _save_relations(fm: dict, rels: list[dict]) -> None:
    fm[FM_RELATIONS] = rels


def add_relation(
    fm: dict,
    from_uid: str,
    to_uid: str,
    relation_name: str,
    comment: str = "",
    max_edges: int = MAX_EDGES,
) -> dict:
    """Insert/refresh a relation at the head. Returns {created|refreshed, evicted}.

    Matches OLD SQLite semantics: bulk position+1 on all existing edges,
    then place new/refreshed edge at position 0.
    """
    raw = fm.get(FM_RELATIONS, [])
    if not isinstance(raw, list):
        raw = []
        fm[FM_RELATIONS] = raw

    existing_idx = None
    for i, r in enumerate(raw):
        if r.get("to_uid") == to_uid and r.get("relation_name") == relation_name:
            existing_idx = i
            break

    ts = now_ts()
    if existing_idx is not None:
        raw.pop(existing_idx)

    new_entry = {
        "to_uid": to_uid,
        "relation_name": relation_name,
        "comment": comment,
        "created_at": ts,
        "position": 0,
    }

    for r in raw:
        r["position"] = r.get("position", 0) + 1

    raw.insert(0, new_entry)
    raw.sort(key=lambda r: r.get("position", 0))
    for i, r in enumerate(raw):
        r["position"] = i

    if len(raw) > max_edges:
        evicted = raw.pop()
        result = {"action": "refreshed" if existing_idx is not None else "created",
                  "evicted": {"to_uid": evicted["to_uid"], "relation_name": evicted["relation_name"]}}
    else:
        result = {"action": "refreshed" if existing_idx is not None else "created", "evicted": None}

    fm[FM_RELATIONS] = raw
    return result


def _renumber_rels(rels: list[dict]) -> None:
    """Reassign contiguous positions 0..N-1 matching OLD SQLite _renumber."""
    rels.sort(key=lambda r: r.get("position", 0))
    for i, r in enumerate(rels):
        r["position"] = i


def touch_relation(fm: dict, from_uid: str, to_uid: str) -> bool:
    """Query hit → advance matched relation(s) one position toward the head (sort-based).

    Uses the same sort-based advance as the original SQLite implementation.
    Modifies frontmatter in-place.
    """
    raw = fm.get(FM_RELATIONS, [])
    if not isinstance(raw, list):
        return False

    if not any(r.get("to_uid") == to_uid for r in raw):
        return False

    keyed = []
    for i, r in enumerate(raw):
        matched = r.get("to_uid") == to_uid
        pos = r.get("position", i)
        primary = pos - 1 if (matched and pos > 0) else pos
        keyed.append((primary, 0 if matched else 1, i, r))

    keyed.sort(key=lambda x: (x[0], x[1], x[2]))
    for new_pos, (_, _, _, r) in enumerate(keyed):
        r["position"] = new_pos

    raw.sort(key=lambda r: r.get("position", 0))
    for i, r in enumerate(raw):
        r["position"] = i

    return True


def list_relations(fm: dict, from_uid: str) -> list[dict]:
    """Return ordered relations list from frontmatter (position = list index)."""
    raw = fm.get(FM_RELATIONS, [])
    return [dict(r) for r in raw]

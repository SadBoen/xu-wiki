"""Relation LRU linked list operations (PRIN-ARCH-7~10, CONST-ARCH-4).

A node's out-edges form one ordered list (max 50). No category, no score.
- add = a touch → insert at head (position 0), shift others down
- query hit = move forward one position (上浮)
- full (50) + new → evict the tail (most stale)
"""
from __future__ import annotations

import sqlite3

from ..utils.constants import MAX_EDGES
from ..utils.paths import now_ts


def _renumber(conn: sqlite3.Connection, from_uid: str) -> None:
    rows = conn.execute(
        "SELECT to_uid, relation_name FROM relations WHERE from_uid=? ORDER BY position",
        (from_uid,),
    ).fetchall()
    for pos, r in enumerate(rows):
        conn.execute(
            "UPDATE relations SET position=? WHERE from_uid=? AND to_uid=? AND relation_name=?",
            (pos, from_uid, r["to_uid"], r["relation_name"]),
        )


def add_relation(
    conn: sqlite3.Connection,
    from_uid: str,
    to_uid: str,
    relation_name: str,
    comment: str = "",
    max_edges: int = MAX_EDGES,
) -> dict:
    """Insert/refresh a relation at the head. Returns {created|refreshed, evicted}.

    Caller is responsible for commit.
    """
    existing = conn.execute(
        "SELECT 1 FROM relations WHERE from_uid=? AND to_uid=? AND relation_name=?",
        (from_uid, to_uid, relation_name),
    ).fetchone()

    # shift everyone down by 1 to free position 0
    conn.execute(
        "UPDATE relations SET position = position + 1 WHERE from_uid=?", (from_uid,)
    )
    if existing:
        conn.execute(
            "UPDATE relations SET position=0, comment=? "
            "WHERE from_uid=? AND to_uid=? AND relation_name=?",
            (comment, from_uid, to_uid, relation_name),
        )
        result = {"action": "refreshed", "evicted": None}
    else:
        conn.execute(
            "INSERT INTO relations(from_uid, to_uid, relation_name, comment, position, created_at) "
            "VALUES(?,?,?,?,0,?)",
            (from_uid, to_uid, relation_name, comment, now_ts()),
        )
        result = {"action": "created", "evicted": None}

    _renumber(conn, from_uid)

    # evict tail if over the cap (BAN-ARCH-6)
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM relations WHERE from_uid=?", (from_uid,)
    ).fetchone()["c"]
    if count > max_edges:
        tail = conn.execute(
            "SELECT to_uid, relation_name FROM relations WHERE from_uid=? "
            "ORDER BY position DESC LIMIT 1",
            (from_uid,),
        ).fetchone()
        if tail:
            conn.execute(
                "DELETE FROM relations WHERE from_uid=? AND to_uid=? AND relation_name=?",
                (from_uid, tail["to_uid"], tail["relation_name"]),
            )
            result["evicted"] = {"to_uid": tail["to_uid"], "relation_name": tail["relation_name"]}
            _renumber(conn, from_uid)
    return result


def touch_relation(conn: sqlite3.Connection, from_uid: str, to_uid: str) -> bool:
    """Query hit → move the relation(s) to that target forward one position.

    A single target may carry several relation_names (each is its own edge).
    Swapping them one-by-one against live positions corrupts ordering (an
    earlier swap shifts the row a later swap then reads), which reverses the
    block. Instead we compute a stable reordering in one pass: every matched
    edge gets a sort key one slot ahead of its current position while ties are
    broken by original order, so matched edges advance without rotating.
    """
    all_rows = conn.execute(
        "SELECT to_uid, relation_name, position FROM relations WHERE from_uid=? ORDER BY position",
        (from_uid,),
    ).fetchall()
    if not any(r["to_uid"] == to_uid for r in all_rows):
        return False
    keyed = []
    moved = False
    for idx, r in enumerate(all_rows):
        matched = r["to_uid"] == to_uid
        if matched and r["position"] > 0:
            primary = r["position"] - 1
            moved = True
        else:
            primary = r["position"]
        # matched edges win ties at the same slot so they overtake an
        # unmatched predecessor; original index keeps matched order stable.
        keyed.append((primary, 0 if matched else 1, idx, r["to_uid"], r["relation_name"]))
    keyed.sort(key=lambda x: (x[0], x[1], x[2]))
    for pos, item in enumerate(keyed):
        conn.execute(
            "UPDATE relations SET position=? WHERE from_uid=? AND to_uid=? AND relation_name=?",
            (pos, from_uid, item[3], item[4]),
        )
    return moved


def list_relations(conn: sqlite3.Connection, from_uid: str) -> list[dict]:
    rows = conn.execute(
        "SELECT to_uid, relation_name, comment, position FROM relations "
        "WHERE from_uid=? ORDER BY position",
        (from_uid,),
    ).fetchall()
    return [dict(r) for r in rows]

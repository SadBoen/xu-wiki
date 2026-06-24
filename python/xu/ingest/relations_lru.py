"""Relation LRU operations (PRIN-ARCH-7~10, CONST-ARCH-4).

A node's out-edges form one ordered list (max 50). Stored in the SQLite
relations table:
  from_uid, to_uid, relation_name, comment, position, created_at
  PRIMARY KEY (from_uid, to_uid, relation_name)

Position = smaller is closer to head (more recently touched).
Frontmatter relations YAML field is no longer used for storage.
"""
from __future__ import annotations

from ..utils.constants import MAX_EDGES
from ..utils.paths import now_ts
from ..utils.wiki import WikiContext


def _conn(ctx: WikiContext):
    return ctx.connect()


def add_relation(
    ctx: WikiContext,
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
    ts = now_ts()
    conn = _conn(ctx)
    try:
        # Check if relation already exists
        existing = conn.execute(
            "SELECT position FROM relations WHERE from_uid=? AND to_uid=? AND relation_name=?",
            (from_uid, to_uid, relation_name),
        ).fetchone()

        if existing is not None:
            # Refresh: delete and re-insert at head
            conn.execute(
                "DELETE FROM relations WHERE from_uid=? AND to_uid=? AND relation_name=?",
                (from_uid, to_uid, relation_name),
            )

        # Shift all existing edges one position down (toward tail)
        conn.execute(
            "UPDATE relations SET position = position + 1 WHERE from_uid=?",
            (from_uid,),
        )

        # Insert new/refreshed edge at head (position = 0)
        conn.execute(
            "INSERT INTO relations (from_uid, to_uid, relation_name, comment, position, created_at) VALUES (?,?,?,?,?,?)",
            (from_uid, to_uid, relation_name, comment, 0, ts),
        )

        # Re-number to ensure contiguous 0..N-1
        _renumber_rels(conn, from_uid)

        # Check if we exceed max_edges and need to evict tail
        rows = conn.execute(
            "SELECT to_uid, relation_name FROM relations WHERE from_uid=? ORDER BY position",
            (from_uid,),
        ).fetchall()

        evicted = None
        if len(rows) > max_edges:
            evicted_row = rows[-1]
            evicted = {"to_uid": evicted_row["to_uid"], "relation_name": evicted_row["relation_name"]}
            conn.execute(
                "DELETE FROM relations WHERE from_uid=? AND to_uid=? AND relation_name=?",
                (from_uid, evicted_row["to_uid"], evicted_row["relation_name"]),
            )
            _renumber_rels(conn, from_uid)

        action = "refreshed" if existing is not None else "created"
        conn.commit()
        return {"action": action, "evicted": evicted}
    finally:
        conn.close()


def _renumber_rels(conn, from_uid: str) -> None:
    """Reassign contiguous positions 0..N-1 matching OLD SQLite _renumber."""
    rows = conn.execute(
        "SELECT to_uid, relation_name FROM relations WHERE from_uid=? ORDER BY position",
        (from_uid,),
    ).fetchall()
    for i, row in enumerate(rows):
        conn.execute(
            "UPDATE relations SET position=? WHERE from_uid=? AND to_uid=? AND relation_name=?",
            (i, from_uid, row["to_uid"], row["relation_name"]),
        )


def touch_relation(ctx: WikiContext, from_uid: str, to_uid: str) -> bool:
    """Query hit → advance matched relation(s) one position toward the head.

    Uses the same sort-based advance as the original SQLite implementation.
    Modifies SQLite relations table in-place.
    """
    conn = _conn(ctx)
    try:
        rows = conn.execute(
            "SELECT to_uid, relation_name, position FROM relations WHERE from_uid=?",
            (from_uid,),
        ).fetchall()

        if not rows:
            return False

        if not any(r["to_uid"] == to_uid for r in rows):
            return False

        keyed = []
        for r in rows:
            matched = r["to_uid"] == to_uid
            pos = r["position"]
            primary = pos - 1 if (matched and pos > 0) else pos
            keyed.append((primary, 0 if matched else 1, pos, r))

        keyed.sort(key=lambda x: (x[0], x[1], x[2]))
        for new_pos, (_, _, _, r) in enumerate(keyed):
            conn.execute(
                "UPDATE relations SET position=? WHERE from_uid=? AND to_uid=? AND relation_name=?",
                (new_pos, from_uid, r["to_uid"], r["relation_name"]),
            )

        conn.commit()
        return True
    finally:
        conn.close()


def list_relations(ctx: WikiContext, from_uid: str) -> list[dict]:
    """Return ordered relations list from SQLite (position = list index)."""
    conn = _conn(ctx)
    try:
        rows = conn.execute(
            "SELECT to_uid, relation_name, comment, created_at, position FROM relations WHERE from_uid=? ORDER BY position",
            (from_uid,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

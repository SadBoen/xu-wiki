"""IDF (Inverse Document Frequency) storage in SQLite idf table.

Schema (defined in utils.db):
  CREATE TABLE idf (
      noun       TEXT PRIMARY KEY,
      freq       INTEGER NOT NULL,
      weight     REAL NOT NULL,
      updated_at INTEGER
  )

Read:  load_idf(ctx)     → dict[noun, (freq, weight)]
Write: dump_idf(ctx, idf)→ None (replaces all rows)
Increment: increment_idf(ctx, nouns_dict) — upsert per-noun counts
"""
from __future__ import annotations

from ..utils.constants import IDF_CONSTANT
from ..utils.paths import now_ts


def load_idf(ctx) -> dict[str, tuple[int, float]]:
    """Load IDF noun table from SQLite. Returns {noun: (freq, weight)}."""
    conn = ctx.connect()
    try:
        rows = conn.execute("SELECT noun, freq, weight FROM idf").fetchall()
        return {row["noun"]: (row["freq"], row["weight"]) for row in rows}
    finally:
        conn.close()


def dump_idf(ctx, idf: dict[str, tuple[int, float]]) -> None:
    """Replace all IDF rows in SQLite."""
    conn = ctx.connect()
    try:
        ts = now_ts()
        conn.execute("DELETE FROM idf")
        for noun, (freq, weight) in idf.items():
            conn.execute(
                "INSERT INTO idf(noun, freq, weight, updated_at) VALUES (?,?,?,?)",
                (noun, freq, weight, ts),
            )
        conn.commit()
    finally:
        conn.close()


def increment_idf(ctx, nouns: dict[str, int]) -> None:
    """Upsert noun counts into SQLite idf table (CONST-ING-6)."""
    if not nouns:
        return
    conn = ctx.connect()
    try:
        ts = now_ts()
        for noun, cnt in nouns.items():
            row = conn.execute("SELECT freq FROM idf WHERE noun=?", (noun,)).fetchone()
            new_freq = (row["freq"] if row else 0) + cnt
            new_weight = IDF_CONSTANT / (new_freq + 1)
            conn.execute(
                "INSERT INTO idf(noun, freq, weight, updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(noun) DO UPDATE SET freq=?, weight=?, updated_at=?",
                (noun, new_freq, new_weight, ts, new_freq, new_weight, ts),
            )
        conn.commit()
    finally:
        conn.close()

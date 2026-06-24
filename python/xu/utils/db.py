"""SQLite schema + access layer (CONST-ARCH-7).

5 tables:
  node_page    — L1 immutable knowledge pages (ingested from raw files)
  node_derived — L2 List + L3 Report (human/agent-curated)
  patches      — L1 revision overlay (page never mutated, patches stack)
  relations    — LRU edge list between any nodes (max 50 per from_uid)
  idf          — noun frequency for TF-IDF query scoring

WAL mode + foreign keys + busy timeout are mandatory (CONST-ARCH-7).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS node_page (
    uid           TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    slug          TEXT,
    rel_md_path   TEXT,                 -- relative path to .md file
    raw_path      TEXT,                 -- relative path under raws/
    content_type  TEXT NOT NULL DEFAULT 'article',
    content_hash  TEXT,                 -- body SHA256 (Level 1 dedup)
    source_hash   TEXT,                 -- source file SHA256 (Level 2 dedup)
    source_hash_compressed TEXT,        -- post-compression hash for images
    active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    attrs         TEXT,                 -- JSON extension attributes
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL,
    body          TEXT                  -- inlined page body
);
CREATE INDEX IF NOT EXISTS idx_page_content_hash ON node_page(content_hash);
CREATE INDEX IF NOT EXISTS idx_page_source_hash ON node_page(source_hash);
CREATE INDEX IF NOT EXISTS idx_page_active ON node_page(active);

CREATE TABLE IF NOT EXISTS node_derived (
    uid           TEXT PRIMARY KEY,
    layer         TEXT NOT NULL CHECK (layer IN ('List','Report')),
    title         TEXT NOT NULL,
    dimension     TEXT,                 -- L2 comparison dimension
    attrs         TEXT,                 -- JSON extension attributes
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL,
    body          TEXT NOT NULL         -- inlined YAML body
);
CREATE INDEX IF NOT EXISTS idx_derived_layer ON node_derived(layer);

-- L1 revision table
CREATE TABLE IF NOT EXISTS patches (
    page_uid    TEXT NOT NULL,
    version     INTEGER NOT NULL,
    op          TEXT NOT NULL CHECK (op IN ('create','revise','correct')),
    delta       TEXT NOT NULL,
    author      TEXT,
    created_at  INTEGER,
    PRIMARY KEY (page_uid, version),
    FOREIGN KEY (page_uid) REFERENCES node_page(uid) ON DELETE CASCADE
);

-- IDF noun frequency table
CREATE TABLE IF NOT EXISTS idf (
    noun        TEXT PRIMARY KEY,
    freq        INTEGER NOT NULL,
    weight      REAL NOT NULL,
    updated_at  INTEGER
);

-- Relation LRU linked list
CREATE TABLE IF NOT EXISTS relations (
    from_uid       TEXT NOT NULL,
    to_uid         TEXT NOT NULL,
    relation_name  TEXT NOT NULL,
    comment        TEXT,
    position       INTEGER NOT NULL,
    created_at     INTEGER,
    PRIMARY KEY (from_uid, to_uid, relation_name)
);
CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_uid, position);
CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_uid);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_schema(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def idf_increment(conn, body: str, *, extract_nouns_fn, constant: float) -> None:
    """Increment IDF frequencies from nouns extracted from body."""
    from .paths import now_ts
    nouns = extract_nouns_fn(body)
    if not nouns:
        return
    ts = now_ts()
    for noun, cnt in nouns.items():
        row = conn.execute("SELECT freq FROM idf WHERE noun=?", (noun,)).fetchone()
        new_freq = (row["freq"] if row else 0) + cnt
        weight = constant / (new_freq + 1)
        conn.execute(
            "INSERT INTO idf(noun, freq, weight, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(noun) DO UPDATE SET freq=?, weight=?, updated_at=?",
            (noun, new_freq, weight, ts, new_freq, weight, ts),
        )


def write_page_body(conn: sqlite3.Connection, uid: str, body: str) -> None:
    """Upsert the inlined body for a page node."""
    from .paths import now_ts
    ts = now_ts()
    conn.execute(
        "UPDATE node_page SET body=?, updated_at=? WHERE uid=?",
        (body, ts, uid),
    )
    if conn.total_changes == 0:
        conn.execute(
            "INSERT INTO node_page(uid, title, content_type, body, created_at, updated_at) "
            "VALUES (?, ?, 'article', ?, ?, ?)",
            (uid, uid, body, ts, ts),
        )


def read_page_body(conn: sqlite3.Connection, uid: str) -> str | None:
    """Read the inlined body for a page node."""
    row = conn.execute("SELECT body FROM node_page WHERE uid=?", (uid,)).fetchone()
    return row["body"] if row else None


def find_any_node(conn: sqlite3.Connection, uid: str) -> dict | None:
    """Find a node by UID in either node_page or node_derived."""
    row = conn.execute(
        "SELECT uid, 'Page' as layer, title, active FROM node_page WHERE uid=? "
        "UNION ALL "
        "SELECT uid, layer, title, 1 as active FROM node_derived WHERE uid=?",
        (uid, uid),
    ).fetchone()
    return dict(row) if row else None

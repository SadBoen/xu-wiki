"""SQLite schema + access layer (PRIN-ARCH-16, CONST-ARCH-7).

Schema reserves positions for all three layers (L1/L2/L3) plus the two
derived tables (patches / idf) and the relation LRU linked list.
WAL mode + foreign keys + busy timeout are mandatory (CONST-ARCH-7).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    uid           TEXT PRIMARY KEY,
    layer         TEXT NOT NULL CHECK (layer IN ('Page','List','Report')),
    template      TEXT NOT NULL,
    title         TEXT NOT NULL,
    node_path     TEXT NOT NULL DEFAULT '',
    slug          TEXT,
    rel_md_path   TEXT,                 -- relative path to .md (NULL only for legacy DB-only L2/L3 rows)
    raw_path      TEXT,                 -- relative path under raws/
    content_hash  TEXT,                 -- body SHA256 (Level 1 dedup)
    source_hash   TEXT,                 -- source file SHA256 (Level 2 dedup)
    source_hash_compressed TEXT,        -- post-compression hash for images (PRIN-ING-12)
    active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    digest        TEXT,
    attrs         TEXT,                 -- JSONB extension attributes
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_layer ON nodes(layer);
CREATE INDEX IF NOT EXISTS idx_nodes_active ON nodes(active);
CREATE INDEX IF NOT EXISTS idx_nodes_content_hash ON nodes(content_hash);
CREATE INDEX IF NOT EXISTS idx_nodes_source_hash ON nodes(source_hash);
CREATE INDEX IF NOT EXISTS idx_nodes_node_path ON nodes(node_path);

-- L1 revision table (PRIN-ARCH-3, CONST-ING-7)
CREATE TABLE IF NOT EXISTS patches (
    page_uid    TEXT NOT NULL,
    version     INTEGER NOT NULL,
    op          TEXT NOT NULL CHECK (op IN ('create','revise','correct')),
    delta       TEXT NOT NULL,
    author      TEXT,
    created_at  INTEGER,
    PRIMARY KEY (page_uid, version),
    FOREIGN KEY (page_uid) REFERENCES nodes(uid) ON DELETE CASCADE
);

-- IDF noun frequency table (PRIN-ARCH-20, CONST-ING-6)
CREATE TABLE IF NOT EXISTS idf (
    noun        TEXT PRIMARY KEY,
    freq        INTEGER NOT NULL,
    weight      REAL NOT NULL,
    updated_at  INTEGER
);

-- Relation LRU linked list (PRIN-ARCH-8, CONST-ARCH-4).
-- position: smaller = closer to head (more recently touched). No category, no score.
CREATE TABLE IF NOT EXISTS relations (
    from_uid       TEXT NOT NULL,
    to_uid         TEXT NOT NULL,
    relation_name  TEXT NOT NULL,
    comment        TEXT,
    position       INTEGER NOT NULL,
    created_at     INTEGER,
    PRIMARY KEY (from_uid, to_uid, relation_name),
    FOREIGN KEY (from_uid) REFERENCES nodes(uid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_uid, position);
CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_uid);

-- L3 evidence chain (BAN-ARCH-5, CONST-DOC-3)
CREATE TABLE IF NOT EXISTS evidence (
    report_uid  TEXT NOT NULL,
    ref_uid     TEXT NOT NULL,
    note        TEXT,
    PRIMARY KEY (report_uid, ref_uid),
    FOREIGN KEY (report_uid) REFERENCES nodes(uid) ON DELETE CASCADE,
    FOREIGN KEY (ref_uid) REFERENCES nodes(uid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_evidence_report ON evidence(report_uid);
CREATE INDEX IF NOT EXISTS idx_evidence_ref ON evidence(ref_uid);

-- L2 list membership (PRIN-ARCH-4)
CREATE TABLE IF NOT EXISTS list_members (
    list_uid    TEXT NOT NULL,
    member_uid  TEXT NOT NULL,
    position    INTEGER NOT NULL,
    PRIMARY KEY (list_uid, member_uid),
    FOREIGN KEY (list_uid) REFERENCES nodes(uid) ON DELETE CASCADE,
    FOREIGN KEY (member_uid) REFERENCES nodes(uid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_list_members ON list_members(list_uid, position);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
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
    """Increment IDF frequencies from nouns extracted from body
    (PRIN-ING-9, CONST-ING-6). Shared across ingest / album / any future
    writer that adds text to a Page body.

    `extract_nouns_fn` is injected to keep this module dependency-free
    of the splitter module (utils.db is the lowest layer). `constant`
    is the IDF constant (typically IDF_CONSTANT from utils.constants).
    """
    from .paths import now_ts  # local import: avoid circular at module load
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

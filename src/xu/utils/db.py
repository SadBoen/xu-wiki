"""SQLite schema + access layer (PRIN-ARCH-16, CONST-ARCH-7).

Schema reserves positions for Page/Entity/List/Report layers plus the
patches derived table and the relation LRU linked list.
WAL mode + foreign keys + busy timeout are mandatory (CONST-ARCH-7).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    uid           TEXT PRIMARY KEY,
    layer         TEXT NOT NULL CHECK (layer IN ('Page','List','Report','Entity')),
    content_type  TEXT NOT NULL,
    title         TEXT NOT NULL,
    node_path     TEXT NOT NULL DEFAULT '',
    slug          TEXT,
    rel_md_path   TEXT,                 -- relative path to .md (NULL only for legacy DB-only rows)
    raw_path      TEXT,                 -- relative path under raws/
    content_hash  TEXT,                 -- body SHA256 (Level 1 dedup)
    source_hash   TEXT,                 -- source file SHA256 (Level 2 dedup)
    source_hash_compressed TEXT,        -- post-compression hash for images (PRIN-ING-12)
    active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    attrs         TEXT,                 -- JSONB extension attributes
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_layer ON nodes(layer);
CREATE INDEX IF NOT EXISTS idx_nodes_active ON nodes(active);
CREATE INDEX IF NOT EXISTS idx_nodes_content_hash ON nodes(content_hash);
CREATE INDEX IF NOT EXISTS idx_nodes_source_hash ON nodes(source_hash);
CREATE INDEX IF NOT EXISTS idx_nodes_node_path ON nodes(node_path);

-- Page revision table (PRIN-ARCH-3, CONST-ING-7)
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

-- Report evidence chain (BAN-ARCH-5, CONST-DOC-3)
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

-- List membership (PRIN-ARCH-4)
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

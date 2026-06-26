use pyo3::prelude::*;
use pyo3::types::PyTuple;
use std::collections::HashMap;
use std::path::Path;

const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS node_page (uid TEXT PRIMARY KEY, title TEXT NOT NULL, slug TEXT, raw_path TEXT, content_type TEXT NOT NULL DEFAULT 'article', content_hash TEXT, source_hash TEXT, source_hash_compressed TEXT, active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)), attrs TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, body TEXT);
CREATE INDEX IF NOT EXISTS idx_page_content_hash ON node_page(content_hash);
CREATE INDEX IF NOT EXISTS idx_page_source_hash ON node_page(source_hash);

CREATE TABLE IF NOT EXISTS node_derived (uid TEXT PRIMARY KEY, layer TEXT NOT NULL CHECK (layer IN ('Entity','List','Report')), title TEXT NOT NULL, dimension TEXT, attrs TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, body TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS patches (page_uid TEXT NOT NULL, version INTEGER NOT NULL, op TEXT NOT NULL CHECK (op IN ('create','revise','correct')), delta TEXT NOT NULL, author TEXT, created_at INTEGER, PRIMARY KEY (page_uid, version), FOREIGN KEY (page_uid) REFERENCES node_page(uid) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS relations (from_uid TEXT NOT NULL, to_uid TEXT NOT NULL, relation_name TEXT NOT NULL, comment TEXT, position INTEGER NOT NULL, created_at INTEGER, PRIMARY KEY (from_uid, to_uid, relation_name));
CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_uid, position);
"#;

pub struct Db { py_conn: PyObject }

impl Db {
    pub fn open(path: &Path) -> PyResult<Self> {
        Python::with_gil(|py| {
            let sqlite3 = py.import_bound("sqlite3")?;
            let conn = sqlite3.call_method1("connect", (path.to_string_lossy().as_ref(),))?;
            conn.setattr("row_factory", sqlite3.getattr("Row")?)?;
            conn.call_method1("executescript", ("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;",))?;
            Ok(Db { py_conn: conn.into() })
        })
    }

    pub fn init_schema(&self) -> PyResult<()> {
        Python::with_gil(|py| {
            let conn = self.py_conn.bind(py).clone();
            conn.call_method1("executescript", (SCHEMA,))?;
            conn.call_method0("commit")?;
            Ok(())
        })
    }

    /// Execute with String params. Returns Err on SQL failure.
    pub fn exec(&self, sql: &str, params: Vec<String>) -> Result<(), String> {
        Python::with_gil(|py| -> Result<(), String> {
            let conn = self.py_conn.bind(py).clone();
            let py_params = PyTuple::new_bound(py, &params);
            conn.call_method1("execute", (sql, &py_params))
                .map_err(|e| e.to_string())?;
            Ok(())
        })
    }

    /// Query returning Vec<HashMap<String,String>>.
    /// Handles INTEGER/REAL/TEXT/NULL via Python str() fallback.
    pub fn query_map(&self, sql: &str, params: Vec<String>) -> Result<Vec<HashMap<String, String>>, String> {
        Python::with_gil(|py| -> Result<Vec<HashMap<String, String>>, String> {
            let conn = self.py_conn.bind(py).clone();
            let py_params = PyTuple::new_bound(py, &params);
            let cursor = conn.call_method1("execute", (sql, &py_params))
                .map_err(|e| e.to_string())?;
            let mut rows = vec![];
            let iter = cursor.iter().map_err(|e| e.to_string())?;
            for item in iter {
                if let Ok(r) = item {
                    let keys: Vec<String> = r.getattr("keys")
                        .and_then(|k| k.call0())
                        .and_then(|k| k.extract())
                        .map_err(|e| e.to_string())?;
                    let mut map = HashMap::new();
                    for key in keys {
                        let obj = r.get_item(key.as_str())
                            .map_err(|e| e.to_string())?;
                        let val: String = obj.extract::<String>()
                            .or_else(|_| obj.str().map(|s| s.to_string()))
                            .unwrap_or_default();
                        map.insert(key, val);
                    }
                    rows.push(map);
                }
            }
            Ok(rows)
        }).map_err(|e| e.to_string())
    }

    pub fn commit(&self) -> Result<(), String> {
        Python::with_gil(|py| -> Result<(), String> {
            let conn = self.py_conn.bind(py).clone();
            conn.call_method0("commit").map_err(|e| e.to_string())?;
            Ok(())
        })
    }
}

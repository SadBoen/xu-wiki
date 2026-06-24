//! xu-wiki core — pyo3 bindings for the Python xu package.

pub mod commands;
pub mod db;
pub mod error;
pub mod frontmatter;
pub mod paths;
pub mod response;
pub mod scanner;
pub mod slicing;
pub mod splitter;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde_json::Value;
use std::collections::HashMap;

fn py_to_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    let json_str = Python::with_gil(|py| -> PyResult<String> {
        let json_module = py.import_bound("json")?;
        json_module.call_method1("dumps", (obj,))?.extract::<String>()
    })?;
    serde_json::from_str(&json_str)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

fn value_to_py(py: Python<'_>, v: &Value) -> PyResult<PyObject> {
    let json_str = serde_json::to_string(v)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    let json_module = py.import_bound("json")?;
    let obj = json_module.call_method1("loads", (json_str,))?;
    Ok(obj.into())
}

fn dict_to_py(py: Python<'_>, map: &HashMap<String, i32>) -> PyResult<PyObject> {
    let dict = PyDict::new_bound(py);
    for (k, v) in map {
        dict.set_item(k, *v)?;
    }
    Ok(dict.into())
}

/// Convert serde_yaml::Mapping to serde_json::Value
fn yaml_map_to_json(map: &serde_yaml::Mapping) -> Value {
    let mut json_map = serde_json::Map::new();
    for (k, v) in map {
        let key = k.as_str().unwrap_or("").to_string();
        let val = yaml_value_to_json(v);
        json_map.insert(key, val);
    }
    Value::Object(json_map)
}

fn yaml_value_to_json(v: &serde_yaml::Value) -> Value {
    match v {
        serde_yaml::Value::String(s) => Value::String(s.clone()),
        serde_yaml::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Value::Number(serde_json::Number::from(i))
            } else if let Some(f) = n.as_f64() {
                serde_json::Number::from_f64(f)
                    .map(Value::Number)
                    .unwrap_or(Value::Null)
            } else {
                Value::Null
            }
        }
        serde_yaml::Value::Bool(b) => Value::Bool(*b),
        serde_yaml::Value::Sequence(seq) => {
            Value::Array(seq.iter().map(yaml_value_to_json).collect())
        }
        serde_yaml::Value::Mapping(m) => yaml_map_to_json(m),
        _ => Value::Null,
    }
}

// ---- Exposed functions ----

#[pyfunction]
fn gen_uid() -> String { paths::gen_uid() }

#[pyfunction]
fn is_valid_uid(uid: &str) -> bool { paths::is_valid_uid(uid) }

#[pyfunction]
fn sha256_text(text: &str) -> String { paths::sha256_text(text) }

#[pyfunction]
fn sha256_file(path: &str) -> PyResult<String> {
    Ok(paths::sha256_file(std::path::Path::new(path))?)
}

#[pyfunction]
#[pyo3(signature = (text, maxlen=None))]
fn safe_slug(text: &str, maxlen: Option<usize>) -> String {
    paths::safe_slug(text, maxlen.unwrap_or(80))
}

#[pyfunction]
fn safe_node_path(path: &str) -> PyResult<String> {
    paths::safe_node_path(path)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
}

#[pyfunction]
fn parse_frontmatter(py: Python<'_>, text: &str) -> PyResult<(PyObject, String)> {
    let (fm, body) = frontmatter::parse(text);
    let value = yaml_map_to_json(&fm);
    Ok((value_to_py(py, &value)?, body))
}

#[pyfunction]
fn render_frontmatter(_py: Python<'_>, fm: Bound<'_, PyDict>, body: &str) -> PyResult<String> {
    let fm_value = py_to_value(&fm.into_any())?;
    // Convert serde_json Map back to serde_yaml Mapping
    let mut yaml_map = serde_yaml::Mapping::new();
    if let Value::Object(m) = fm_value {
        for (k, v) in m {
            let yv = json_value_to_yaml(&v);
            yaml_map.insert(serde_yaml::Value::String(k), yv);
        }
    }
    Ok(frontmatter::render(&yaml_map, body))
}

fn json_value_to_yaml(v: &Value) -> serde_yaml::Value {
    match v {
        Value::String(s) => serde_yaml::Value::String(s.clone()),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                serde_yaml::Value::Number(i.into())
            } else if let Some(f) = n.as_f64() {
                serde_yaml::Value::Number(serde_yaml::Number::from(f as i64))
            } else {
                serde_yaml::Value::Null
            }
        }
        Value::Bool(b) => serde_yaml::Value::Bool(*b),
        Value::Array(arr) => serde_yaml::Value::Sequence(arr.iter().map(json_value_to_yaml).collect()),
        Value::Object(m) => {
            let mut ym = serde_yaml::Mapping::new();
            for (k, v) in m {
                ym.insert(serde_yaml::Value::String(k.clone()), json_value_to_yaml(v));
            }
            serde_yaml::Value::Mapping(ym)
        }
        Value::Null => serde_yaml::Value::Null,
    }
}

#[pyfunction]
#[pyo3(signature = (text, max_lines=None))]
fn split_pages(text: &str, max_lines: Option<usize>) -> Vec<String> {
    splitter::split_pages(text, max_lines)
}

#[pyfunction]
fn extract_nouns_fallback(text: &str) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        let nouns = splitter::extract_nouns_fallback(text);
        dict_to_py(py, &nouns)
    })
}

#[pyfunction]
fn make_slice(
    text: &str, hit_start: usize, hit_end: usize,
    soft_limit: usize, hard_limit: usize,
) -> (usize, usize, String) {
    slicing::make_slice(text, hit_start, hit_end, soft_limit, hard_limit)
}

#[pyfunction]
fn scan_bodies(
    py: Python<'_>,
    uid_body: Bound<'_, PyDict>,
    keywords: Vec<String>,
) -> PyResult<PyObject> {
    let mut map: HashMap<String, String> = HashMap::new();
    for (k, v) in uid_body.iter() {
        let key: String = k.extract()?;
        let val: String = v.extract()?;
        map.insert(key, val);
    }
    let results = scanner::scan_bodies(&map, &keywords);
    let result_dict = PyDict::new_bound(py);
    for (kw, hits) in results {
        let hits_py: Vec<PyObject> = hits
            .iter()
            .map(|h| {
                Python::with_gil(|py| {
                    let d = PyDict::new_bound(py);
                    let _ = d.set_item("uid", &h.uid);
                    let _ = d.set_item("char_pos", h.char_pos);
                    let _ = d.set_item("keyword", &h.keyword);
                    let _ = d.set_item("snippet", &h.snippet);
                    d.into()
                })
            })
            .collect();
        result_dict.set_item(kw, hits_py)?;
    }
    Ok(result_dict.into())
}

/// Validate body format (Rust -> Python bridge).
#[pyfunction]
fn validate_body_format(body: &str, content_type: &str) -> Option<String> {
    commands::validate_body_format(body, content_type)
}

/// Strip YAML frontmatter from text (Rust -> Python bridge).
#[pyfunction]
fn strip_frontmatter(text: &str) -> String {
    commands::strip_frontmatter(text)
}

/// Parse pending header from Phase 1 temp file (Rust -> Python bridge).
#[pyfunction]
fn parse_pending_header_py(text: &str) -> (std::collections::HashMap<String, String>, String) {
    commands::parse_pending_header(text)
}

// === Command pyfunctions (return JSON strings) ===

#[pyfunction] fn py_create(name: &str, path: &str, alias: Option<&str>) -> String { commands::cmd_create(name, path, alias).to_string() }
#[pyfunction] fn py_selfcheck() -> String { commands::cmd_selfcheck().to_string() }
#[pyfunction] fn py_doctor(wiki: &str) -> String { commands::cmd_doctor(wiki).to_string() }
#[pyfunction] fn py_uninstall_plan(preserve_config: bool, keep_pip: bool) -> String { commands::cmd_uninstall_plan(preserve_config, keep_pip).to_string() }
#[pyfunction] fn py_uninstall_execute(preserve_config: bool, keep_pip: bool) -> String { commands::cmd_uninstall_execute(preserve_config, keep_pip).to_string() }
#[pyfunction] fn py_ingest_commit(wiki: &str, pending: &str, title: &str, content_type: &str, raw_path: &str, author: &str, relations: &str) -> String { commands::cmd_ingest_commit(wiki, pending, title, content_type, raw_path, author, relations).to_string() }
#[pyfunction] fn py_query(wiki: &str, core: &str, expansion: &str, top_k: usize) -> String { commands::cmd_query(wiki, core, expansion, top_k).to_string() }
#[pyfunction] fn py_expand(wiki: &str, uids: &str) -> String { commands::cmd_expand(wiki, uids).to_string() }
#[pyfunction] fn py_ingest_context(wiki: &str, keywords: &str) -> String { commands::cmd_ingest_context(wiki, keywords).to_string() }

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(gen_uid, m)?)?;
    m.add_function(wrap_pyfunction!(is_valid_uid, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_text, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_file, m)?)?;
    m.add_function(wrap_pyfunction!(safe_slug, m)?)?;
    m.add_function(wrap_pyfunction!(safe_node_path, m)?)?;
    m.add_function(wrap_pyfunction!(parse_frontmatter, m)?)?;
    m.add_function(wrap_pyfunction!(render_frontmatter, m)?)?;
    m.add_function(wrap_pyfunction!(split_pages, m)?)?;
    m.add_function(wrap_pyfunction!(extract_nouns_fallback, m)?)?;
    m.add_function(wrap_pyfunction!(make_slice, m)?)?;
    m.add_function(wrap_pyfunction!(scan_bodies, m)?)?;
    m.add_function(wrap_pyfunction!(validate_body_format, m)?)?;
    m.add_function(wrap_pyfunction!(strip_frontmatter, m)?)?;
    m.add_function(wrap_pyfunction!(parse_pending_header_py, m)?)?;
    m.add_function(wrap_pyfunction!(py_create, m)?)?;
    m.add_function(wrap_pyfunction!(py_selfcheck, m)?)?;
    m.add_function(wrap_pyfunction!(py_doctor, m)?)?;
    m.add_function(wrap_pyfunction!(py_uninstall_plan, m)?)?;
    m.add_function(wrap_pyfunction!(py_uninstall_execute, m)?)?;
    m.add_function(wrap_pyfunction!(py_ingest_commit, m)?)?;
    m.add_function(wrap_pyfunction!(py_query, m)?)?;
    m.add_function(wrap_pyfunction!(py_expand, m)?)?;
    m.add_function(wrap_pyfunction!(py_ingest_context, m)?)?;
    Ok(())
}

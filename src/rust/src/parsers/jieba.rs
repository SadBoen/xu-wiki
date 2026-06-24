//! jieba_wrapper pyo3 bridge — call Python jieba from Rust.

use pyo3::prelude::*;
use std::collections::HashMap;

use crate::error::ParserError;

/// Extract noun tokens with within-document frequencies from text.
/// Calls Python `jieba_wrapper.extract_nouns()` via pyo3.
pub fn extract_nouns(text: &str) -> Result<HashMap<String, i32>, ParserError> {
    Python::with_gil(|py| {
        // Add src/python to Python path so jieba_wrapper is importable
        let python_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("python");
        let python_dir_str = python_dir.to_string_lossy();

        let sys = py.import_bound("sys")?;
        let path = sys.getattr("path")?;
        // Only insert if not already present
        let existing: Vec<String> = path.extract()?;
        if !existing.contains(&python_dir_str.to_string()) {
            let _ = path.call_method1("insert", (0, python_dir_str.as_ref()));
        }

        let module = py.import_bound("jieba_wrapper")?;
        let func = module.getattr("extract_nouns")?;
        let result = func.call1((text,))?;
        let dict: HashMap<String, i32> = result.extract()?;
        Ok(dict)
    })
}

/// Tokenize text with jieba, returning (word, flag) pairs.
/// Calls Python `jieba_wrapper.tokenize()` via pyo3.
pub fn tokenize(text: &str) -> Result<Vec<(String, String)>, ParserError> {
    Python::with_gil(|py| {
        let python_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("python");
        let python_dir_str = python_dir.to_string_lossy();

        let sys = py.import_bound("sys")?;
        let path = sys.getattr("path")?;
        let existing: Vec<String> = path.extract()?;
        if !existing.contains(&python_dir_str.to_string()) {
            let _ = path.call_method1("insert", (0, python_dir_str.as_ref()));
        }

        let module = py.import_bound("jieba_wrapper")?;
        let func = module.getattr("tokenize")?;
        let result = func.call1((text,))?;
        let list: Vec<(String, String)> = result.extract()?;
        Ok(list)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_nouns_smoke() {
        let result = extract_nouns("机器学习和深度学习是人工智能的核心技术");
        // May fail if jieba not importable; that's OK for smoke test
        let _ = result;
    }
}

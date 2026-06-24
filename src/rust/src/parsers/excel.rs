//! excel_parser pyo3 bridge — call Python openpyxl from Rust.

use pyo3::prelude::*;
use std::path::Path;

use crate::error::ParserError;
use crate::parsers::ParseResult;

/// Extensions supported by the excel parser.
const SUPPORTED: &[&str] = &[".xlsx", ".xls", ".csv"];

/// Check if a file extension is supported.
pub fn can_parse(path: &Path) -> bool {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|e| SUPPORTED.contains(&e.to_lowercase().as_str()))
        .unwrap_or(false)
}

/// Parse an Excel file via Python openpyxl, returning YAML text.
pub fn parse_excel(path: &Path) -> Result<ParseResult, ParserError> {
    if !can_parse(path) {
        return Err(ParserError::UnsupportedExtension(
            path.extension()
                .and_then(|e| e.to_str())
                .unwrap_or("unknown")
                .to_string(),
        ));
    }

    let path_str = path.to_string_lossy().to_string();

    Python::with_gil(|py| {
        let python_dir =
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("python");
        let sys = py.import_bound("sys")?;
        let py_path = sys.getattr("path")?;
        let existing: Vec<String> = py_path.extract()?;
        let python_dir_str = python_dir.to_string_lossy();
        if !existing.contains(&python_dir_str.to_string()) {
            let _ = py_path.call_method1("insert", (0, python_dir_str.as_ref()));
        }

        let module = py.import_bound("excel_parser")?;
        let func = module.getattr("parse_excel")?;
        let result = func.call1((&path_str,))?;
        let content: String = result.extract()?;

        Ok(ParseResult::new(content, "openpyxl"))
    })
}

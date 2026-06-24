//! Custom error type for xu-parser.

use thiserror::Error;

#[derive(Error, Debug)]
pub enum ParserError {
    #[error("Python error: {0}")]
    PythonError(String),

    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),

    #[error("parser not available for: {0}")]
    UnsupportedExtension(String),

    #[error("parse failed: {0}")]
    ParseFailed(String),
}

impl From<pyo3::PyErr> for ParserError {
    fn from(e: pyo3::PyErr) -> Self {
        ParserError::PythonError(e.to_string())
    }
}

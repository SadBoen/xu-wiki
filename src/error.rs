//! Unified error type for xu-wiki.

use thiserror::Error;

#[derive(Error, Debug)]
pub enum XuError {
    #[error("Python error: {0}")]
    Python(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("YAML error: {0}")]
    Yaml(#[from] serde_yaml::Error),

    #[error("wiki not found: {0}")]
    WikiNotFound(String),

    #[error("node not found: {0}")]
    NodeNotFound(String),

    #[error("invalid argument: {0}")]
    InvalidArgument(String),

    #[error("parser not available for: {0}")]
    UnsupportedExtension(String),

    #[error("parse failed: {0}")]
    ParseFailed(String),

    #[error("{0}")]
    Generic(String),
}

impl From<pyo3::PyErr> for XuError {
    fn from(e: pyo3::PyErr) -> Self {
        XuError::Python(e.to_string())
    }
}

impl From<String> for XuError {
    fn from(s: String) -> Self {
        XuError::Generic(s)
    }
}

impl From<&str> for XuError {
    fn from(s: &str) -> Self {
        XuError::Generic(s.to_string())
    }
}

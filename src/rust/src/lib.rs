//! xu-parser — pyo3 Rust-Python hybrid parser layer for xu-wiki.
//!
//! Provides a unified `Parser` trait. Python libraries (jieba, markitdown,
//! openpyxl) are called from Rust via pyo3.

use std::collections::HashMap;
use std::path::Path;

pub mod error;
pub mod parsers;

pub use error::ParserError;
pub use parsers::{ParseResult, Parser};

/// Extract noun tokens from text using jieba (called from Rust business logic).
pub fn extract_nouns(text: &str) -> Result<HashMap<String, i32>, ParserError> {
    parsers::jieba::extract_nouns(text)
}

/// Parse a document (.pdf/.docx/.pptx/.html) via markitdown fallback.
pub fn parse_document(path: &Path) -> Result<ParseResult, ParserError> {
    parsers::doc::parse_document(path)
}

/// Parse an Excel file (.xlsx/.xls/.csv) via openpyxl.
pub fn parse_excel(path: &Path) -> Result<ParseResult, ParserError> {
    parsers::excel::parse_excel(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_nouns_smoke() {
        let result = extract_nouns("机器学习和深度学习是人工智能的核心技术");
        let _ = result;
    }
}

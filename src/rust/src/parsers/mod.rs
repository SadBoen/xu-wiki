//! Parser submodules.

pub mod doc;
pub mod excel;
pub mod jieba;

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

pub use jieba::extract_nouns;

/// Result of a successful parse operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParseResult {
    /// The extracted text content (markdown for doc, yaml for excel).
    pub content_markdown: String,
    /// Arbitrary metadata extracted during parsing.
    pub metadata: HashMap<String, String>,
    /// Name of the parser that produced this result.
    pub parser_name: String,
}

impl ParseResult {
    pub fn new(content_markdown: String, parser_name: &str) -> Self {
        Self {
            content_markdown,
            metadata: HashMap::new(),
            parser_name: parser_name.to_string(),
        }
    }

    pub fn with_metadata(
        mut self,
        key: impl Into<String>,
        value: impl Into<String>,
    ) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    pub fn is_empty(&self) -> bool {
        self.content_markdown.trim().is_empty()
    }
}

/// Unified parser interface (not currently used as a trait object since
/// Python parsers are stateless function wrappers; defined for future extensibility).
pub trait Parser: Send + Sync {
    fn name(&self) -> &str;
    fn parse(&self, path: &Path) -> Result<ParseResult, crate::ParserError>;
}

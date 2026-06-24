//! Ingest helper functions (pyo3-exported for Python ingest.py).

use std::collections::HashMap;
use serde_yaml;

/// Validate body matches content_type format.
/// Returns None if valid, or error message string.
pub fn validate_body_format(body: &str, content_type: &str) -> Option<String> {
    if content_type == "article" {
        return None;
    }
    if content_type != "table" && content_type != "gallery" {
        return Some(format!("unknown content_type: {content_type}"));
    }
    if body.trim().is_empty() {
        return None;
    }
    let parsed: Result<serde_yaml::Value, _> = serde_yaml::from_str(body);
    match parsed {
        Ok(serde_yaml::Value::Sequence(seq)) => {
            for (i, item) in seq.iter().enumerate() {
                if !item.is_mapping() {
                    return Some(format!(
                        "content_type={content_type} body item {i} is not a dict"
                    ));
                }
                if content_type == "gallery" {
                    if let serde_yaml::Value::Mapping(ref m) = item {
                        if !m.contains_key(&serde_yaml::Value::String("filename".into())) {
                            return Some(format!(
                                "content_type=gallery body item {i} missing 'filename' field"
                            ));
                        }
                    }
                }
            }
            None
        }
        Ok(_) => Some(format!(
            "content_type={content_type} requires body to be a YAML list"
        )),
        Err(_) => Some(format!(
            "content_type={content_type} requires YAML list in body, but parsing failed"
        )),
    }
}

/// Strip YAML frontmatter (---...---) from markdown text.
pub fn strip_frontmatter(text: &str) -> String {
    if text.starts_with("---") {
        if let Some(end) = text[3..].find("\n---") {
            let body = text[3 + end + 4..].to_string();
            return body.trim_start_matches('\n').to_string();
        }
    }
    text.to_string()
}

/// Parse pending header metadata from Phase 1 temp file.
pub fn parse_pending_header(text: &str) -> (HashMap<String, String>, String) {
    let mut meta = HashMap::new();
    if text.starts_with("<!-- xu-pending") {
        if let Some(end) = text.find("-->") {
            let header = &text[15..end].trim();
            for tok in header.split_whitespace() {
                if let Some(eq) = tok.find('=') {
                    let k = tok[..eq].to_string();
                    let v = tok[eq + 1..].to_string();
                    meta.insert(k, v);
                }
            }
            let body = text[end + 3..].trim_start_matches('\n').to_string();
            return (meta, body);
        }
    }
    (meta, text.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_article_passes() {
        assert_eq!(validate_body_format("any text", "article"), None);
    }

    #[test]
    fn test_validate_table_valid() {
        let body = "- uid: X\ntitle: T\n- uid: Y\ntitle: U";
        assert_eq!(validate_body_format(body, "table"), None);
    }

    #[test]
    fn test_validate_table_not_list() {
        assert!(validate_body_format("not: a list", "table").is_some());
    }

    #[test]
    fn test_strip_frontmatter() {
        let text = "---\nuid: X\n---\n\nbody text";
        let body = strip_frontmatter(text);
        assert_eq!(body, "body text");
    }

    #[test]
    fn test_parse_pending_header() {
        let text = "<!-- xu-pending source_hash=abc parser=test -->\ncontent";
        let (meta, body) = parse_pending_header(text);
        assert_eq!(meta.get("source_hash").unwrap(), "abc");
        assert_eq!(body, "content");
    }
}

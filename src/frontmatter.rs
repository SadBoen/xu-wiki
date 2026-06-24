//! YAML frontmatter parsing / rendering for Node markdown files.
//! Pure Rust — serde_yaml, no Python deps.

use serde::{Deserialize, Serialize};
use serde_yaml::{Mapping, Value};

const DELIM: &str = "---";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Frontmatter {
    pub uid: String,
    pub title: String,
    pub layer: String,
    #[serde(default)]
    pub active: bool,
    #[serde(default)]
    pub content_type: Option<String>,
    #[serde(default)]
    pub created_at: Option<String>,
    #[serde(default)]
    pub updated_at: Option<String>,
    #[serde(default)]
    pub split_index: Option<i64>,
    #[serde(default)]
    pub parent_uid: Option<String>,
    #[serde(default)]
    pub source_hash: Option<String>,
    #[serde(default)]
    pub content_hash: Option<String>,
    #[serde(default)]
    pub relations: Vec<Value>,
    #[serde(flatten)]
    pub extra: Mapping,
}

/// Split a markdown document into (frontmatter dict, body).
pub fn parse(text: &str) -> (Mapping, String) {
    if !text.starts_with(DELIM) {
        return (Mapping::new(), text.to_string());
    }
    let lines: Vec<&str> = text.lines().collect();
    if lines.is_empty() || lines[0].trim() != DELIM {
        return (Mapping::new(), text.to_string());
    }
    let mut end: Option<usize> = None;
    for (i, line) in lines.iter().enumerate().skip(1) {
        if line.trim() == DELIM {
            end = Some(i);
            break;
        }
    }
    let end = match end {
        Some(e) => e,
        None => return (Mapping::new(), text.to_string()),
    };
    let fm_text = lines[1..end].join("\n");
    let body = if end + 1 < lines.len() {
        let b = lines[end + 1..].join("\n");
        b.trim_start_matches('\n').to_string()
    } else {
        String::new()
    };
    let fm: Mapping = serde_yaml::from_str(&fm_text).unwrap_or_default();
    (fm, body)
}

/// Render frontmatter + body into markdown string.
pub fn render(fm: &Mapping, body: &str) -> String {
    let fm_text = serde_yaml::to_string(fm).unwrap_or_default();
    let fm_text = fm_text.trim_end().trim_end_matches('\n');
    format!("{DELIM}\n{fm_text}\n{DELIM}\n\n{}\n", body.trim_end())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple() {
        let text = "---\nuid: ABC\n---\n\nbody text\n";
        let (fm, body) = parse(text);
        assert_eq!(fm.get("uid").unwrap().as_str().unwrap(), "ABC");
        assert_eq!(body.trim(), "body text");
    }

    #[test]
    fn test_no_frontmatter() {
        let (fm, body) = parse("just text");
        assert!(fm.is_empty());
        assert_eq!(body, "just text");
    }

    #[test]
    fn test_render_roundtrip() {
        let mut fm = Mapping::new();
        fm.insert("uid".into(), "ABC".into());
        fm.insert("title".into(), "Test".into());
        let rendered = render(&fm, "body");
        let (parsed, body) = parse(&rendered);
        assert_eq!(parsed.get("uid").unwrap().as_str().unwrap(), "ABC");
        assert!(body.contains("body"));
    }
}

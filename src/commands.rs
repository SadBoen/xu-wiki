//! Command implementations ported from Python commands/ to Rust.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use crate::error::XuError;
use crate::paths::{gen_uid, now_ts, safe_slug};
use crate::response;
use serde_json::{json, Value};

const WIKI_FORMAT_VERSION: &str = "1.0.0";

static NAME_REGEX: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"^[A-Za-z0-9_-]{1,64}$").unwrap());

fn build_skeleton(target: &Path, name: &str) -> Result<(), XuError> {
    fs::create_dir_all(target.join("raws"))?;
    fs::create_dir_all(target.join("nodes").join("page"))?;
    fs::create_dir_all(target.join("nodes").join("list"))?;
    fs::create_dir_all(target.join("nodes").join("report"))?;
    let xu_dir = target.join(".xu");
    fs::create_dir_all(&xu_dir)?;

    // wiki config
    let config = format!(
        "version: \"{WIKI_FORMAT_VERSION}\"\nname: \"{name}\"\ntemplates: {{}}\n"
    );
    fs::write(xu_dir.join("config.yaml"), config)?;

    // state.json
    let ts = now_ts();
    fs::write(
        xu_dir.join("state.json"),
        format!(r#"{{"version": "{WIKI_FORMAT_VERSION}", "created_at": {ts}}}"#),
    )?;

    // Create empty wiki.db placeholder (schema init via Python xu create)
    fs::write(xu_dir.join("wiki.db"), b"")?;
    Ok(())
}

/// create — initialize a new wiki instance.
pub fn cmd_create(name: &str, path: &str, _alias: Option<&str>) -> Value {
    if name.trim().is_empty() {
        return response::error("create requires --name", "MissingName", None, &[]);
    }
    if !NAME_REGEX.is_match(name) {
        return response::error(
            &format!("invalid wiki name: {name:?}"),
            "InvalidName",
            None,
            &["name must be alnum/-/_ and <= 64 chars".into()],
        );
    }

    let target = PathBuf::from(path);
    if !target.is_absolute() {
        return response::error(
            &format!("--path must be absolute; got: {path:?}"),
            "PathNotAbsolute",
            None,
            &[],
        );
    }

    if target.exists() && target.read_dir().map_or(false, |mut d| d.next().is_some()) {
        return response::warning(
            json!({"path": path, "name": name}),
            &format!("directory exists and is non-empty: {path}"),
        );
    }

    match build_skeleton(&target, name) {
        Ok(()) => response::success(
            json!({
                "name": name,
                "path": path,
                "version": WIKI_FORMAT_VERSION,
                "layout": ["raws/", "nodes/page/", "nodes/list/", "nodes/report/", ".xu/"],
            }),
            &format!("created empty wiki '{name}' at {path}"),
        ),
        Err(e) => response::error(
            &format!("create failed: {e}"),
            "CreateFailed",
            None,
            &[],
        ),
    }
}

/// selfcheck — verify installation health.
pub fn cmd_selfcheck() -> Value {
    let mut checks: Vec<Value> = vec![];

    let uid = gen_uid();
    checks.push(json!({"name": "uid_gen", "ok": !uid.is_empty(), "detail": uid}));

    let h = crate::paths::sha256_text("test");
    checks.push(json!({"name": "sha256", "ok": h.len() == 64}));

    let slug = safe_slug("Test Check", 80);
    checks.push(json!({"name": "slug", "ok": slug == "test-check", "detail": slug}));

    let all_ok = checks.iter().all(|c| c["ok"].as_bool().unwrap_or(false));

    if all_ok {
        response::success(
            json!({"checks": checks, "version": env!("CARGO_PKG_VERSION")}),
            "all core checks passed",
        )
    } else {
        response::warning(json!({"checks": checks}), "some checks failed")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cmd_create_missing_name() {
        let r = cmd_create("", "/tmp/wiki", None);
        assert_eq!(r["status"], "error");
    }

    #[test]
    fn test_cmd_create_relative_path() {
        let r = cmd_create("testwiki", "relative/path", None);
        assert_eq!(r["status"], "error");
    }

    #[test]
    fn test_cmd_create_invalid_name() {
        let r = cmd_create("bad name!", "/tmp/wiki", None);
        assert_eq!(r["status"], "error");
    }

    #[test]
    fn test_cmd_create_success() {
        let tmp = std::env::temp_dir().join(format!("xu-test-create-{}", gen_uid()));
        let r = cmd_create("testwiki", &tmp.to_string_lossy(), None);
        assert_eq!(r["status"], "success", "{r}");
        assert!(tmp.join("raws").is_dir());
        assert!(tmp.join(".xu").join("config.yaml").exists());
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_cmd_selfcheck() {
        let r = cmd_selfcheck();
        assert_eq!(r["status"], "success");
    }
}

// ---- Ingest helpers (pure Rust, no SQLite) ----

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
        return None; // empty body allowed
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
pub fn parse_pending_header(text: &str) -> (std::collections::HashMap<String, String>, String) {
    let mut meta = std::collections::HashMap::new();
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
mod ingest_tests {
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
        assert_eq!(meta.get("parser").unwrap(), "test");
        assert_eq!(body, "content");
    }
}
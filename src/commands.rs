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

/// create 鈥?initialize a new wiki instance.
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

/// selfcheck 鈥?verify installation health.
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
// ---- Uninstall (pure Rust, no SQLite) ----

/// Build uninstall plan (dry-run).
pub fn cmd_uninstall_plan(preserve_config: bool, keep_pip: bool) -> Value {
    let home = dirs_next::home_dir()
        .unwrap_or_else(|| PathBuf::from("/tmp"));
    let xu_config_dir = home.join(".xu-wiki");
    let exists = xu_config_dir.exists();

    let plan = json!({
        "mode": "dry-run",
        "execute": false,
        "pip_uninstall": !keep_pip,
        "purge_wikis": false,
        "purge_wikis_note": "wiki data is NEVER deleted (REQ-9)",
        "purge_config": !preserve_config,
        "global_dir": xu_config_dir.to_string_lossy(),
        "global_dir_exists": exists,
        "package": "xu-wiki",
        "installer": detect_installer(),
        "actions": []
    });

    response::success(plan, "dry-run: this is what would happen with --execute")
}

/// Execute uninstall (actually remove things).
/// Wiki data is NEVER deleted — hard invariant (REQ-9).
pub fn cmd_uninstall_execute(preserve_config: bool, keep_pip: bool) -> Value {
    let mut actions: Vec<Value> = vec![];

    // 1. Pip uninstall
    if !keep_pip {
        let pip_result = run_pip_uninstall();
        actions.push(json!({
            "action": "pip_uninstall",
            "ok": pip_result,
            "detail": if pip_result { "pip uninstall succeeded" } else { "pip uninstall skipped/failed" }
        }));
    }

    // 2. Config dir
    if !preserve_config {
        let home = dirs_next::home_dir().unwrap_or_else(|| PathBuf::from("/tmp"));
        let xu_dir = home.join(".xu-wiki");
        if xu_dir.exists() {
            match fs::remove_dir_all(&xu_dir) {
                Ok(()) => actions.push(json!({"action": "remove_config",
                    "path": xu_dir.to_string_lossy(), "ok": true})),
                Err(e) => actions.push(json!({"action": "remove_config",
                    "path": xu_dir.to_string_lossy(), "ok": false, "error": e.to_string()})),
            }
        }
    }

    // 3. Wiki data — NEVER deleted
    actions.push(json!({
        "action": "wikis",
        "note": "ALL wiki data preserved — never deleted (REQ-9)",
        "ok": true
    }));

    response::success(
        json!({
            "mode": "execute",
            "actions": actions,
            "wikis_preserved": true,
        }),
        "uninstall complete; all wiki data preserved",
    )
}

fn detect_installer() -> String {
    // Check for pipx first
    if which::which("pipx").is_ok() {
        return "pipx".to_string();
    }
    if which::which("pip").is_ok() || which::which("pip3").is_ok() {
        return "pip".to_string();
    }
    "unknown".to_string()
}

fn run_pip_uninstall() -> bool {
    std::process::Command::new("pip")
        .args(["uninstall", "xu-wiki", "-y"])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

#[cfg(test)]
mod uninstall_tests {
    use super::*;

    #[test]
    fn test_uninstall_plan_returns_success() {
        let r = cmd_uninstall_plan(false, false);
        assert_eq!(r["status"], "success");
        assert_eq!(r["data"]["mode"], "dry-run");
        assert_eq!(r["data"]["purge_wikis"], false);
    }

    #[test]
    fn test_uninstall_execute_returns_success() {
        let r = cmd_uninstall_execute(true, true); // preserve_config + keep_pip = no-op
        assert_eq!(r["status"], "success");
        assert_eq!(r["data"]["wikis_preserved"], true);
    }

    #[test]
    fn test_uninstall_wikis_never_deleted() {
        let r = cmd_uninstall_execute(false, false);
        assert_eq!(r["data"]["wikis_preserved"], true);
    }

    #[test]
    fn test_detect_installer_returns_string() {
        let installer = detect_installer();
        assert!(!installer.is_empty());
    }
}
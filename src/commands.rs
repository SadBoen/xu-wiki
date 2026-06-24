//! Command implementations — Rust owns all business logic.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use crate::db::Db;
use crate::paths::{gen_uid, now_ts, safe_slug};
use crate::response;
use serde_json::{json, Value};

static NAME_REGEX: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"^[A-Za-z0-9_-]{1,64}$").unwrap());

// ---- create ----

fn build_skeleton(target: &Path, name: &str) -> Result<(), String> {
    fs::create_dir_all(target.join("raws")).map_err(|e| e.to_string())?;
    let xu_dir = target.join(".xu");
    fs::create_dir_all(&xu_dir).map_err(|e| e.to_string())?;
    let cfg = format!("version: \"1.0.0\"\nname: \"{name}\"\ntemplates: {{}}\n");
    fs::write(xu_dir.join("config.yaml"), cfg).map_err(|e| e.to_string())?;
    let ts = now_ts();
    fs::write(xu_dir.join("state.json"), format!(r#"{{"version":"1.0.0","created_at":{ts}}}"#)).map_err(|e| e.to_string())?;
    let db = Db::open(&xu_dir.join("wiki.db")).map_err(|e| e.to_string())?;
    db.init_schema().map_err(|e| e.to_string())?;
    Ok(())
}

pub fn cmd_create(name: &str, path: &str, _alias: Option<&str>) -> Value {
    if name.trim().is_empty() {
        return response::error("create requires --name", "MissingName", None, &[]);
    }
    if !NAME_REGEX.is_match(name) {
        return response::error(&format!("invalid wiki name: {name:?}"), "InvalidName", None,
            &["name must be alnum/-/_ and <= 64 chars".into()]);
    }
    let target = PathBuf::from(path);
    if !target.is_absolute() {
        return response::error("--path must be absolute", "PathNotAbsolute", None, &[]);
    }
    if target.exists() && target.read_dir().map_or(false, |mut d| d.next().is_some()) {
        return response::warning(json!({"path":path,"name":name}), "directory exists and is non-empty");
    }
    match build_skeleton(&target, name) {
        Ok(()) => response::success(
            json!({"name":name,"path":path,"version":"1.0.0","layout":["raws/",".xu/"],"tables":["node_page","node_derived","patches","relations"]}),
            &format!("created wiki '{name}'"),
        ),
        Err(e) => response::error(&format!("create failed: {e}"), "CreateFailed", None, &[]),
    }
}

// ---- selfcheck ----

pub fn cmd_selfcheck() -> Value {
    let uid = gen_uid();
    let h = crate::paths::sha256_text("test");
    let slug = safe_slug("Test Check", 80);
    let all_ok = !uid.is_empty() && h.len() == 64 && slug == "test-check";
    let checks = json!([{"name":"uid_gen","ok":!uid.is_empty(),"detail":uid},{"name":"sha256","ok":h.len()==64},{"name":"slug","ok":slug=="test-check","detail":slug}]);
    if all_ok { response::success(json!({"checks":checks,"version":env!("CARGO_PKG_VERSION")}), "all core checks passed") }
    else { response::warning(json!({"checks":checks}), "some checks failed") }
}

// ---- doctor (filesystem) ----

pub fn cmd_doctor(wiki_path: &str) -> Value {
    let root = PathBuf::from(wiki_path);
    if !root.exists() { return response::error("wiki not found", "WikiNotFound", None, &[]); }
    let mut issues = 0i32;
    let mut checks = vec![];
    let mut add = |name: &str, ok: bool, detail: &str| { checks.push(json!({"check":name,"ok":ok,"detail":detail})); if !ok { issues += 1; } };
    let xu = root.join(".xu");
    add("raws_dir", root.join("raws").is_dir(), &root.join("raws").to_string_lossy());
    add("xu_dir", xu.is_dir(), &xu.to_string_lossy());
    add("config_yaml", xu.join("config.yaml").exists(), ".xu/config.yaml");
    let sz = xu.join("wiki.db").metadata().map(|m| m.len()).unwrap_or(0);
    add("wiki_db", sz > 0, &format!("{sz} bytes"));
    add("state_json", xu.join("state.json").exists(), ".xu/state.json");
    if issues == 0 { response::success(json!({"checks":checks,"issues":0,"wiki":wiki_path}), "filesystem: all passed") }
    else { response::warning(json!({"checks":checks,"issues":issues,"wiki":wiki_path}), &format!("{issues} issue(s)")) }
}

// ---- uninstall ----

pub fn cmd_uninstall_plan(preserve_config: bool, keep_pip: bool) -> Value {
    response::success(json!({"mode":"dry-run","pip_uninstall":!keep_pip,"purge_config":!preserve_config,"purge_wikis":false,"note":"wiki data NEVER deleted"}), "dry-run plan")
}

pub fn cmd_uninstall_execute(preserve_config: bool, keep_pip: bool) -> Value {
    let mut actions = vec![];
    if !keep_pip {
        let ok = std::process::Command::new("pip").args(["uninstall","xu-wiki","-y"]).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).status().map(|s| s.success()).unwrap_or(false);
        actions.push(json!({"action":"pip_uninstall","ok":ok}));
    }
    if !preserve_config {
        if let Ok(home) = std::env::var("HOME") {
            let d = PathBuf::from(home).join(".xu-wiki");
            if d.exists() { let ok = fs::remove_dir_all(&d).is_ok(); actions.push(json!({"action":"remove_config","ok":ok})); }
        }
    }
    actions.push(json!({"action":"wikis","note":"ALL wiki data preserved","ok":true}));
    response::success(json!({"mode":"execute","actions":actions,"wikis_preserved":true}), "uninstall complete")
}

// ---- ingest helpers ----

pub fn validate_body_format(body: &str, content_type: &str) -> Option<String> {
    if content_type == "article" { return None; }
    if content_type != "table" && content_type != "gallery" { return Some(format!("unknown content_type: {content_type}")); }
    if body.trim().is_empty() { return None; }
    let parsed: Result<serde_yaml::Value, _> = serde_yaml::from_str(body);
    match parsed {
        Ok(serde_yaml::Value::Sequence(seq)) => {
            for (i, item) in seq.iter().enumerate() {
                if !item.is_mapping() { return Some(format!("item {i} is not a dict")); }
                if content_type == "gallery" && matches!(item, serde_yaml::Value::Mapping(ref m) if !m.contains_key(&serde_yaml::Value::String("filename".into()))) {
                    return Some(format!("gallery item {i} missing 'filename' field"));
                }
            }
            None
        }
        Ok(_) => Some(format!("{content_type} requires YAML list")),
        Err(_) => Some("YAML parse failed".into()),
    }
}

pub fn strip_frontmatter(text: &str) -> String {
    if text.starts_with("---") { if let Some(end) = text[3..].find("\n---") { return text[3+end+4..].trim_start_matches('\n').to_string(); } }
    text.to_string()
}

pub fn parse_pending_header(text: &str) -> (std::collections::HashMap<String, String>, String) {
    let mut meta = std::collections::HashMap::new();
    if text.starts_with("<!-- xu-pending") { if let Some(end) = text.find("-->") {
        for tok in text[15..end].trim().split_whitespace() { if let Some(eq) = tok.find('=') { meta.insert(tok[..eq].to_string(), tok[eq+1..].to_string()); } }
        return (meta, text[end+3..].trim_start_matches('\n').to_string());
    }}
    (meta, text.to_string())
}

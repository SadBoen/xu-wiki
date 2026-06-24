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

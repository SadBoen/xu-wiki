//! Doctor: filesystem-level wiki health checks (no SQLite).

use std::fs;
use std::path::PathBuf;

use crate::response;
use serde_json::{json, Value};

/// Run filesystem integrity checks on a wiki directory.
pub fn cmd_doctor(wiki_path: &str) -> Value {
    let root = PathBuf::from(wiki_path);
    if !root.exists() {
        return response::error(
            &format!("wiki path does not exist: {wiki_path}"),
            "WikiNotFound", None, &[],
        );
    }

    let mut checks: Vec<Value> = vec![];
    let mut issues = 0u32;

    let raws = root.join("raws");
    let raws_ok = raws.is_dir();
    checks.push(json!({"check":"raws_dir","ok":raws_ok,"detail":raws.to_string_lossy()}));
    if !raws_ok { issues += 1; }

    let xu = root.join(".xu");
    let xu_ok = xu.is_dir();
    checks.push(json!({"check":"xu_dir","ok":xu_ok,"detail":xu.to_string_lossy()}));
    if !xu_ok { issues += 1; }

    let config = xu.join("config.yaml");
    let cfg_ok = config.exists();
    checks.push(json!({"check":"config_yaml","ok":cfg_ok}));
    if !cfg_ok { issues += 1; }

    let db = xu.join("wiki.db");
    let db_exists = db.exists();
    let db_size = if db_exists { db.metadata().map(|m| m.len()).unwrap_or(0) } else { 0 };
    checks.push(json!({"check":"wiki_db","ok":db_exists && db_size>0,"detail":format!("{db_size} bytes")}));
    if !db_exists || db_size == 0 { issues += 1; }

    let state = xu.join("state.json");
    let state_ok = state.exists();
    checks.push(json!({"check":"state_json","ok":state_ok}));
    if !state_ok { issues += 1; }

    if issues == 0 {
        response::success(
            json!({"checks":checks,"issues":0,"wiki":wiki_path}),
            "wiki filesystem integrity: all checks passed",
        )
    } else {
        response::warning(
            json!({"checks":checks,"issues":issues,"wiki":wiki_path}),
            &format!("wiki filesystem integrity: {issues} issue(s) found"),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::paths::gen_uid;

    #[test]
    fn test_doctor_missing_wiki() {
        let r = cmd_doctor("/tmp/does-not-exist-xu-test");
        assert_eq!(r["status"], "error");
    }

    #[test]
    fn test_doctor_empty_dir_finds_issues() {
        let tmp = std::env::temp_dir().join(format!("xu-doctor-{}", gen_uid()));
        fs::create_dir_all(&tmp).unwrap();
        let r = cmd_doctor(&tmp.to_string_lossy());
        let _ = fs::remove_dir_all(&tmp);
        assert_eq!(r["status"], "warning");
        assert!(r["data"]["issues"].as_u64().unwrap() > 0);
    }
}

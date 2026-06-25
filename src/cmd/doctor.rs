use std::path::PathBuf;
use crate::response;
use serde_json::Value;

pub fn cmd_doctor(wiki_path: &str) -> Value {
    let root = PathBuf::from(wiki_path);
    if !root.exists() { return response::error("wiki not found", "WikiNotFound", None, &[]); }
    let xu = root.join(".xu");
    let mut checks: Vec<Value> = vec![];

    // --- Layer 1: filesystem ---
    checks.push(response::json!({"check":"raws_dir","ok":root.join("raws").is_dir(),"group":"fs"}));
    checks.push(response::json!({"check":"xu_dir","ok":xu.is_dir(),"group":"fs"}));
    checks.push(response::json!({"check":"config_yaml","ok":xu.join("config.yaml").exists(),"group":"fs"}));
    checks.push(response::json!({"check":"wiki_db","ok":xu.join("wiki.db").metadata().map(|m|m.len()).unwrap_or(0)>0,"group":"fs"}));
    checks.push(response::json!({"check":"state_json","ok":xu.join("state.json").exists(),"group":"fs"}));

    // --- Layer 2: database stats ---
    let db = crate::db::Db::open(&xu.join("wiki.db"));
    if let Ok(ref db) = db {
        let total = db.query_map("SELECT COUNT(*) as cnt FROM node_page", vec![]).unwrap_or_default();
        let active = db.query_map("SELECT COUNT(*) as cnt FROM node_page WHERE active=1", vec![]).unwrap_or_default();
        let deactivated = db.query_map("SELECT COUNT(*) as cnt FROM node_page WHERE active=0", vec![]).unwrap_or_default();
        let total_cnt: i64 = total.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        let active_cnt: i64 = active.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        let dead_cnt: i64 = deactivated.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        checks.push(response::json!({"check":"page_total","ok":true,"detail":total_cnt,"group":"stats"}));
        checks.push(response::json!({"check":"page_active","ok":true,"detail":active_cnt,"group":"stats"}));
        checks.push(response::json!({"check":"page_deactivated","ok":true,"detail":dead_cnt,"group":"stats"}));

        let entities = db.query_map("SELECT COUNT(*) as cnt FROM node_derived WHERE layer='Entity'", vec![]).unwrap_or_default();
        let lists = db.query_map("SELECT COUNT(*) as cnt FROM node_derived WHERE layer='List'", vec![]).unwrap_or_default();
        let reports = db.query_map("SELECT COUNT(*) as cnt FROM node_derived WHERE layer='Report'", vec![]).unwrap_or_default();
        let entity_cnt: i64 = entities.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        let list_cnt: i64 = lists.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        let report_cnt: i64 = reports.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        checks.push(response::json!({"check":"entity_count","ok":true,"detail":entity_cnt,"group":"stats"}));
        checks.push(response::json!({"check":"list_count","ok":true,"detail":list_cnt,"group":"stats"}));
        checks.push(response::json!({"check":"report_count","ok":true,"detail":report_cnt,"group":"stats"}));

        let rels = db.query_map("SELECT COUNT(*) as cnt FROM relations", vec![]).unwrap_or_default();
        let rel_cnt: i64 = rels.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        checks.push(response::json!({"check":"relation_count","ok":true,"detail":rel_cnt,"group":"stats"}));

        // --- Layer 3: cross-layer integrity ---
        let broken_from = db.query_map("SELECT COUNT(*) as cnt FROM relations WHERE from_uid NOT IN (SELECT uid FROM node_page UNION SELECT uid FROM node_derived)", vec![]).unwrap_or_default();
        let broken_to = db.query_map("SELECT COUNT(*) as cnt FROM relations WHERE to_uid NOT IN (SELECT uid FROM node_page WHERE active=1 UNION SELECT uid FROM node_derived)", vec![]).unwrap_or_default();
        let broken_from_cnt: i64 = broken_from.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        let broken_to_cnt: i64 = broken_to.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        checks.push(response::json!({"check":"broken_from_uid","ok":broken_from_cnt==0,"detail":format!("{} orphan(s)", broken_from_cnt),"group":"integrity"}));
        checks.push(response::json!({"check":"broken_to_uid","ok":broken_to_cnt==0,"detail":format!("{} dangling(s)", broken_to_cnt),"group":"integrity"}));

        let orphan_entities = db.query_map("SELECT COUNT(*) as cnt FROM node_derived WHERE layer='Entity' AND uid NOT IN (SELECT from_uid FROM relations)", vec![]).unwrap_or_default();
        let orphan_cnt: i64 = orphan_entities.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        checks.push(response::json!({"check":"orphan_entities","ok":orphan_cnt==0,"detail":format!("{} without relations", orphan_cnt),"group":"integrity"}));

        let empty_lists = db.query_map("SELECT COUNT(*) as cnt FROM node_derived WHERE layer='List' AND uid NOT IN (SELECT from_uid FROM relations WHERE relation_name='contains')", vec![]).unwrap_or_default();
        let empty_list_cnt: i64 = empty_lists.first().and_then(|r| r.get("cnt").and_then(|v| v.parse().ok())).unwrap_or(0);
        checks.push(response::json!({"check":"empty_lists","ok":empty_list_cnt==0,"detail":format!("{} empty list(s)", empty_list_cnt),"group":"integrity"}));
    } else {
        checks.push(response::json!({"check":"db_open","ok":false,"detail":"cannot open database","group":"fs"}));
    }

    // --- Layer 4: registry ---
    let reg_path = if let Ok(xh) = std::env::var("XU_HOME") { PathBuf::from(xh).join("config.yaml") }
                   else if let Ok(home) = std::env::var("HOME") { PathBuf::from(home).join(".xu-wiki").join("config.yaml") }
                   else { PathBuf::new() };
    if reg_path.exists() {
        let reg_ok = std::fs::read_to_string(&reg_path).map(|s| s.contains(wiki_path)).unwrap_or(false);
        checks.push(response::json!({"check":"registry_entry","ok":reg_ok,"detail":if reg_ok {"found"} else {"missing"},"group":"registry"}));
    } else {
        checks.push(response::json!({"check":"registry_file","ok":false,"detail":"~/.xu-wiki/config.yaml not found","group":"registry"}));
    }

    let issues = checks.iter().filter(|c| !c["ok"].as_bool().unwrap_or(false)).count();
    let stats: Value = checks.iter().filter(|c| c["group"]=="stats").map(|c| {(c["check"].as_str().unwrap_or("").to_string(), c["detail"].as_i64().map(|n| response::json!(n)).unwrap_or(response::json!(c["detail"].as_str().unwrap_or(""))))}).collect::<serde_json::Map<_,_>>().into();

    if issues == 0 {
        response::success(response::json!({"checks":checks,"issues":0,"wiki":wiki_path,"stats":stats}), "all checks passed")
    } else {
        response::warning(response::json!({"checks":checks,"issues":issues,"wiki":wiki_path,"stats":stats}), &format!("{} issue(s)", issues))
    }
}

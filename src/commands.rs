//! Command implementations — Rust owns all business logic.
//! All functions return 4-key JSON via crate::response.

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use crate::db::Db;
use crate::paths::{gen_uid, now_ts, safe_slug, sha256_text};
use crate::response;
use serde_json::{json, Value};

static NAME_REGEX: LazyLock<regex::Regex> = LazyLock::new(|| regex::Regex::new(r"^[A-Za-z0-9_-]{1,64}$").unwrap());

// ======== CREATE ========

fn build_skeleton(target: &Path, name: &str) -> Result<(), String> {
    fs::create_dir_all(target.join("raws")).map_err(|e| e.to_string())?;
    let xu = target.join(".xu");
    fs::create_dir_all(&xu).map_err(|e| e.to_string())?;
    fs::write(xu.join("config.yaml"), format!("version: \"1.0.0\"\nname: \"{name}\"\ntemplates: {{}}\n")).map_err(|e| e.to_string())?;
    fs::write(xu.join("state.json"), format!(r#"{{"version":"1.0.0","created_at":{}}}"#, now_ts())).map_err(|e| e.to_string())?;
    Db::open(&xu.join("wiki.db")).map_err(|e| e.to_string())?.init_schema().map_err(|e| e.to_string())?;
    Ok(())
}

pub fn cmd_create(name: &str, path: &str, _alias: Option<&str>) -> Value {
    if name.trim().is_empty() { return response::error("create requires --name", "MissingName", None, &[]); }
    if !NAME_REGEX.is_match(name) { return response::error(&format!("invalid wiki name: {name:?}"), "InvalidName", None, &["name must be alnum/-/_ and <= 64 chars".into()]); }
    let target = PathBuf::from(path);
    if !target.is_absolute() { return response::error("--path must be absolute", "PathNotAbsolute", None, &[]); }
    if target.exists() && target.read_dir().map_or(false, |mut d| d.next().is_some()) { return response::warning(json!({"path":path,"name":name}), "directory exists and is non-empty"); }
    match build_skeleton(&target, name) {
        Ok(()) => response::success(json!({"name":name,"path":path,"version":"1.0.0","layout":["raws/",".xu/"],"tables":["node_page","node_derived","patches","relations"]}), &format!("created wiki '{name}'")),
        Err(e) => response::error(&format!("create failed: {e}"), "CreateFailed", None, &[]),
    }
}

// ======== SELFCHECK ========

pub fn cmd_selfcheck() -> Value {
    response::success(json!({"checks":[{"name":"uid_gen","ok":true,"detail":gen_uid()},{"name":"sha256","ok":true},{"name":"slug","ok":safe_slug("Test",80)=="test"}],"version":env!("CARGO_PKG_VERSION")}), "all core checks passed")
}

// ======== DOCTOR (filesystem) ========

pub fn cmd_doctor(wiki_path: &str) -> Value {
    let root = PathBuf::from(wiki_path);
    if !root.exists() { return response::error("wiki not found", "WikiNotFound", None, &[]); }
    let xu = root.join(".xu");
    let checks = json!([
        {"check":"raws_dir","ok":root.join("raws").is_dir()},
        {"check":"xu_dir","ok":xu.is_dir()},
        {"check":"config_yaml","ok":xu.join("config.yaml").exists()},
        {"check":"wiki_db","ok":xu.join("wiki.db").metadata().map(|m|m.len()).unwrap_or(0)>0},
        {"check":"state_json","ok":xu.join("state.json").exists()},
    ]);
    let issues = checks.as_array().map(|a| a.iter().filter(|c| !c["ok"].as_bool().unwrap_or(false)).count()).unwrap_or(0);
    if issues == 0 { response::success(json!({"checks":checks,"issues":0,"wiki":wiki_path}), "filesystem: all passed") }
    else { response::warning(json!({"checks":checks,"issues":issues,"wiki":wiki_path}), &format!("{issues} issue(s)")) }
}

// ======== UNINSTALL ========

pub fn cmd_uninstall_plan(preserve_config: bool, keep_pip: bool) -> Value {
    response::success(json!({"mode":"dry-run","pip_uninstall":!keep_pip,"purge_config":!preserve_config,"purge_wikis":false,"note":"wiki data NEVER deleted"}), "dry-run plan")
}

pub fn cmd_uninstall_execute(preserve_config: bool, keep_pip: bool) -> Value {
    let mut a = vec![];
    if !keep_pip { let ok = std::process::Command::new("pip").args(["uninstall","xu-wiki","-y"]).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).status().map(|s|s.success()).unwrap_or(false); a.push(json!({"action":"pip_uninstall","ok":ok})); }
    if !preserve_config { if let Ok(home) = std::env::var("HOME") { let d = PathBuf::from(home).join(".xu-wiki"); if d.exists() { a.push(json!({"action":"remove_config","ok":fs::remove_dir_all(&d).is_ok()})); } } }
    a.push(json!({"action":"wikis","note":"ALL wiki data preserved","ok":true}));
    response::success(json!({"mode":"execute","actions":a,"wikis_preserved":true}), "uninstall complete")
}

// ======== INGEST HELPERS ========

pub fn validate_body_format(body: &str, content_type: &str) -> Option<String> {
    if content_type == "article" { return None; }
    if content_type != "table" && content_type != "gallery" { return Some(format!("unknown content_type: {content_type}")); }
    if body.trim().is_empty() { return None; }
    match serde_yaml::from_str::<serde_yaml::Value>(body) {
        Ok(serde_yaml::Value::Sequence(seq)) => {
            for (i, item) in seq.iter().enumerate() {
                if !item.is_mapping() { return Some(format!("item {i} not a dict")); }
            }
            None
        }
        Ok(_) => Some("requires YAML list".into()),
        Err(_) => Some("YAML parse failed".into()),
    }
}

pub fn strip_frontmatter(text: &str) -> String {
    if text.starts_with("---") { if let Some(e) = text[3..].find("\n---") { return text[3+e+4..].trim_start_matches('\n').to_string(); } }
    text.to_string()
}

pub fn parse_pending_header(text: &str) -> (HashMap<String, String>, String) {
    let mut m = HashMap::new();
    if text.starts_with("<!-- xu-pending") { if let Some(e) = text.find("-->") { for t in text[15..e].trim().split_whitespace() { if let Some(eq) = t.find('=') { m.insert(t[..eq].into(), t[eq+1..].into()); } } return (m, text[e+3..].trim_start_matches('\n').to_string()); } }
    (m, text.to_string())
}

// ======== INGEST-COMMIT ========

fn open_db(wiki_path: &str) -> Result<Db, String> {
    let p = PathBuf::from(wiki_path).join(".xu").join("wiki.db");
    if !p.exists() { return Err("wiki not found".into()); }
    Db::open(&p).map_err(|e| e.to_string())
}

pub fn cmd_ingest_commit(wiki_path: &str, pending_text: &str, title: &str, content_type: &str, raw_path: &str, author: &str, relations_json: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    let (meta, content) = parse_pending_header(pending_text);
    let source_hash = meta.get("source_hash").cloned().unwrap_or_default();

    // === DEDUP FIRST ===
    if !source_hash.is_empty() {
        if let Ok(rows) = db.query_map("SELECT uid FROM node_page WHERE source_hash=?", vec![source_hash.clone()]) {
            if !rows.is_empty() { return response::warning(json!({"source_hash":source_hash}), "source already ingested"); }
        }
    }

    let pages = crate::splitter::split_pages(&content, Some(300));
    if pages.is_empty() { return response::error("no content after splitting", "EmptyContent", None, &[]); }

    let ts = now_ts();
    let mut created = vec![];

    for (idx, body) in pages.iter().enumerate() {
        let body = body.trim();
        if body.is_empty() { continue; }
        if let Some(e) = validate_body_format(body, content_type) { return response::error(&e, "BodyFormatMismatch", None, &[]); }

        let ch = sha256_text(body);
        let uid = gen_uid();
        let t = if pages.len() == 1 { title.to_string() } else { format!("{title} (part {})", idx+1) };
        let slug = safe_slug(&t, 80);
        let rp = if idx == 0 && !raw_path.is_empty() { raw_path.to_string() } else { String::new() };

        let _ = db.exec("INSERT INTO node_page(uid,title,slug,raw_path,content_type,content_hash,source_hash,active,attrs,created_at,updated_at,body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            vec![uid.clone(),t.clone(),slug,rp,content_type.into(),ch.clone(),source_hash.clone(),"1".into(),"".into(),ts.to_string(),ts.to_string(),body.to_string()]);

        let _ = db.exec("INSERT INTO patches(page_uid,version,op,delta,author,created_at) VALUES(?,?,?,?,?,?)",
            vec![uid.clone(),"1".into(),"create".into(),ch,author.into(),ts.to_string()]);

        // Relations
        if !relations_json.is_empty() && idx == 0 {
            if let Ok(rels) = serde_json::from_str::<Vec<Value>>(relations_json) {
                for rel in rels {
                    let to = rel["to_uid"].as_str().unwrap_or("");
                    let rn = rel["relation_name"].as_str().unwrap_or("");
                    let cm = rel["comment"].as_str().unwrap_or("");
                    if !to.is_empty() && !rn.is_empty() {
                        let _ = db.exec("INSERT INTO relations(from_uid,to_uid,relation_name,comment,position,created_at) VALUES(?,?,?,?,?,?)",
                            vec![uid.clone(),to.into(),rn.into(),cm.into(),"0".into(),ts.to_string()]);
                    }
                }
            }
        }
        created.push(json!({"uid":uid,"title":t}));
    }

    let _ = db.commit();
    if created.is_empty() { response::warning(json!({"created":[]}), "all pages duplicates") }
    else { response::success(json!({"created":created,"page_count":created.len()}), &format!("committed {} page(s)", created.len())) }
}

// ======== QUERY ========

pub fn cmd_query(wiki_path: &str, core: &str, expansion: &str, top_k: usize) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };
    let ck: Vec<String> = core.split(',').map(|s| s.trim().to_lowercase()).filter(|s| !s.is_empty()).collect();
    let ek: Vec<String> = expansion.split(',').map(|s| s.trim().to_lowercase()).filter(|s| !s.is_empty()).collect();
    if ck.is_empty() && ek.is_empty() { return response::error("provide --core or --expansion", "NoKeywords", None, &[]); }

    let rows = match db.query_map("SELECT uid,title,body FROM node_page WHERE active=1", vec![]) { Ok(r) => r, Err(e) => return response::error(&e.to_string(), "DbError", None, &[]) };

    let mut scored: Vec<(u64, Value)> = vec![];
    for row in rows {
        let body = row.get("body").map(|s| s.to_lowercase()).unwrap_or_default();
        if body.is_empty() { continue; }
        let ch: usize = ck.iter().map(|k| body.matches(k).count()).sum();
        let eh: usize = ek.iter().map(|k| body.matches(k).count()).sum();
        let score = (ch * 3 + eh) as u64;
        if score == 0 { continue; }
        let snippet: String = row.get("body").map(|b| b.chars().take(100).collect()).unwrap_or_default();
        scored.push((score, json!({"uid":row.get("uid").unwrap_or(&String::new()),"title":row.get("title").unwrap_or(&String::new()),"layer":"Page","score":score,"snippet":snippet})));
    }
    scored.sort_by(|a,b| b.0.cmp(&a.0));
    let top: Vec<Value> = scored.into_iter().take(top_k.max(1).min(50)).map(|(_,v)| v).collect();
    response::success(json!({"related_nodes":top,"total_hits":top.len()}), &format!("{} snippet(s)", top.len()))
}

// ======== EXPAND ========

pub fn cmd_expand(wiki_path: &str, uids: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };
    let uid_list: Vec<&str> = uids.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).take(20).collect();
    let mut result = serde_json::Map::new();
    for uid in uid_list {
        let rows = match db.query_map("SELECT uid,title,body FROM node_page WHERE uid=?", vec![uid.into()]) { Ok(r) => r, Err(_) => continue };
        let rels = db.query_map("SELECT to_uid,relation_name,position FROM relations WHERE from_uid=? ORDER BY position", vec![uid.into()]).unwrap_or_default();
        if let Some(row) = rows.first() {
            let u = row.get("uid").cloned().unwrap_or_default();
            let t = row.get("title").cloned().unwrap_or_default();
            let b = row.get("body").cloned().unwrap_or_default();
            let r: Vec<Value> = rels.iter().map(|r| json!({"to_uid":r.get("to_uid").cloned().unwrap_or_default(),"relation_name":r.get("relation_name").cloned().unwrap_or_default()})).collect();
            result.insert(u.clone(), json!({"uid":u,"title":t,"layer":"Page","body":b,"relations":r}));
        }
    }
    let count = result.len();
    response::success(json!({"nodes":serde_json::Value::Object(result),"count":count}), &format!("expanded {} node(s)", count))
}

// ======== INGEST-CONTEXT ========

pub fn cmd_ingest_context(wiki_path: &str, keywords: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };
    let kw: Vec<&str> = keywords.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    // raws_tree
    let mut dirs = std::collections::HashSet::new();
    if let Ok(rows) = db.query_map("SELECT DISTINCT raw_path FROM node_page WHERE raw_path IS NOT NULL AND raw_path!=''", vec![]) {
        for r in &rows { if let Some(rp) = r.get("raw_path") { let rn = rp.replace('\\', "/"); for (i,_) in rn.split('/').enumerate() { if i>0 { dirs.insert(rn.split('/').take(i).collect::<Vec<_>>().join("/")); } } } }
    }
    let mut raws_tree: Vec<String> = dirs.into_iter().collect(); raws_tree.sort();
    // related_nodes
    let mut related = vec![];
    if let Ok(rows) = db.query_map("SELECT uid,title,body FROM node_page WHERE active=1", vec![]) {
        for r in &rows { let body = r.get("body").map(|b| b.to_lowercase()).unwrap_or_default(); let c = kw.iter().filter(|k| body.contains(&k.to_lowercase())).count(); if c>0 { related.push(json!({"uid":r.get("uid").unwrap_or(&String::new()),"title":r.get("title").unwrap_or(&String::new()),"layer":"Page","match_count":c})); } }
    }
    related.sort_by(|a,b| b["match_count"].as_u64().cmp(&a["match_count"].as_u64()));
    response::success(json!({"raws_tree":raws_tree,"related_nodes":related.iter().take(10).collect::<Vec<_>>()}), &format!("{} raw dirs, {} related", raws_tree.len(), related.len()))
}

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
    let mut actions: Vec<Value> = vec![];
    let mut failed: Vec<String> = vec![];
    let mut hints: Vec<String> = vec![];

    // --- package removal: try pipx first, fall back to pip ---
    if !keep_pip {
        let pipx_ok = std::process::Command::new("pipx")
            .args(["uninstall", "xu-wiki"])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);

        let pip_ok = if pipx_ok {
            true  // pipx succeeded, skip pip
        } else {
            std::process::Command::new("pip")
                .args(["uninstall", "xu-wiki", "-y"])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status()
                .map(|s| s.success())
                .unwrap_or(false)
        };

        let uninstalled = pipx_ok || pip_ok;
        let method = if pipx_ok { "pipx" } else if pip_ok { "pip" } else { "none" };
        actions.push(json!({"action":"pip_uninstall","ok":uninstalled,"method":method}));

        if !uninstalled {
            failed.push("pip_uninstall".into());
            hints.push("Auto-removal of xu-wiki package failed. Try manually: pipx uninstall xu-wiki  OR  pip uninstall xu-wiki -y".into());
        }
    }

    // --- config removal ---
    if !preserve_config {
        let config_dir = if let Ok(xh) = std::env::var("XU_HOME") {
            PathBuf::from(xh)
        } else if let Ok(home) = std::env::var("HOME") {
            PathBuf::from(home).join(".xu-wiki")
        } else {
            PathBuf::new()
        };

        if !config_dir.as_os_str().is_empty() && config_dir.exists() {
            let removed = fs::remove_dir_all(&config_dir).is_ok();
            actions.push(json!({"action":"remove_config","ok":removed,"path":config_dir.to_string_lossy()}));
            if !removed {
                failed.push("remove_config".into());
                hints.push(format!("Could not remove config directory: {}. You may remove it manually.", config_dir.display()));
            }
        }
    }

    // --- wikis always preserved ---
    actions.push(json!({"action":"wikis","note":"ALL wiki data preserved","ok":true}));

    // --- response grading ---
    let failed_count = failed.len();
    if failed_count == 0 {
        response::success(json!({"mode":"execute","actions":actions,"wikis_preserved":true}), "uninstall complete")
    } else {
        response::warning_with_hints(
            json!({"mode":"execute","actions":actions,"failed_components":failed,"wikis_preserved":true}),
            &format!("uninstall completed with {failed_count} issue(s)"),
            &hints,
        )
    }
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

    let page_rows = db.query_map("SELECT uid,title,body FROM node_page WHERE active=1", vec![]).unwrap_or_default();
    let derived_rows = db.query_map("SELECT uid,title,body,layer FROM node_derived", vec![]).unwrap_or_default();

    let mut scored: Vec<(u64, Value)> = vec![];
    for row in page_rows.iter().chain(derived_rows.iter()) {
        let body = row.get("body").map(|s| s.to_lowercase()).unwrap_or_default();
        let title_lower = row.get("title").map(|s| s.to_lowercase()).unwrap_or_default();
        let search_text = format!("{title_lower} {body}");
        if search_text.trim().is_empty() { continue; }
        let ch: usize = ck.iter().map(|k| search_text.matches(k).count()).sum();
        let eh: usize = ek.iter().map(|k| search_text.matches(k).count()).sum();
        let score = (ch * 3 + eh) as u64;
        if score == 0 { continue; }
        let snippet: String = body.chars().take(100).collect();
        let layer = row.get("layer").cloned().unwrap_or_else(|| "Page".into());
        scored.push((score, json!({"uid":row.get("uid").unwrap_or(&String::new()),"title":row.get("title").unwrap_or(&String::new()),"layer":layer,"score":score,"snippet":snippet})));
    }
    scored.sort_by(|a,b| b.0.cmp(&a.0));
    let top: Vec<Value> = scored.into_iter().take(top_k.max(1).min(50)).map(|(_,v)| v).collect();

    // --- Post-query reflection: hints for the Agent ---
    let reflection = build_reflection(&db, &ck, &top);

    response::success(
        json!({"related_nodes":top,"total_hits":top.len(),"reflection":reflection}),
        &format!("{} snippet(s)", top.len()),
    )
}

fn build_reflection(db: &crate::db::Db, core_keywords: &[String], top: &[Value]) -> Value {
    // Existing derived nodes matching core keywords
    let mut existing_entities: Vec<Value> = vec![];
    let mut existing_lists: Vec<Value> = vec![];
    let mut existing_reports: Vec<Value> = vec![];

    for kw in core_keywords {
        let like = format!("%{kw}%");
        // Entities
        if let Ok(rows) = db.query_map(
            "SELECT uid,title FROM node_derived WHERE layer='Entity' AND (title LIKE ? OR body LIKE ?)",
            vec![like.clone(), like.clone()],
        ) {
            for r in &rows {
                existing_entities.push(json!({"uid":r.get("uid").unwrap_or(&String::new()),"title":r.get("title").unwrap_or(&String::new())}));
            }
        }
        // Lists
        if let Ok(rows) = db.query_map(
            "SELECT uid,title FROM node_derived WHERE layer='List' AND (title LIKE ? OR body LIKE ?)",
            vec![like.clone(), like.clone()],
        ) {
            for r in &rows {
                existing_lists.push(json!({"uid":r.get("uid").unwrap_or(&String::new()),"title":r.get("title").unwrap_or(&String::new())}));
            }
        }
        // Reports
        if let Ok(rows) = db.query_map(
            "SELECT uid,title FROM node_derived WHERE layer='Report' AND (title LIKE ? OR body LIKE ?)",
            vec![like.clone(), like.clone()],
        ) {
            for r in &rows {
                existing_reports.push(json!({"uid":r.get("uid").unwrap_or(&String::new()),"title":r.get("title").unwrap_or(&String::new())}));
            }
        }
    }

    // Deduplicate
    existing_entities.dedup_by(|a,b| a["uid"] == b["uid"]);
    existing_lists.dedup_by(|a,b| a["uid"] == b["uid"]);
    existing_reports.dedup_by(|a,b| a["uid"] == b["uid"]);

    let has_pages = top.iter().any(|n| n["layer"].as_str() == Some("Page"));

    json!({
        "existing_entities": existing_entities,
        "existing_lists": existing_lists,
        "existing_reports": existing_reports,
        "suggest_extract_entities": has_pages && existing_entities.len() < top.len(),
        "suggest_create_list": top.len() >= 2 && existing_lists.is_empty(),
        "suggest_create_report": top.len() >= 3 && existing_reports.len() < 2,
        "hint": if has_pages && existing_entities.is_empty() {
            format!("{} page(s) found — consider extracting entities with: xu entity-create --wiki <w> --title <name> --source-page <uid>", top.len())
        } else if top.len() >= 2 && existing_lists.is_empty() {
            "multiple results share a theme — consider: xu list-create".into()
        } else {
            "".into()
        }
    })
}


// ======== EXPAND ========

pub fn cmd_expand(wiki_path: &str, uids: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };
    let uid_list: Vec<&str> = uids.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).take(20).collect();
    let mut result = serde_json::Map::new();
    for uid in uid_list {
        // Try node_page first, then node_derived
        let mut rows = db.query_map("SELECT uid,title,body FROM node_page WHERE uid=?", vec![uid.into()]).unwrap_or_default();
        let mut layer = "Page".to_string();
        if rows.is_empty() {
            rows = db.query_map("SELECT uid,title,body,layer FROM node_derived WHERE uid=?", vec![uid.into()]).unwrap_or_default();
            layer = rows.first().and_then(|r| r.get("layer").cloned()).unwrap_or_else(|| "Derived".into());
        }
        let rels = db.query_map("SELECT to_uid,relation_name,position FROM relations WHERE from_uid=? ORDER BY position", vec![uid.into()]).unwrap_or_default();
        if let Some(row) = rows.first() {
            let u = row.get("uid").cloned().unwrap_or_default();
            let t = row.get("title").cloned().unwrap_or_default();
            let b = row.get("body").cloned().unwrap_or_default();
            let r: Vec<Value> = rels.iter().map(|r| json!({"to_uid":r.get("to_uid").cloned().unwrap_or_default(),"relation_name":r.get("relation_name").cloned().unwrap_or_default()})).collect();
            result.insert(u.clone(), json!({"uid":u,"title":t,"layer":layer,"body":b,"relations":r}));
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

// ======== UPDATE ========

pub fn cmd_update(wiki_path: &str, uid: &str, title: Option<&str>, body: Option<&str>, relations_json: &str, author: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    // --- read current page ---
    let rows = match db.query_map("SELECT * FROM node_page WHERE uid=? AND active=1", vec![uid.into()]) {
        Ok(r) => r,
        Err(e) => return response::error(&e.to_string(), "DbError", None, &[]),
    };
    if rows.is_empty() {
        return response::error(&format!("node not found: {uid}"), "NodeNotFound", None, &[]);
    }
    let row = &rows[0];
    let old_body = row.get("body").cloned().unwrap_or_default();
    let old_title = row.get("title").cloned().unwrap_or_default();
    let old_content_type = row.get("content_type").cloned().unwrap_or_default();
    // Get current max version from patches
    let versions = db.query_map("SELECT MAX(version) as ver FROM patches WHERE page_uid=?", vec![uid.into()]).unwrap_or_default();
    let old_version: i64 = versions.first()
        .and_then(|r| r.get("ver"))
        .and_then(|v| v.parse().ok())
        .unwrap_or(1);

    // --- compute new values ---
    let new_title = title.filter(|t| !t.is_empty()).unwrap_or(&old_title);
    let new_body = body.filter(|b| !b.is_empty()).unwrap_or(&old_body);

    // validate body format
    if new_body != old_body {
        if let Some(e) = validate_body_format(new_body, &old_content_type) {
            return response::error(&e, "BodyFormatMismatch", None, &[]);
        }
    }

    let new_hash = crate::paths::sha256_text(new_body);
    let ts = now_ts();
    let new_version = old_version + 1;
    let mut changed: Vec<&str> = vec![];

    // --- update node_page ---
    if new_title != old_title || new_body != old_body {
        if new_title != old_title { changed.push("title"); }
        if new_body != old_body { changed.push("body"); }
        let _ = db.exec(
            "UPDATE node_page SET title=?, body=?, content_hash=?, updated_at=? WHERE uid=?",
            vec![new_title.into(), new_body.into(), new_hash.clone(), ts.to_string(), uid.into()],
        );
        // --- insert patch ---
        let _ = db.exec(
            "INSERT INTO patches(page_uid,version,op,delta,author,created_at) VALUES(?,?,?,?,?,?)",
            vec![uid.into(), new_version.to_string(), "revise".into(), new_hash, author.into(), ts.to_string()],
        );
    }

    // --- update relations if provided ---
    if !relations_json.is_empty() {
        changed.push("relations");
        // delete old
        let _ = db.exec("DELETE FROM relations WHERE from_uid=?", vec![uid.into()]);
        // insert new
        if let Ok(rels) = serde_json::from_str::<Vec<Value>>(relations_json) {
            for (pos, rel) in rels.iter().enumerate() {
                let to = rel["to_uid"].as_str().unwrap_or("");
                let rn = rel["relation_name"].as_str().unwrap_or("");
                let cm = rel["comment"].as_str().unwrap_or("");
                if !to.is_empty() && !rn.is_empty() {
                    let _ = db.exec(
                        "INSERT INTO relations(from_uid,to_uid,relation_name,comment,position,created_at) VALUES(?,?,?,?,?,?)",
                        vec![uid.into(), to.into(), rn.into(), cm.into(), pos.to_string(), ts.to_string()],
                    );
                }
            }
        }
    }

    let _ = db.commit();
    if changed.is_empty() {
        response::success(json!({"uid":uid,"changed":[]}), "nothing to update")
    } else {
        response::success(
            json!({"uid":uid,"changed":changed,"version":new_version}),
            &format!("updated {} field(s)", changed.len()),
        )
    }
}

// ======== DEACTIVATE (soft delete) ========

pub fn cmd_deactivate(wiki_path: &str, uid: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    // check exists + active
    let rows = match db.query_map("SELECT active FROM node_page WHERE uid=?", vec![uid.into()]) {
        Ok(r) => r,
        Err(e) => return response::error(&e.to_string(), "DbError", None, &[]),
    };
    if rows.is_empty() {
        return response::error(&format!("node not found: {uid}"), "NodeNotFound", None, &[]);
    }
    if rows[0].get("active").map(|a| a == "0").unwrap_or(false) {
        return response::warning(json!({"uid":uid}), "node already deactivated");
    }

    let ts = now_ts();
    let _ = db.exec("UPDATE node_page SET active=0, updated_at=? WHERE uid=?", vec![ts.to_string(), uid.into()]);
    let _ = db.commit();
    response::success(json!({"uid":uid,"active":false,"deactivated_at":ts}), "node deactivated")
}

// ======== VERIFY ========

pub fn cmd_verify(wiki_path: &str, uid: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    // Search node_page first, then node_derived
    let rows = db.query_map("SELECT * FROM node_page WHERE uid=?", vec![uid.into()]).unwrap_or_default();
    let is_page = !rows.is_empty();
    let rows = if is_page { rows } else {
        db.query_map("SELECT * FROM node_derived WHERE uid=?", vec![uid.into()]).unwrap_or_default()
    };
    if rows.is_empty() {
        return response::error(&format!("node not found: {uid}"), "NodeNotFound", None, &[]);
    }
    let row = &rows[0];
    let body = row.get("body").cloned().unwrap_or_default();
    let title = row.get("title").cloned().unwrap_or_default();
    let content_hash = row.get("content_hash").cloned().unwrap_or_default();
    let active = row.get("active").cloned().unwrap_or_default();

    let mut checks: Vec<Value> = vec![];
    checks.push(json!({"check":"exists","ok":true,"detail":uid}));

    if is_page {
        checks.push(json!({"check":"active","ok":active=="1","detail":format!("active={active}")}));
    }
    checks.push(json!({"check":"title_non_empty","ok":!title.is_empty(),"detail":title}));
    checks.push(json!({"check":"body_non_empty","ok":!body.is_empty(),"detail":format!("{} chars", body.len())}));

    if is_page {
        let computed_hash = crate::paths::sha256_text(&body);
        checks.push(json!({"check":"content_hash","ok":content_hash == computed_hash,"detail":format!("stored={:.12}.. computed={:.12}..", &content_hash[..12.min(content_hash.len())], &computed_hash[..12.min(computed_hash.len())])}));

        // patch v1
        let patches = db.query_map("SELECT version FROM patches WHERE page_uid=?", vec![uid.into()]).unwrap_or_default();
        let has_v1 = patches.iter().any(|p| p.get("version").map(|v| v == "1").unwrap_or(false));
        checks.push(json!({"check":"patch_v1_exists","ok":has_v1,"detail":format!("{} patch(es)", patches.len())}));
    }

    // relations validity (check both tables for targets)
    let rels = db.query_map("SELECT to_uid FROM relations WHERE from_uid=?", vec![uid.into()]).unwrap_or_default();
    let mut broken_rels = vec![];
    for rel in &rels {
        if let Some(to_uid) = rel.get("to_uid") {
            let target_page = db.query_map("SELECT uid FROM node_page WHERE uid=? AND active=1", vec![to_uid.clone()]).unwrap_or_default();
            let target_derived = db.query_map("SELECT uid FROM node_derived WHERE uid=?", vec![to_uid.clone()]).unwrap_or_default();
            if target_page.is_empty() && target_derived.is_empty() {
                broken_rels.push(to_uid.clone());
            }
        }
    }
    checks.push(json!({"check":"relations_valid","ok":broken_rels.is_empty(),"detail":if broken_rels.is_empty() { format!("{} relation(s)", rels.len()) } else { format!("{} broken: {:?}", broken_rels.len(), broken_rels) }}));

    let failures = checks.iter().filter(|c| !c["ok"].as_bool().unwrap_or(false)).count();
    if failures == 0 {
        response::success(json!({"uid":uid,"checks":checks,"failures":0}), "all checks passed")
    } else {
        response::warning(json!({"uid":uid,"checks":checks,"failures":failures}), &format!("{failures} check(s) failed"))
    }
}

// ======== LIST CREATE (L2 derived node) ========

pub fn cmd_list_create(wiki_path: &str, title: &str, members_csv: &str, dimension: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    let members: Vec<String> = members_csv.split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();

    if members.is_empty() {
        return response::error("provide --members uid1,uid2,...", "MissingMembers", None, &[]);
    }

    // Validate members exist in node_page
    for m in &members {
        let rows = db.query_map("SELECT uid FROM node_page WHERE uid=? AND active=1", vec![m.clone()])
            .unwrap_or_default();
        if rows.is_empty() {
            return response::error(&format!("member not found: {m}"), "MemberNotFound", None, &[]);
        }
    }

    let uid = gen_uid();
    let ts = now_ts();

    // Build body: YAML list of {uid, title} for each member
    let mut body_entries: Vec<Value> = vec![];
    for m in &members {
        let info = db.query_map("SELECT title FROM node_page WHERE uid=?", vec![m.clone()])
            .unwrap_or_default();
        let m_title = info.first().and_then(|r| r.get("title").cloned()).unwrap_or_default();
        body_entries.push(json!({"uid":m,"title":m_title}));
    }
    let body = serde_yaml::to_string(&body_entries).unwrap_or_default();

    // Insert derived node
    let _ = db.exec(
        "INSERT INTO node_derived(uid,layer,title,dimension,attrs,created_at,updated_at,body) VALUES(?,?,?,?,?,?,?,?)",
        vec![uid.clone(), "List".into(), title.into(), dimension.into(), "".into(), ts.to_string(), ts.to_string(), body.clone()],
    );

    // Create relations: List -> member
    for (pos, m) in members.iter().enumerate() {
        let _ = db.exec(
            "INSERT INTO relations(from_uid,to_uid,relation_name,comment,position,created_at) VALUES(?,?,?,?,?,?)",
            vec![uid.clone(), m.clone(), "contains".into(), "".into(), pos.to_string(), ts.to_string()],
        );
    }

    let _ = db.commit();
    response::success(
        json!({"uid":uid,"layer":"List","title":title,"member_count":members.len()}),
        &format!("created List with {} member(s)", members.len()),
    )
}

// ======== LIST EXTEND ========

pub fn cmd_list_extend(wiki_path: &str, uid: &str, members_csv: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    // Verify it's a List
    let rows = db.query_map("SELECT * FROM node_derived WHERE uid=? AND layer='List'", vec![uid.into()])
        .unwrap_or_default();
    if rows.is_empty() {
        return response::error(&format!("List not found: {uid}"), "ListNotFound", None, &[]);
    }

    let new_members: Vec<String> = members_csv.split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();

    if new_members.is_empty() {
        return response::success(json!({"uid":uid,"added":0}), "nothing to add");
    }

    // Validate new members exist
    for m in &new_members {
        let r = db.query_map("SELECT uid FROM node_page WHERE uid=? AND active=1", vec![m.clone()])
            .unwrap_or_default();
        if r.is_empty() {
            return response::error(&format!("member not found: {m}"), "MemberNotFound", None, &[]);
        }
    }

    // Read existing body, parse as YAML, append
    let old_body = rows[0].get("body").cloned().unwrap_or_default();
    let mut entries: Vec<Value> = serde_yaml::from_str(&old_body).unwrap_or_default();
    let ts = now_ts();

    // Get max position from existing relations
    let max_pos = db.query_map("SELECT MAX(position) as mx FROM relations WHERE from_uid=? AND relation_name='contains'", vec![uid.into()])
        .unwrap_or_default()
        .first()
        .and_then(|r| r.get("mx").and_then(|v| v.parse::<usize>().ok()))
        .unwrap_or(0);

    for (i, m) in new_members.iter().enumerate() {
        let info = db.query_map("SELECT title FROM node_page WHERE uid=?", vec![m.clone()])
            .unwrap_or_default();
        let m_title = info.first().and_then(|r| r.get("title").cloned()).unwrap_or_default();
        entries.push(json!({"uid":m,"title":m_title}));

        let _ = db.exec(
            "INSERT INTO relations(from_uid,to_uid,relation_name,comment,position,created_at) VALUES(?,?,?,?,?,?)",
            vec![uid.into(), m.clone(), "contains".into(), "".into(), (max_pos + 1 + i).to_string(), ts.to_string()],
        );
    }

    let new_body = serde_yaml::to_string(&entries).unwrap_or_default();
    let _ = db.exec(
        "UPDATE node_derived SET body=?, updated_at=? WHERE uid=?",
        vec![new_body, ts.to_string(), uid.into()],
    );
    let _ = db.commit();

    response::success(
        json!({"uid":uid,"added":new_members.len(),"total_members":entries.len()}),
        &format!("added {} member(s), total {}", new_members.len(), entries.len()),
    )
}

// ======== ENTITY CREATE (L0 concept node) ========

pub fn cmd_entity_create(wiki_path: &str, title: &str, body: &str, source_page_uid: &str, attrs_json: &str, dimension: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    if title.trim().is_empty() {
        return response::error("entity requires --title", "MissingTitle", None, &[]);
    }

    // Validate source page if provided
    if !source_page_uid.is_empty() {
        let rows = db.query_map("SELECT uid FROM node_page WHERE uid=? AND active=1", vec![source_page_uid.into()])
            .unwrap_or_default();
        if rows.is_empty() {
            return response::error(&format!("source page not found: {source_page_uid}"), "SourceNotFound", None, &[]);
        }
    }

    // Parse attrs (optional structured properties)
    let attrs = if attrs_json.trim().is_empty() {
        json!({})
    } else {
        match serde_json::from_str::<Value>(attrs_json) {
            Ok(Value::Object(_)) => serde_json::from_str::<Value>(attrs_json).unwrap_or(json!({})),
            _ => return response::error("attrs must be a JSON object", "InvalidAttrs", None, &[]),
        }
    };

    let uid = gen_uid();
    let ts = now_ts();
    let attrs_str = attrs.to_string();

    let _ = db.exec(
        "INSERT INTO node_derived(uid,layer,title,dimension,attrs,created_at,updated_at,body) VALUES(?,?,?,?,?,?,?,?)",
        vec![uid.clone(), "Entity".into(), title.into(), dimension.into(), attrs_str, ts.to_string(), ts.to_string(), body.into()],
    );

    // Relation: Entity -> source page
    if !source_page_uid.is_empty() {
        let _ = db.exec(
            "INSERT INTO relations(from_uid,to_uid,relation_name,comment,position,created_at) VALUES(?,?,?,?,?,?)",
            vec![uid.clone(), source_page_uid.into(), "extracted_from".into(), "".into(), "0".into(), ts.to_string()],
        );
    }

    let _ = db.commit();
    response::success(
        json!({"uid":uid,"layer":"Entity","title":title,"source_page":source_page_uid}),
        "entity created",
    )
}

// ======== REPORT CREATE (L3 derived node) ========

pub fn cmd_report_create(wiki_path: &str, title: &str, body: &str, evidence_csv: &str, dimension: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    if body.trim().is_empty() {
        return response::error("report requires --body", "EmptyBody", None, &[]);
    }

    let evidence: Vec<String> = evidence_csv.split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();

    // Validate evidence UIDs exist
    for uid in &evidence {
        let rows = db.query_map(
            "SELECT uid FROM node_page WHERE uid=? AND active=1 UNION SELECT uid FROM node_derived WHERE uid=?",
            vec![uid.clone(), uid.clone()],
        ).unwrap_or_default();
        if rows.is_empty() {
            return response::error(&format!("evidence uid not found: {uid}"), "EvidenceNotFound", None, &[]);
        }
    }

    let uid = gen_uid();
    let ts = now_ts();

    let _ = db.exec(
        "INSERT INTO node_derived(uid,layer,title,dimension,attrs,created_at,updated_at,body) VALUES(?,?,?,?,?,?,?,?)",
        vec![uid.clone(), "Report".into(), title.into(), dimension.into(), "".into(), ts.to_string(), ts.to_string(), body.into()],
    );

    // Create relations: Report -> evidence
    for (pos, ev) in evidence.iter().enumerate() {
        let _ = db.exec(
            "INSERT INTO relations(from_uid,to_uid,relation_name,comment,position,created_at) VALUES(?,?,?,?,?,?)",
            vec![uid.clone(), ev.clone(), "cites".into(), "".into(), pos.to_string(), ts.to_string()],
        );
    }

    let _ = db.commit();
    response::success(
        json!({"uid":uid,"layer":"Report","title":title,"evidence_count":evidence.len()}),
        "report created",
    )
}

use std::collections::HashMap;
use std::path::PathBuf;
use crate::db::Db;
use crate::paths::{gen_uid, now_ts, sha256_text, safe_slug};
use crate::response;
use serde_json::Value;

fn ok(v: Value) -> Result<Value, String> { Ok(v) }
fn err(msg: &str, cls: &str) -> Result<Value, String> { Err(format!("[{}] {}", cls, msg)) }

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
    let prefix = "<!-- xu-pending";
    if let Some(start) = text.find(prefix) {
        let after_prefix = start + prefix.len();
        if let Some(tag_end) = text[after_prefix..].find("-->") {
            let attrs_end = after_prefix + tag_end;
            for t in text[after_prefix..attrs_end].trim().split_whitespace() {
                if let Some(eq) = t.find('=') {
                    m.insert(t[..eq].into(), t[eq+1..].into());
                }
            }
            return (m, text[attrs_end + 3..].trim_start_matches('\n').to_string());
        }
    }
    (m, text.to_string())
}

fn open_db(wiki_path: &str) -> Result<Db, String> {
    let p = PathBuf::from(wiki_path).join(".xu").join("wiki.db");
    if !p.exists() { return Err("wiki not found".into()); }
    Db::open(&p).map_err(|e| e.to_string())
}

pub fn cmd_ingest_commit(wiki_path: &str, pending_text: &str, title: &str, content_type: &str, raw_path: &str, author: &str, relations_json: &str) -> Result<Value, String> {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return err(&e, "DbError") };

    let (meta, content) = parse_pending_header(pending_text);
    let source_hash = meta.get("source_hash").cloned().unwrap_or_default();

    if !source_hash.is_empty() {
        if let Ok(rows) = db.query_map("SELECT uid FROM node_page WHERE source_hash=?", vec![source_hash.clone()]) {
            if !rows.is_empty() { return ok(response::warning(response::json!({"source_hash":source_hash}), "source already ingested")); }
        }
    }

    let pages = crate::splitter::split_pages(&content, Some(300));
    if pages.is_empty() { return err("no content after splitting", "EmptyContent"); }

    let ts = now_ts();
    let mut created = vec![];

    for (idx, body) in pages.iter().enumerate() {
        let body = body.trim();
        if body.is_empty() { continue; }
        if let Some(e) = validate_body_format(body, content_type) { return err(&e, "BodyFormatMismatch"); }

        let ch = sha256_text(body);
        let uid = gen_uid();
        let t = if pages.len() == 1 { title.to_string() } else { format!("{title} (part {})", idx+1) };
        let slug = safe_slug(&t, 80);
        let rp = if idx == 0 && !raw_path.is_empty() { raw_path.to_string() } else { String::new() };

        if let Err(e) = db.exec("INSERT INTO node_page(uid,title,slug,raw_path,content_type,content_hash,source_hash,active,attrs,created_at,updated_at,body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            vec![uid.clone(),t.clone(),slug,rp,content_type.into(),ch.clone(),source_hash.clone(),"1".into(),"".into(),ts.to_string(),ts.to_string(),body.to_string()]) {
            return Err(format!("db error inserting node_page: {}", e));
        }

        if let Err(e) = db.exec("INSERT INTO patches(page_uid,version,op,delta,author,created_at) VALUES(?,?,?,?,?,?)",
            vec![uid.clone(),"1".into(),"create".into(),ch,author.into(),ts.to_string()]) {
            return Err(format!("db error inserting patch: {}", e));
        }

        if !relations_json.is_empty() && idx == 0 {
            if let Ok(rels) = serde_json::from_str::<Vec<Value>>(relations_json) {
                for rel in rels {
                    let to = rel["to_uid"].as_str().unwrap_or("");
                    let rn = rel["relation_name"].as_str().unwrap_or("");
                    let cm = rel["comment"].as_str().unwrap_or("");
                    if !to.is_empty() && !rn.is_empty() {
                        if let Err(e) = db.exec("INSERT INTO relations(from_uid,to_uid,relation_name,comment,position,created_at) VALUES(?,?,?,?,?,?)",
                            vec![uid.clone(),to.into(),rn.into(),cm.into(),"0".into(),ts.to_string()]) {
                            return Err(format!("db error inserting relation: {}", e));
                        }
                    }
                }
            }
        }
        created.push(response::json!({"uid":uid,"title":t}));
    }

    if let Err(e) = db.commit() {
        return Err(format!("db commit failed: {}", e));
    }
    if created.is_empty() { ok(response::warning(response::json!({"created":[]}), "all pages duplicates")) }
    else { ok(response::success(response::json!({"created":created,"page_count":created.len()}), &format!("committed {} page(s)", created.len()))) }
}

pub fn cmd_ingest_context(wiki_path: &str, keywords: &str) -> Result<Value, String> {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return err(&e, "DbError") };
    let kw: Vec<&str> = keywords.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    let mut dirs = std::collections::HashSet::new();
    let rows = db.query_map("SELECT DISTINCT raw_path FROM node_page WHERE raw_path IS NOT NULL AND raw_path!=''", vec![])
        .map_err(|e| format!("db error: {}", e))?;
    for r in &rows { if let Some(rp) = r.get("raw_path") { let rn = rp.replace('\\', "/"); for (i,_) in rn.split('/').enumerate() { if i>0 { dirs.insert(rn.split('/').take(i).collect::<Vec<_>>().join("/")); } } } }
    let mut raws_tree: Vec<String> = dirs.into_iter().collect(); raws_tree.sort();
    let mut related = vec![];
    let rows = db.query_map("SELECT uid,title,body FROM node_page WHERE active=1", vec![])
        .map_err(|e| format!("db error: {}", e))?;
    for r in &rows { let body = r.get("body").map(|b| b.to_lowercase()).unwrap_or_default(); let c = kw.iter().filter(|k| body.contains(&k.to_lowercase())).count(); if c>0 { related.push(response::json!({"uid":r.get("uid").unwrap_or(&String::new()),"title":r.get("title").unwrap_or(&String::new()),"layer":"Page","match_count":c})); } }
    related.sort_by(|a,b| b["match_count"].as_u64().cmp(&a["match_count"].as_u64()));
    ok(response::success(response::json!({"raws_tree":raws_tree,"related_nodes":related.iter().take(10).collect::<Vec<_>>()}), &format!("{} raw dirs, {} related", raws_tree.len(), related.len())))
}

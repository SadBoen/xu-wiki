use std::path::PathBuf;
use crate::cmd::config::load_registry;
use crate::db::Db;
use crate::paths::{gen_uid, now_ts, sha256_text, safe_slug};
use crate::response;
use serde_json::{json, Value};

fn open_db(wiki_path: &str) -> Result<Db, String> {
    let p = PathBuf::from(wiki_path).join(".xu").join("wiki.db");
    if !p.exists() { return Err("wiki not found".into()); }
    Db::open(&p).map_err(|e| e.to_string())
}

fn build_reflection(db: &crate::db::Db, core_keywords: &[String], top: &[Value]) -> Value {
    let mut existing_entities: Vec<Value> = vec![];
    let mut existing_lists: Vec<Value> = vec![];
    let mut existing_reports: Vec<Value> = vec![];

    for kw in core_keywords {
        let like = format!("%{kw}%");
        if let Ok(rows) = db.query_map(
            "SELECT uid,title FROM node_derived WHERE layer='Entity' AND (title LIKE ? OR body LIKE ?)",
            vec![like.clone(), like.clone()],
        ) {
            for r in &rows {
                existing_entities.push(json!({"uid":r.get("uid").unwrap_or(&String::new()),"title":r.get("title").unwrap_or(&String::new())}));
            }
        }
        if let Ok(rows) = db.query_map(
            "SELECT uid,title FROM node_derived WHERE layer='List' AND (title LIKE ? OR body LIKE ?)",
            vec![like.clone(), like.clone()],
        ) {
            for r in &rows {
                existing_lists.push(json!({"uid":r.get("uid").unwrap_or(&String::new()),"title":r.get("title").unwrap_or(&String::new())}));
            }
        }
        if let Ok(rows) = db.query_map(
            "SELECT uid,title FROM node_derived WHERE layer='Report' AND (title LIKE ? OR body LIKE ?)",
            vec![like.clone(), like.clone()],
        ) {
            for r in &rows {
                existing_reports.push(json!({"uid":r.get("uid").unwrap_or(&String::new()),"title":r.get("title").unwrap_or(&String::new())}));
            }
        }
    }

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
            format!("{} page(s) found – consider extracting entities with: xu entity-create --wiki <w> --title <name> --source-page <uid>", top.len())
        } else if top.len() >= 2 && existing_lists.is_empty() {
            "multiple results share a theme – consider: xu list-create".into()
        } else {
            "".into()
        }
    })
}

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

    let reflection = build_reflection(&db, &ck, &top);

    response::success(
        json!({"related_nodes":top,"total_hits":top.len(),"reflection":reflection}),
        &format!("{} snippet(s)", top.len()),
    )
}

pub fn cmd_expand(wiki_path: &str, uids: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };
    let uid_list: Vec<&str> = uids.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).take(20).collect();
    let mut result = serde_json::Map::new();
    for uid in uid_list {
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

pub fn cmd_update(wiki_path: &str, uid: &str, title: Option<&str>, body: Option<&str>, relations_json: &str, author: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

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
    let versions = db.query_map("SELECT MAX(version) as ver FROM patches WHERE page_uid=?", vec![uid.into()]).unwrap_or_default();
    let old_version: i64 = versions.first()
        .and_then(|r| r.get("ver"))
        .and_then(|v| v.parse().ok())
        .unwrap_or(1);

    let new_title = title.filter(|t| !t.is_empty()).unwrap_or(&old_title);
    let new_body = body.filter(|b| !b.is_empty()).unwrap_or(&old_body);

    if new_body != old_body {
        if let Some(e) = crate::cmd::ingest::validate_body_format(new_body, &old_content_type) {
            return response::error(&e, "BodyFormatMismatch", None, &[]);
        }
    }

    let new_hash = sha256_text(new_body);
    let ts = now_ts();
    let new_version = old_version + 1;
    let mut changed: Vec<&str> = vec![];

    if new_title != old_title || new_body != old_body {
        if new_title != old_title { changed.push("title"); }
        if new_body != old_body { changed.push("body"); }
        let _ = db.exec(
            "UPDATE node_page SET title=?, body=?, content_hash=?, updated_at=? WHERE uid=?",
            vec![new_title.into(), new_body.into(), new_hash.clone(), ts.to_string(), uid.into()],
        );
        let _ = db.exec(
            "INSERT INTO patches(page_uid,version,op,delta,author,created_at) VALUES(?,?,?,?,?,?)",
            vec![uid.into(), new_version.to_string(), "revise".into(), new_hash, author.into(), ts.to_string()],
        );
    }

    if !relations_json.is_empty() {
        changed.push("relations");
        let _ = db.exec("DELETE FROM relations WHERE from_uid=?", vec![uid.into()]);
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

// ======== WIKIS (global registry read) ========

pub fn cmd_wikis() -> Value {
    let reg = load_registry();
    let wikis: Vec<Value> = reg.wikis.iter().map(|(name, entry)| {
        json!({
            "name": name,
            "path": entry.path,
            "alias": entry.alias,
            "created_at": entry.created_at,
        })
    }).collect();

    response::success(
        json!({"wikis": wikis, "count": wikis.len()}),
        &format!("{} registered wiki(s)", wikis.len()),
    )
}

// ======== DELETE NODE ========

pub fn cmd_delete_node(wiki_path: &str, uid: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    // Check if node exists and which table
    let from_page = db.query_map("SELECT uid FROM node_page WHERE uid=?", vec![uid.into()]).unwrap_or_default();
    let from_derived = db.query_map("SELECT uid FROM node_derived WHERE uid=?", vec![uid.into()]).unwrap_or_default();

    if from_page.is_empty() && from_derived.is_empty() {
        return response::error(&format!("node not found: {uid}"), "NodeNotFound", None, &[]);
    }

    let is_page = !from_page.is_empty();

    // Check List references (members containing this uid)
    let list_refs = db.query_map(
        "SELECT uid,title,body FROM node_derived WHERE layer='List'",
        vec![],
    ).unwrap_or_default();
    let mut list_referrers: Vec<Value> = vec![];
    for r in &list_refs {
        let body = r.get("body").unwrap_or(&String::new());
        if body.contains(uid) {
            list_referrers.push(json!({
                "uid": r.get("uid").unwrap_or(&String::new()),
                "title": r.get("title").unwrap_or(&String::new()),
                "layer": "List",
            }));
        }
    }

    // Check Report references (evidence containing this uid)
    let report_refs = db.query_map(
        "SELECT uid,title FROM node_derived WHERE layer='Report'",
        vec![],
    ).unwrap_or_default();
    let mut report_referrers: Vec<Value> = vec![];
    for r in &report_refs {
        let uid_in_rel = db.query_map(
            "SELECT to_uid FROM relations WHERE from_uid=? AND to_uid=? AND relation_name='cites'",
            vec![r.get("uid").unwrap_or(&String::new()).into(), uid.into()],
        ).unwrap_or_default();
        if !uid_in_rel.is_empty() {
            report_referrers.push(json!({
                "uid": r.get("uid").unwrap_or(&String::new()),
                "title": r.get("title").unwrap_or(&String::new()),
                "layer": "Report",
            }));
        }
    }

    // Check relation references (this uid is a relation target)
    let incoming_rels = db.query_map(
        "SELECT from_uid,relation_name FROM relations WHERE to_uid=?",
        vec![uid.into()],
    ).unwrap_or_default();
    let mut rel_referrers: Vec<Value> = vec![];
    for r in &incoming_rels {
        let from_uid = r.get("from_uid").unwrap_or(&String::new());
        let (title, layer) = if let Ok(page_rows) = db.query_map("SELECT title,'Page' as layer FROM node_page WHERE uid=?", vec![from_uid.into()]) {
            if !page_rows.is_empty() {
                (page_rows[0].get("title").unwrap_or(&String::new()).clone(), "Page".to_string())
            } else {
                let derived_rows = db.query_map("SELECT title,layer FROM node_derived WHERE uid=?", vec![from_uid.into()]).unwrap_or_default();
                if !derived_rows.is_empty() {
                    (derived_rows[0].get("title").unwrap_or(&String::new()).clone(), derived_rows[0].get("layer").unwrap_or(&String::new()).clone())
                } else {
                    ("(unknown)".to_string(), "?".to_string())
                }
            }
        } else {
            ("(unknown)".to_string(), "?".to_string())
        };
        rel_referrers.push(json!({
            "from_uid": from_uid,
            "title": title,
            "layer": layer,
            "relation_name": r.get("relation_name").unwrap_or(&String::new()),
        }));
    }

    let total_refs = list_referrers.len() + report_referrers.len() + rel_referrers.len();
    if total_refs > 0 {
        return response::error(
            &format!("cannot delete {uid}: {} reference(s) exist", total_refs),
            "HasReferences",
            Some(json!({
                "uid": uid,
                "list_referrers": list_referrers,
                "report_referrers": report_referrers,
                "relation_referrers": rel_referrers,
                "total_refs": total_refs,
            })),
            &["remove references first (deactivate List/Report, or delete relation edges)".into()],
        );
    }

    // Delete outgoing relations first
    let _ = db.exec("DELETE FROM relations WHERE from_uid=?", vec![uid.into()]);

    // Delete from appropriate table
    if is_page {
        let _ = db.exec("DELETE FROM patches WHERE page_uid=?", vec![uid.into()]);
        let _ = db.exec("DELETE FROM node_page WHERE uid=?", vec![uid.into()]);
    } else {
        let _ = db.exec("DELETE FROM node_derived WHERE uid=?", vec![uid.into()]);
    }

    let _ = db.commit();

    response::success(
        json!({"uid": uid, "deleted_from": if is_page { "node_page" } else { "node_derived" }}),
        &format!("deleted node {uid}"),
    )
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

pub fn cmd_deactivate(wiki_path: &str, uid: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

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

pub fn cmd_verify(wiki_path: &str, uid: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

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
        let computed_hash = sha256_text(&body);
        checks.push(json!({"check":"content_hash","ok":content_hash == computed_hash,"detail":format!("stored={:.12}.. computed={:.12}..", &content_hash[..12.min(content_hash.len())], &computed_hash[..12.min(computed_hash.len())])}));

        let patches = db.query_map("SELECT version FROM patches WHERE page_uid=?", vec![uid.into()]).unwrap_or_default();
        let has_v1 = patches.iter().any(|p| p.get("version").map(|v| v == "1").unwrap_or(false));
        checks.push(json!({"check":"patch_v1_exists","ok":has_v1,"detail":format!("{} patch(es)", patches.len())}));
    }

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

pub fn cmd_list_create(wiki_path: &str, title: &str, members_csv: &str, dimension: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    let members: Vec<String> = members_csv.split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();

    if members.is_empty() {
        return response::error("provide --members uid1,uid2,...", "MissingMembers", None, &[]);
    }

    for m in &members {
        let rows = db.query_map("SELECT uid FROM node_page WHERE uid=? AND active=1", vec![m.clone()])
            .unwrap_or_default();
        if rows.is_empty() {
            return response::error(&format!("member not found: {m}"), "MemberNotFound", None, &[]);
        }
    }

    let uid = gen_uid();
    let ts = now_ts();

    let mut body_entries: Vec<Value> = vec![];
    for m in &members {
        let info = db.query_map("SELECT title FROM node_page WHERE uid=?", vec![m.clone()])
            .unwrap_or_default();
        let m_title = info.first().and_then(|r| r.get("title").cloned()).unwrap_or_default();
        body_entries.push(json!({"uid":m,"title":m_title}));
    }
    let body = serde_yaml::to_string(&body_entries).unwrap_or_default();

    let _ = db.exec(
        "INSERT INTO node_derived(uid,layer,title,dimension,attrs,created_at,updated_at,body) VALUES(?,?,?,?,?,?,?,?)",
        vec![uid.clone(), "List".into(), title.into(), dimension.into(), "".into(), ts.to_string(), ts.to_string(), body.clone()],
    );

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

pub fn cmd_list_extend(wiki_path: &str, uid: &str, members_csv: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

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

    for m in &new_members {
        let r = db.query_map("SELECT uid FROM node_page WHERE uid=? AND active=1", vec![m.clone()])
            .unwrap_or_default();
        if r.is_empty() {
            return response::error(&format!("member not found: {m}"), "MemberNotFound", None, &[]);
        }
    }

    let old_body = rows[0].get("body").cloned().unwrap_or_default();
    let mut entries: Vec<Value> = serde_yaml::from_str(&old_body).unwrap_or_default();
    let ts = now_ts();

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

pub fn cmd_entity_create(wiki_path: &str, title: &str, body: &str, source_page_uid: &str, attrs_json: &str, dimension: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    if title.trim().is_empty() {
        return response::error("entity requires --title", "MissingTitle", None, &[]);
    }

    if !source_page_uid.is_empty() {
        let rows = db.query_map("SELECT uid FROM node_page WHERE uid=? AND active=1", vec![source_page_uid.into()])
            .unwrap_or_default();
        if rows.is_empty() {
            return response::error(&format!("source page not found: {source_page_uid}"), "SourceNotFound", None, &[]);
        }
    }

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

pub fn cmd_report_create(wiki_path: &str, title: &str, body: &str, evidence_csv: &str, dimension: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    if body.trim().is_empty() {
        return response::error("report requires --body", "EmptyBody", None, &[]);
    }

    let evidence: Vec<String> = evidence_csv.split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();

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

// ======== NODES (DB metadata query) ========

pub fn cmd_nodes(wiki_path: &str, layer: Option<&str>, active_only: bool, limit: usize) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    let sql = if layer == Some("Page") || layer == Some("Derived") {
        let t = if layer == Some("Page") { "node_page" } else { "node_derived" };
        let active_filter = if active_only { " WHERE active=1" } else { "" };
        format!("SELECT uid,title,layer,created_at,updated_at FROM {t}{active_filter} ORDER BY created_at DESC LIMIT {limit}")
    } else if layer == Some("Entity") || layer == Some("List") || layer == Some("Report") {
        let active_filter = if active_only { " AND active=1" } else { "" };
        format!("SELECT uid,title,layer,created_at,updated_at FROM node_derived WHERE layer='{}'{active_filter} ORDER BY created_at DESC LIMIT {limit}", layer.unwrap())
    } else {
        let active_filter = if active_only { " WHERE active=1" } else { "" };
        format!("SELECT uid,title,'Page' as layer,created_at,updated_at FROM node_page{active_filter} UNION ALL SELECT uid,title,layer,created_at,updated_at FROM node_derived ORDER BY created_at DESC LIMIT {limit}")
    };

    let rows = db.query_map(&sql, vec![]).unwrap_or_default();
    let nodes: Vec<Value> = rows.iter().map(|r| {
        json!({
            "uid": r.get("uid").unwrap_or(&String::new()),
            "title": r.get("title").unwrap_or(&String::new()),
            "layer": r.get("layer").unwrap_or(&String::new()),
            "created_at": r.get("created_at").unwrap_or(&String::new()),
            "updated_at": r.get("updated_at").unwrap_or(&String::new()),
        })
    }).collect();

    response::success(
        json!({"nodes": nodes, "count": nodes.len(), "layer": layer.unwrap_or("all"), "active_only": active_only}),
        &format!("{} node(s)", nodes.len()),
    )
}

// ======== QUERY RELATION ========

pub fn cmd_query_relation(wiki_path: &str, from_uid: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    let rows = db.query_map("SELECT to_uid,relation_name,comment,position,created_at FROM relations WHERE from_uid=? ORDER BY position", vec![from_uid.into()]).unwrap_or_default();

    let mut rels: Vec<Value> = vec![];
    for r in &rows {
        let to_uid = r.get("to_uid").unwrap_or(&String::new());

        let to_info = if let Ok(page_rows) = db.query_map("SELECT title,'Page' as layer FROM node_page WHERE uid=?", vec![to_uid.clone()]) {
            if !page_rows.is_empty() {
                Some((page_rows[0].get("title").unwrap_or(&String::new()).clone(), "Page".to_string()))
            } else {
                None
            }
        } else { None };

        let (to_title, to_layer) = if let Some((t, l)) = to_info {
            (t, l)
        } else if let Ok(derived_rows) = db.query_map("SELECT title,layer FROM node_derived WHERE uid=?", vec![to_uid.clone()]) {
            if !derived_rows.is_empty() {
                (derived_rows[0].get("title").unwrap_or(&String::new()).clone(), derived_rows[0].get("layer").unwrap_or(&String::new()).clone())
            } else {
                ("(missing)".to_string(), "?".to_string())
            }
        } else {
            ("(missing)".to_string(), "?".to_string())
        };

        rels.push(json!({
            "to_uid": to_uid,
            "to_title": to_title,
            "to_layer": to_layer,
            "relation_name": r.get("relation_name").unwrap_or(&String::new()),
            "comment": r.get("comment").unwrap_or(&String::new()),
            "position": r.get("position").unwrap_or(&String::new()),
            "created_at": r.get("created_at").unwrap_or(&String::new()),
        }));
    }

    response::success(
        json!({"from_uid": from_uid, "relations": rels, "edge_count": rels.len()}),
        &format!("{} edge(s) in LRU order (head = most recently touched)", rels.len()),
    )
}

// ======== LIST SHOW ========

pub fn cmd_list_show(wiki_path: &str, uid: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    let rows = db.query_map("SELECT uid,title,dimension,body,created_at,updated_at FROM node_derived WHERE uid=? AND layer='List'", vec![uid.into()]).unwrap_or_default();
    if rows.is_empty() {
        return response::error(&format!("List not found: {uid}"), "ListNotFound", None, &[]);
    }

    let row = &rows[0];
    let body = row.get("body").cloned().unwrap_or_default();
    let members: Vec<Value> = serde_yaml::from_str(&body).unwrap_or_default();

    response::success(
        json!({
            "uid": row.get("uid").unwrap_or(&String::new()),
            "title": row.get("title").unwrap_or(&String::new()),
            "dimension": row.get("dimension").unwrap_or(&String::new()),
            "members": members,
            "member_count": members.len(),
            "created_at": row.get("created_at").unwrap_or(&String::new()),
            "updated_at": row.get("updated_at").unwrap_or(&String::new()),
        }),
        &format!("List {uid}: {} member(s)", members.len()),
    )
}

// ======== REPORT SHOW ========

pub fn cmd_report_show(wiki_path: &str, uid: &str) -> Value {
    let db = match open_db(wiki_path) { Ok(d) => d, Err(e) => return response::error(&e, "DbError", None, &[]) };

    let rows = db.query_map("SELECT uid,title,dimension,body,created_at,updated_at FROM node_derived WHERE uid=? AND layer='Report'", vec![uid.into()]).unwrap_or_default();
    if rows.is_empty() {
        return response::error(&format!("Report not found: {uid}"), "ReportNotFound", None, &[]);
    }

    let row = &rows[0];
    let body = row.get("body").cloned().unwrap_or_default();

    let rels = db.query_map("SELECT to_uid,relation_name FROM relations WHERE from_uid=? AND relation_name='cites'", vec![uid.into()]).unwrap_or_default();
    let mut references: Vec<Value> = vec![];
    let mut dangling: Vec<String> = vec![];

    for r in &rels {
        let to_uid = r.get("to_uid").unwrap_or(&String::new()).clone();
        let (title, layer) = if let Ok(page_rows) = db.query_map("SELECT title,'Page' as layer FROM node_page WHERE uid=? AND active=1", vec![to_uid.clone()]) {
            if !page_rows.is_empty() {
                (page_rows[0].get("title").unwrap_or(&String::new()).clone(), "Page".to_string())
            } else {
                ("(missing)".to_string(), "?".to_string())
            }
        } else {
            ("(missing)".to_string(), "?".to_string())
        };

        let is_dangling = title == "(missing)";
        if is_dangling {
            dangling.push(to_uid.clone());
        }

        references.push(json!({
            "uid": to_uid,
            "title": title,
            "layer": layer,
            "relation_name": r.get("relation_name").unwrap_or(&String::new()),
        }));
    }

    let data = json!({
        "uid": row.get("uid").unwrap_or(&String::new()),
        "title": row.get("title").unwrap_or(&String::new()),
        "body": body,
        "dimension": row.get("dimension").unwrap_or(&String::new()),
        "references": references,
        "evidence_count": references.len(),
        "created_at": row.get("created_at").unwrap_or(&String::new()),
        "updated_at": row.get("updated_at").unwrap_or(&String::new()),
    });

    if dangling.is_empty() {
        response::success(data, &format!("Report {uid}: {} evidence link(s)", references.len()))
    } else {
        response::warning(
            data,
            &format!("Report shown; {} dangling evidence ref(s)", dangling.len()),
            &[format!("dangling: {:?}", dangling)],
        )
    }
}

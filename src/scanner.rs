//! Keyword scanner — scans node bodies for keywords.
//! Pure Rust with memchr-style scanning.

use serde::Serialize;
use std::collections::HashMap;

/// A single keyword hit.
#[derive(Debug, Clone, Serialize)]
pub struct KeywordHit {
    pub uid: String,
    pub char_pos: usize,
    pub keyword: String,
    pub snippet: String,
}

/// Scan uid→body map for keyword hits.
/// Returns {keyword: [hit, ...]}.
pub fn scan_bodies(
    uid_body: &HashMap<String, String>,
    keywords: &[String],
) -> HashMap<String, Vec<KeywordHit>> {
    let mut results: HashMap<String, Vec<KeywordHit>> = keywords
        .iter()
        .map(|k| (k.clone(), Vec::new()))
        .collect();

    for kw in keywords {
        if kw.trim().is_empty() {
            continue;
        }
        let kw_lower = kw.to_lowercase();
        let hits = results.get_mut(kw).unwrap();

        for (uid, body) in uid_body {
            let body_lower = body.to_lowercase();
            let mut pos = 0usize;
            while let Some(found) = body_lower[pos..].find(&kw_lower) {
                let abs_pos = pos + found;
                // Verify exact-case match (not just lower)
                if body[abs_pos..].starts_with(kw.as_str()) {
                    let snippet_start = abs_pos.saturating_sub(50);
                    let snippet_end = (abs_pos + kw.len() + 50).min(body.len());
                    let snippet = body[snippet_start..snippet_end].to_string();
                    hits.push(KeywordHit {
                        uid: uid.clone(),
                        char_pos: abs_pos,
                        keyword: kw.clone(),
                        snippet,
                    });
                }
                pos = abs_pos + 1;
                if pos >= body.len() {
                    break;
                }
            }
        }
    }
    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scan_finds_keyword() {
        let mut map = HashMap::new();
        map.insert("N1".into(), "hello world machine learning".into());
        let results = scan_bodies(&map, &["machine".into()]);
        let hits = results.get("machine").unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].uid, "N1");
    }

    #[test]
    fn test_scan_case_sensitive() {
        let mut map = HashMap::new();
        map.insert("N1".into(), "Hello WORLD".into());
        let results = scan_bodies(&map, &["WORLD".into()]);
        assert_eq!(results.get("WORLD").unwrap().len(), 1);
        // "world" won't match "WORLD" in case-sensitive check
        let results2 = scan_bodies(&map, &["world".into()]);
        assert_eq!(results2.get("world").unwrap().len(), 0);
    }
}

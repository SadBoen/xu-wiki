//! Path helpers, UID generation, hashing, slugification.
//! Pure Rust — no Python deps.

use regex::Regex;
use sha2::{Digest, Sha256};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static UID_COUNTER: AtomicU64 = AtomicU64::new(0);
static UID_LAST_SEC: AtomicU64 = AtomicU64::new(0);

const UID_ALPHABET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

pub fn now_ts() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

pub fn gen_uid() -> String {
    let now_sec = now_ts();
    let last_sec = UID_LAST_SEC.load(Ordering::Relaxed);

    let counter = if now_sec == last_sec {
        UID_COUNTER.fetch_add(1, Ordering::Relaxed) + 1
    } else {
        UID_LAST_SEC.store(now_sec, Ordering::Relaxed);
        UID_COUNTER.store(0, Ordering::Relaxed);
        0
    };

    if counter < 1296 {
        let q = (counter / 36) as usize;
        let r = (counter % 36) as usize;
        let counter_part = format!(
            "{}{}",
            UID_ALPHABET[q] as char,
            UID_ALPHABET[r] as char
        );
        let random_part: String = getrandom(6)
            .iter()
            .map(|&b| UID_ALPHABET[(b % 36) as usize] as char)
            .collect();
        format!("{}{}", counter_part, random_part)
    } else {
        getrandom(8)
            .iter()
            .map(|&b| UID_ALPHABET[(b % 36) as usize] as char)
            .collect()
    }
}

fn getrandom(len: usize) -> Vec<u8> {
    use rand::RngCore;
    let mut bytes = vec![0u8; len];
    rand::rngs::OsRng.fill_bytes(&mut bytes);
    bytes
}

pub fn is_valid_uid(uid: &str) -> bool {
    uid.len() == 8 && uid.chars().all(|c| c.is_ascii_alphanumeric())
}

pub fn sha256_text(text: &str) -> String {
    let mut h = Sha256::new();
    h.update(text.as_bytes());
    format!("{:x}", h.finalize())
}

pub fn sha256_bytes(data: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(data);
    format!("{:x}", h.finalize())
}

pub fn sha256_file(path: &Path) -> std::io::Result<String> {
    use std::io::Read;
    let mut file = std::fs::File::open(path)?;
    let mut h = Sha256::new();
    let mut buf = [0u8; 65536];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(format!("{:x}", h.finalize()))
}

pub fn safe_slug(text: &str, maxlen: usize) -> String {
    let re = Regex::new(r"[^\w\-]+").unwrap();
    let lowered = text.to_lowercase();
    let s = re.replace_all(lowered.trim(), "-");
    let re2 = Regex::new(r"-+").unwrap();
    let s = re2.replace_all(&s, "-").trim_matches('-').to_string();
    let s = if s.is_empty() { "untitled".to_string() } else { s };
    s.chars().take(maxlen).collect()
}

pub fn safe_node_path(node_path: &str) -> Result<String, String> {
    if node_path.is_empty() {
        return Ok(String::new());
    }
    let normalized = node_path.replace('\\', "/");
    let parts: Vec<&str> = normalized
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    for part in &parts {
        if *part == ".." {
            return Err(format!("node-path traversal rejected: {node_path:?}"));
        }
    }
    Ok(parts.join("/"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_uid_format() {
        let uid = gen_uid();
        assert!(is_valid_uid(&uid));
        assert_eq!(uid.len(), 8);
    }

    #[test]
    fn test_uid_uniqueness() {
        let mut seen = std::collections::HashSet::new();
        for _ in 0..1000 {
            let uid = gen_uid();
            assert!(seen.insert(uid.clone()), "duplicate uid: {uid}");
        }
        assert_eq!(seen.len(), 1000);
    }

    #[test]
    fn test_uid_charset() {
        for _ in 0..100 {
            let uid = gen_uid();
            for c in uid.chars() {
                assert!(c.is_ascii_alphanumeric(), "bad char in uid: {c}");
            }
        }
    }

    #[test]
    fn test_sha256_stable() {
        assert_eq!(sha256_text("abc"), sha256_text("abc"));
        assert_ne!(sha256_text("abc"), sha256_text("abd"));
    }

    #[test]
    fn test_sha256_bytes() {
        let h1 = sha256_bytes(b"hello");
        let h2 = sha256_bytes(b"hello");
        assert_eq!(h1, h2);
        assert_eq!(h1.len(), 64);
    }

    #[test]
    fn test_sha256_file() {
        let tmp_dir = std::env::temp_dir();
        let tmp = tmp_dir.join(format!("xu-test-{}", gen_uid()));
        std::fs::write(&tmp, b"test content").unwrap();
        let h = sha256_file(&tmp).unwrap();
        let _ = std::fs::remove_file(&tmp);
        assert_eq!(h, sha256_text("test content"));
    }

    #[test]
    fn test_safe_slug_basic() {
        assert_eq!(safe_slug("Hello World!", 80), "hello-world");
        assert_eq!(safe_slug("", 80), "untitled");
        assert_eq!(safe_slug("  Spaces  ", 80), "spaces");
        assert_eq!(safe_slug("a-b_c", 80), "a-b_c");
    }

    #[test]
    fn test_safe_slug_maxlen() {
        let s = safe_slug("very long title that should be truncated", 10);
        assert_eq!(s.len(), 10);
        assert!(s.starts_with("very-long"));
    }

    #[test]
    fn test_safe_slug_cjk() {
        let s = safe_slug("你好世界", 80);
        assert_eq!(s, "你好世界"); // CJK chars pass through \\w
    }

    #[test]
    fn test_safe_node_path_normal() {
        assert_eq!(safe_node_path("papers/ml").unwrap(), "papers/ml");
        assert_eq!(safe_node_path("").unwrap(), "");
        assert_eq!(safe_node_path("/papers/ml/").unwrap(), "papers/ml");
        assert_eq!(safe_node_path("/abs/path").unwrap(), "abs/path");
    }

    #[test]
    fn test_safe_node_path_rejects_traversal() {
        for bad in &["../etc", "a/../../b", "../../tmp/evil", "foo/../bar"] {
            assert!(safe_node_path(bad).is_err(), "should reject {bad:?}");
        }
    }

    #[test]
    fn test_safe_node_path_collapses_dots() {
        assert_eq!(safe_node_path("a/./b").unwrap(), "a/b");
    }

    #[test]
    fn test_now_ts_is_reasonable() {
        let ts = now_ts();
        assert!(ts > 1700000000); // after 2023
    }
}

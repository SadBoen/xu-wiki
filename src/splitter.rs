//! Page splitting (PRIN-ING-4) + CJK bigram fallback.
//! Pure Rust — regex, no Python deps.

use regex::Regex;
use std::collections::HashMap;
use std::sync::LazyLock;

static HEADER_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(#{1,6})\s+").unwrap()
});

const PAGE_SPLIT_LINES: usize = 300;

/// Split body into pages of ~max_lines.
pub fn split_pages(text: &str, max_lines: Option<usize>) -> Vec<String> {
    let max_lines = max_lines.unwrap_or(PAGE_SPLIT_LINES);
    let lines: Vec<&str> = text.lines().collect();
    if lines.is_empty() {
        return if text.trim().is_empty() {
            vec![]
        } else {
            vec![text.to_string()]
        };
    }
    if lines.len() <= max_lines {
        return vec![lines.join("\n")];
    }

    // Find header cut points
    let header_idx: Vec<usize> = lines
        .iter()
        .enumerate()
        .filter(|(_, ln)| HEADER_RE.is_match(ln))
        .map(|(i, _)| i)
        .collect();

    if header_idx.is_empty() {
        return hard_split(&lines, max_lines);
    }

    let mut boundaries: Vec<usize> = vec![0];
    boundaries.extend(header_idx);
    boundaries.push(lines.len());
    boundaries.sort();
    boundaries.dedup();

    let mut sections: Vec<(usize, usize)> = Vec::new();
    for w in boundaries.windows(2) {
        if w[1] > w[0] {
            sections.push((w[0], w[1]));
        }
    }

    let mut pages: Vec<String> = Vec::new();
    let mut cur_start = sections[0].0;
    let mut cur_end = cur_start;
    for &(a, b) in &sections {
        let seg_len = b - cur_start;
        if seg_len >= max_lines && cur_end > cur_start {
            pages.push(lines[cur_start..cur_end].join("\n"));
            cur_start = a;
        }
        cur_end = b;
        if cur_end - cur_start >= max_lines {
            pages.push(lines[cur_start..cur_end].join("\n"));
            cur_start = cur_end;
        }
    }
    if cur_end > cur_start {
        pages.push(lines[cur_start..cur_end].join("\n"));
    }

    // Hard split oversized pages
    let mut final_pages: Vec<String> = Vec::new();
    for pg in pages {
        let pls: Vec<&str> = pg.lines().collect();
        if pls.len() > max_lines * 2 {
            final_pages.extend(hard_split(&pls, max_lines));
        } else {
            final_pages.push(pg);
        }
    }

    final_pages
        .into_iter()
        .filter(|p| !p.trim().is_empty())
        .collect()
}

fn hard_split(lines: &[&str], max_lines: usize) -> Vec<String> {
    let mut out = Vec::new();
    for chunk in lines.chunks(max_lines) {
        let joined = chunk.join("\n");
        if joined.trim().len() > 0 {
            out.push(joined);
        }
    }
    out
}

// ---- CJK bigram fallback tokenizer ----

static LATIN_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[A-Za-z0-9]{2,}").unwrap()
});

static CJK_RUN_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[\u{4e00}-\u{9fff}]+").unwrap()
});

/// Extract noun-like tokens with counts using CJK bigram fallback.
/// This is the pure-Rust fallback; when jieba is available, the Python
/// bridge should be used instead for POS-based extraction.
pub fn extract_nouns_fallback(text: &str) -> HashMap<String, i32> {
    let mut counts: HashMap<String, i32> = HashMap::new();
    let lowered = text.to_lowercase();

    for m in LATIN_RE.find_iter(&lowered) {
        *counts.entry(m.as_str().to_string()).or_insert(0) += 1;
    }

    for run_match in CJK_RUN_RE.find_iter(&lowered) {
        let run = run_match.as_str();
        let chars: Vec<char> = run.chars().collect();
        if chars.len() < 2 {
            let tok: String = chars.iter().collect();
            *counts.entry(tok).or_insert(0) += 1;
        } else {
            for w in chars.windows(2) {
                let tok: String = w.iter().collect();
                *counts.entry(tok).or_insert(0) += 1;
            }
        }
    }
    counts
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_split_small() {
        let pages = split_pages("a\nb\nc", Some(300));
        assert_eq!(pages.len(), 1);
    }

    #[test]
    fn test_split_large() {
        let text: String = (0..720).map(|i| format!("line {i}")).collect::<Vec<_>>().join("\n");
        let pages = split_pages(&text, Some(300));
        assert_eq!(pages.len(), 3);
    }

    #[test]
    fn test_extract_nouns_fallback() {
        let nouns = extract_nouns_fallback("machine learning 深度学习");
        assert!(nouns.contains_key("machine"));
        assert!(nouns.contains_key("learning"));
        // CJK bigrams
        assert!(nouns.values().sum::<i32>() > 0);
    }
}

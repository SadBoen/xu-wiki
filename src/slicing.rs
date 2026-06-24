//! Elastic slicing + neighborhood merge (DESIGN-ARCH-6/7, PRIN-QRY-8/9).
//! Pure Rust — no Python deps.

use std::collections::HashSet;

const HIGH_PUNCT: &str = "。？！.?!\n";
const LOW_PUNCT: &str = "，,;；";

/// Expand a hit [start, end) into a slice bounded by soft/hard limits.
pub fn make_slice(
    text: &str,
    hit_start: usize,
    hit_end: usize,
    soft_limit: usize,
    hard_limit: usize,
) -> (usize, usize, String) {
    let n = text.len();
    let left = expand_left(text, hit_start, soft_limit, hard_limit);
    let right = expand_right(text, hit_end, soft_limit, hard_limit);
    let left = left.min(n);
    let right = right.min(n);
    (left, right, text[left..right].to_string())
}

fn expand_left(text: &str, pos: usize, soft: usize, hard: usize) -> usize {
    let soft_bound = pos.saturating_sub(soft);
    let hard_bound = pos.saturating_sub(hard);
    // search backward within soft window for high punct
    let chars: Vec<char> = text.chars().collect();
    for i in (soft_bound..pos).rev() {
        if i < chars.len() && HIGH_PUNCT.contains(chars[i]) {
            return i + 1;
        }
    }
    for i in (soft_bound..pos).rev() {
        if i < chars.len() && LOW_PUNCT.contains(chars[i]) {
            return i + 1;
        }
    }
    hard_bound
}

fn expand_right(text: &str, pos: usize, soft: usize, hard: usize) -> usize {
    let n = text.len();
    let soft_bound = n.min(pos + soft);
    let hard_bound = n.min(pos + hard);
    let chars: Vec<char> = text.chars().collect();
    for i in pos..soft_bound {
        if i < chars.len() && HIGH_PUNCT.contains(chars[i]) {
            return i + 1;
        }
    }
    for i in pos..soft_bound {
        if i < chars.len() && LOW_PUNCT.contains(chars[i]) {
            return i + 1;
        }
    }
    hard_bound
}

/// A slice block with hits and position.
#[derive(Debug, Clone)]
pub struct SliceBlock {
    pub start: usize,
    pub end: usize,
    pub text: String,
    pub hits: HashSet<String>,
    pub line: usize,
}

/// Merge same-file slices whose physical distance < radius.
/// When `full_text` is provided, re-slices the merged range from the source.
pub fn merge_slices(
    slices: &[SliceBlock],
    radius: usize,
    full_text: Option<&str>,
) -> Vec<SliceBlock> {
    if slices.is_empty() {
        return vec![];
    }

    let mut ordered: Vec<SliceBlock> = slices.to_vec();
    ordered.sort_by_key(|s| s.start);

    let first = ordered[0].clone();
    let mut merged: Vec<SliceBlock> = vec![SliceBlock {
        hits: first.hits.clone(),
        ..first
    }];

    for s in &ordered[1..] {
        let last = merged.last_mut().unwrap();
        if s.start.saturating_sub(last.end) < radius {
            last.end = last.end.max(s.end);
            last.hits.extend(s.hits.iter().cloned());
            if let Some(full) = full_text {
                if last.end <= full.len() {
                    last.text = full[last.start..last.end].to_string();
                }
            }
        } else {
            let mut nb = s.clone();
            nb.hits = s.hits.clone();
            merged.push(nb);
        }
    }
    merged
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_make_slice_hard_limit() {
        let text = "x".repeat(500);
        let (s, e, _) = make_slice(&text, 250, 251, 80, 150);
        assert!(e - s <= 301);
    }

    #[test]
    fn test_merge_adjacent() {
        let s1 = SliceBlock {
            start: 0, end: 50, text: "a".into(),
            hits: ["k1".into()].into(), line: 1,
        };
        let s2 = SliceBlock {
            start: 60, end: 100, text: "b".into(),
            hits: ["k2".into()].into(), line: 2,
        };
        let merged = merge_slices(&[s1, s2], 80, None);
        assert_eq!(merged.len(), 1);
        assert_eq!(merged[0].hits.len(), 2);
    }
}

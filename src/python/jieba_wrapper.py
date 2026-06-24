"""jieba_wrapper — thin wrapper around jieba for Rust via pyo3.

No business logic. Pure library interface.
"""
import os
import sys

# Suppress jieba's "Building prefix dict..." banner which writes to FD 1/2
# and would corrupt JSON output in CLI mode.
_SUPPRESS = False


def _suppress_stderr():
    """Redirect jieba's stderr banner to /dev/null equivalent."""
    global _SUPPRESS
    _SUPPRESS = True


def _restore_stderr():
    global _SUPPRESS
    _SUPPRESS = False


def tokenize(text: str) -> list[tuple[str, str]]:
    """Run jieba.posseg.cut, return list of (word, flag) pairs."""
    import jieba.posseg as pseg

    fd_save = None
    devnull = None
    try:
        if _SUPPRESS:
            fd_save = os.dup(2)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 2)
    except OSError:
        pass

    try:
        words = list(pseg.cut(text))
        return [(w.word, w.flag) for w in words]
    finally:
        if fd_save is not None:
            os.dup2(fd_save, 2)
            os.close(fd_save)
        if devnull is not None:
            os.close(devnull)


def extract_nouns(text: str) -> dict[str, int]:
    """Extract noun-like tokens with within-document counts.

    Returns a dict of {word: count} for nouns only.
    Falls back to a CJK bigram tokenizer if jieba is unavailable.
    """
    import re

    _NOUN_FLAGS = {"n", "nr", "ns", "nt", "nz", "nl", "ng", "eng"}
    _LATIN_RE = re.compile(r"[A-Za-z0-9]{2,}")
    _CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")

    counts: dict[str, int] = {}

    try:
        pairs = tokenize(text)
        for word, flag in pairs:
            w = word.strip().lower()
            if len(w) < 2:
                continue
            if flag in _NOUN_FLAGS:
                counts[w] = counts.get(w, 0) + 1
        if counts:
            return counts
    except Exception:
        pass

    # Fallback tokenizer: Latin word runs + CJK bigrams
    lowered = text.lower()
    for tok in _LATIN_RE.findall(lowered):
        counts[tok] = counts.get(tok, 0) + 1
    for run in _CJK_RUN_RE.findall(lowered):
        for i in range(len(run) - 1):
            tok = run[i : i + 2]
            counts[tok] = counts.get(tok, 0) + 1
    return counts


def enable_parallel():
    """Enable jieba parallel mode."""
    import jieba
    jieba.enable_parallel()


def disable_parallel():
    """Disable jieba parallel mode."""
    import jieba
    jieba.disable_parallel()

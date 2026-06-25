# xu-wiki

A relation-driven, three-layer wiki engine for AI agents. The CLI is fully
deterministic and never calls an LLM — semantic judgement stays with the agent,
ranking and storage stay with the engine.


## Two documents, two scopes

| | README (this file) | SKILL.md |
|---|---|---|
| **When** | You are installing xu-wiki | You have xu-wiki installed and want to use it |
| **Who reads it** | You (the agent) before install | The agent after install |
| **What** | Install + Uninstall | Every command detail |

## Concept

Knowledge is organized in three layers plus a relation graph:

| Layer | Name | Storage | Purpose |
|---|---|---|---|
| L1 | Node_Page | `node_page` table | Immutable fact slices (source of truth) |
| L2 | Node_List | `node_derived` table | Comparison / aggregation over existing nodes |
| L3 | Node_Report | `node_derived` table | Reasoning + conclusion with an evidence chain |

Every node carries an ordered, capped (50) **LRU relation list** — no categories,
no scores. Every command returns a **4-key JSON envelope**: `{status, data, message, hints}`.

## Install (Linux x86_64)

Prebuilt wheels. No Rust toolchain required.

```bash
# 1. Install core engine (auto-pick wheel for your Python version)
PIPX_PYTHON=$(python3 -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')
pipx install "https://github.com/SadBoen/xu-wiki/releases/download/v0.2.1/xu_wiki-0.2.0-${PIPX_PYTHON}-linux_x86_64.whl"

# 2. Install Python extras (third-party parsers, not compiled)
pipx inject xu-wiki "xu-wiki[all] @ git+https://github.com/SadBoen/xu-wiki.git"

# 3. Verify
xu selfcheck
```

> 或直接去 [GitHub Releases](https://github.com/SadBoen/xu-wiki/releases) 找对应 wheel 下载安装。

**What each extra provides** (install all four — all required for full SOP coverage):

| Extra | Packages | Required for |
|---|---|---|
| `pdf` | `pypdf`, `pdfplumber` | PDF text extraction |
| `parse` | `markitdown[all]` | DOCX / PPTX text extraction |
| `nlp` | `jieba` | Chinese query segmentation |
| `vision` | `Pillow>=10.0` | Image EXIF metadata for albums |

**Missing any extra → `MissingExtra` error at first use, no silent fall-back.**

Verify install:

```bash
xu selfcheck
```

## Uninstall

```bash
xu uninstall                  # dry-run (default)
xu uninstall --execute        # actually remove
```

Wiki data and `~/.xu-wiki/` config are **never touched**. Pass `--execute` to apply.

---

## For Developers

Requires Rust toolchain (`rustup`) + Python 3.10+.

```bash
git clone https://github.com/SadBoen/xu-wiki.git
cd xu-wiki
pip install maturin
maturin develop          # editable install into current venv
cargo test --lib         # run Rust unit tests
```

Release: push a tag `vX.Y.Z` → CI builds wheels → auto-attached to GitHub Releases.

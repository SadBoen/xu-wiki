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

## ⚠️ REQUIRED for agents — install the skill

The wheel installs the CLI. The **skill bundle** (the agent's operating manual,
including `SKILL.md` and `references/`) is shipped as package data **inside**
the wheel and is **not** auto-deployed — the CLI does not know which agent
runtime you use.

> **No skill = the project is useless to an agent.** A naked `xu` binary
> gives the agent nothing to follow; commands are only meaningful in the
> order described in `SKILL.md` and the per-SOP files in `references/`.

After installing the wheel (step 1–3 below), **always** run:

```bash
xu skills install
# -> copies SKILL.md + references/ into ~/.hermes/skills/xu-wiki/
```

Use `xu skills path` to see the on-disk source, `xu skills list` to see the
file list, and `xu skills install --target <dir>` to deploy somewhere else
(e.g. Claude Desktop, Cursor, Trae — pass their skill directory).

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

> **Why no one-liner URL here:** maturin-built wheels embed a PEP 600 platform
> tag like `cp313-cp313-manylinux_2_39_x86_64.whl`. The exact name depends on
> the Python version used to build, and the user's local Python can be any
> `cp310`–`cp313`. Hard-coding a URL drifts. Use the helper below or pick
> from the [Releases page](https://github.com/SadBoen/xu-wiki/releases).

### Recommended — fetch the latest wheel that matches your Python

```bash
# 1. Pick the wheel that matches your Python, then install the core engine.
PIPX_PYTHON=$(python3 -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')
WHEEL_URL=$(curl -sSL https://api.github.com/repos/SadBoen/xu-wiki/releases/latest \
  | python3 -c "import json,sys,re; r=json.load(sys.stdin); print(next(a['browser_download_url'] for a in r['assets'] if a['name'].endswith('${PIPX_PYTHON}-linux_x86_64.whl')))")
pipx install "$WHEEL_URL"

# 2. Install Python extras (third-party parsers, not compiled)
pipx inject xu-wiki "xu-wiki[all] @ git+https://github.com/SadBoen/xu-wiki.git"

# 3. Verify CLI
xu selfcheck

# 4. REQUIRED for agents — install the skill bundle
xu skills install
```

### Fallback — copy the URL from GitHub Releases

If the helper above can't find a matching wheel (e.g. brand-new Python release
or non-x86_64 host), go to [GitHub Releases](https://github.com/SadBoen/xu-wiki/releases),
copy the exact wheel filename for your Python + platform, then:

```bash
pipx install "https://github.com/SadBoen/xu-wiki/releases/download/<TAG>/<WHEEL_FILENAME>"
```

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
The skill bundle at `~/.hermes/skills/xu-wiki/` is also left in place — remove it
manually if you want a fully clean uninstall.

---

## For Developers

Requires Rust toolchain (`rustup`) + Python 3.10+.

```bash
git clone https://github.com/SadBoen/xu-wiki.git
cd xu-wiki
pip install maturin
maturin develop          # editable install into current venv
cargo test --lib         # run Rust unit tests
xu skills install        # deploy the bundled skill for testing
```

Release: push a tag `vX.Y.Z` → CI builds wheels → auto-attached to GitHub Releases.

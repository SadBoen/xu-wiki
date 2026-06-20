# ingest — add content to a wiki

`/xu-wiki ingest` adds content to a wiki as **L1 Node_Page** (immutable). It
is the most complex SOP because L1 body style **must match the content
type** (PRIN-ING-13). The `content_type` frontmatter key stores the body form
(`article` for prose, `table` for tabular, `gallery` for album).

This file is **self-contained** (PRIN-SKILL-1). Cross-cutting rules
(L1 immutability, 4-key JSON, missing-args, paths-must-be-absolute) live in
`SKILL.md`; the body-form decision tree lives here because it only applies
to ingest.

## Hard rule for this SOP (PRIN-ING-2, PRIN-ING-13)

> **Route by content form first; Phase 1↔2 intermediate values are LLM-generated.**
>
> Content form routing (before Phase 1 — only this step requires a user question):
>
> | User says | Route to | Agent action |
> |---|---|---|
> | PDF / DOCX / XLSX / MD / text / single image | `ingest-file` → `ingest-commit` | Auto-fill `--content-type` from `CONTENT_TYPE_MAP` (`.xlsx/.csv`→`table`, images→`gallery`, rest→`article`); do not ask |
> | N images, one theme | `ingest-album` | Ask "vision per-photo? (yes/no)" before calling (PRIN-SOP-7) |
> | code block / terminal output | `ingest-commit --native` | Auto-fill `--content-type=article`; do not ask |
> | After commit: verify integrity | `ingest-verify` | 5 read-only checks (DB / nodes/ / hash / raw / format); run before declaring task done |
>
> After `ingest-file` succeeds, the Agent reads the temp file and synthesizes ALL
> intermediate values **without asking the user**: title, node_path, relations,
> content_type — these are LLM-generated decisions (PRIN-ING-2). The user never
> sees or approves these values.
>
> **content_type body validation** (PRIN-ING-13): the CLI validates body format
> before write — `article` accepts free text; `table` requires YAML list of dicts;
> `gallery` requires YAML list of dicts each with a `filename` field. Mismatch
> returns `BodyFormatMismatch` error and blocks commit.
>
> **Never split a single album into N parallel `ingest-file` + `ingest-commit`
> cycles** — that breaks the body-form rule and leaves N disjoint L1 pages
> with no album structure.

## CLI palette

```bash
# Two-phase prose flow (PRIN-ING-1)
xu ingest-file   --wiki <w> --file <abs> [--node-path <p>]   # Phase 1: parse → pending
xu ingest-commit --wiki <w> --pending <f> --title <t> \
                      [--content-type article|table|gallery] \
                      [--node-path <p>] [--relations '<json>'] \
                      [--native '<md>'] [--author <a>]

# Album single-shot flow (PRIN-ING-14)
xu ingest-album  --wiki <w> --title <t> --files <abs1,abs2,...> \
                      [--node-path <p>] [--layout table|list] [--vision] \
                      [--captions '<json>'] [--author <a>]

# Optional follow-up (still in the ingest SOP — wiring happens here)
xu query-relation add  --wiki <w> --from-uid <uid> --to-uid <uid> \
                            --relation-name <r> [--comment <c>]
xu list create --wiki <w> --title <t> --members <uid,uid,...> \
                    [--dimension <d>] [--node-path <p>]
xu report create --wiki <w> --title <t> --body <md> \
                      --references <uid,uid,...> [--node-path <p>]
```

| Flag (album) | Required | Purpose |
|---|---|---|
| `--wiki` | yes | Wiki name or alias |
| `--title` | yes | Album theme = L1 page title |
| `--files` | yes | Comma-separated absolute paths to images |
| `--node-path` | no | Where in the wiki tree to place the page |
| `--layout` | no | `table` (default) or `list` |
| `--vision` | no | Flag that user wants per-photo captions; sets intent even if backend absent (PRIN-SOP-7) |
| `--captions` | no | Pre-computed captions as JSON; if absent, vision backend runs at view time |
| `--author` | no | L1 frontmatter author field |

## Workflow — prose / document (PDF / DOCX / MD / image)

1. **Confirm wiki exists and file is absolute** (rule 8, rule 9 in `SKILL.md`).
2. **Phase 1 — `ingest-file`**: parses the file via the offline-first
   fallback chain (MinerU → markitdown → text → image, CONST-ING-1) and
   writes a temp file to the system temp directory. Returns the temp file path
   in `data.pending`. No node is created at this stage.
3. **Agent synthesizes all metadata** from the temp file (PRIN-ING-2):
   title, node_path, relations, content_type — all LLM-generated, never asked
   of the user. `--title` is required by CLI but the value comes from the LLM.
4. **取证副本 (PRIN-ING-6)**: after `ingest-commit` succeeds, the CLI copies
   the source file to `raws/<node_path>/<original_name>` (first page only).
   **This is mandatory for all document types** — `.md / .pdf / .docx / .pptx`
   must all be physically stored. The response `data.created[].raw_path` should
   be non-null. If it is null, PRIN-ING-6 was bypassed — stop and investigate.
   > **Exception**: `--native` mode has no source file (agent-synthesized text),
   > so `raw_path` is null by design. But `--native` still requires `--source`
   > (a reference path) for dedup. Use `--pending` for any external document.
5. **Phase 2 — `ingest-commit --pending <f> --title <t>`**: promotes temp file
   to L1. All intermediate values (content_type, node_path, relations, author)
   are synthesized by the LLM and passed as CLI arguments.
6. **Page splitting notice**: if `data.page_count > 1`, tell the user
   "文档较长，已自动按容量分片为 N 个 L1 节点"。This is normal behavior, not an error.
7. **Verify raws/**: after commit, confirm `raw_path` in the response is non-null.
   An empty `raws/` directory with populated `nodes/page/` = PRIN-ING-6 was
   bypassed (usually from `--native` on a document).
8. **(Optional) Wire relations** with `query-relation add`.
9. **(Optional) Group into L2/L3** with `list create` / `report create`.

## Workflow — album (multiple images, one theme)

1. **Verify files**: all `--files` must be absolute paths to images.
2. **Ask vision intent**: "需要每张照片的 AI 描述吗？" — set `--vision` if yes
   (PRIN-SOP-7: never decide for the user).
3. **Single-shot `ingest-album`**: writes ONE L1 page with a markdown
   table (or list if `--layout list`). Album theme = `--title`.
4. **(Optional) Wire relations / group** as in prose flow.

## Workflow — code block / terminal output

1. **Single `ingest-commit --native "<code>"`**: skips Phase 1 (no parse),
   goes through dedup / patches v1 / IDF directly.
   > **Warning — PRIN-ING-6 bypass**: `--native` has **no physical source file**
   > (it is agent-synthesized text), so `raw_path` in the response is null by
   > design. **Do NOT use `--native` for external `.md / .pdf / .docx / .pptx**
   > ingestion** — that silently skips the raws/ forensic copy. Use the
    > `--pending` path (Phase 1 + Phase 2) for any external document.

## Phase 1 temp file lifecycle (PRIN-ING-7)

Phase 1 writes to a **system temp file** (not `nodes/pending/`). The temp file
path is returned in `data.pending` of the `ingest-file` response. Its lifecycle:

| Event | What happens |
|---|---|
| `ingest-file` runs | Creates temp file via `tempfile.gettempdir()` (e.g. `/tmp/<stem>-pre.md`) |
| `ingest-commit` succeeds | CLI deletes temp file immediately (PRIN-ING-7) |
| `ingest-commit` fails | Temp file **retained** for debug / retry |
| Any leftover temp file after success | **Bug** — fix the error and re-run `ingest-commit` to trigger deletion |

**There is no `nodes/pending/` directory.** The two-phase separation is achieved
by the system temp file; no wiki-internal staging directory exists.

## Post-commit reflection (PRIN-CR-1, asymmetric bias)

After **every** `ingest-commit` (single page, album, or batch), the agent MUST
run a creation-value reflection **before declaring the task done**. The CLI
does not run this reflection (PRIN-QRY-3) and never auto-creates (PRIN-ING-*).

**Why ingest leans List (PRIMARY), not Report:**
L1 adds fresh facts. A List curates a comparable group of facts; a Report
needs a conclusion that doesn't yet exist. So:

1. **List valuation — PRIMARY (bias toward proposing).**
   Ask all three:
   - Did this ingest add ≥ 1 page that is comparable to ≥ 1 existing L1
     page on an obvious axis (parameter count / accuracy / date / location /
     category / model family / phase)?
   - Or did this ingest add ≥ 2 pages that share an obvious dimension?
   - Would a Node_List save future "find me the X" queries time, or
     prevent duplication of future ingests?
   → If all three: draft `list create` payload
   (`--title` / `--dimension` / `--members`), show the preview to the user
   in **one** sentence (e.g. "建一个 List 把 X、Y、Z 放一起，按
   parameter count 对比？"), wait for explicit approval.

2. **Report valuation — SECONDARY (opportunistic only).**
   - Did the new page CONTRADICT something in the existing wiki?
   - Did it force a re-evaluation of an existing Report's conclusion?
   - Is there a documented conflict the user should know about?
   → Only propose if signal is strong. By default, after ingest, do NOT
   propose Report.

3. **Neither** — say nothing. Don't manufacture value.

**Important**: single-page ingest also triggers reflection (item 1's first
bullet). "Just one page" is not an excuse; the value can be "this page
joins an existing group". The CLI provides no hint here — the reflection is
the agent's job entirely.

**Important**: this section is the **ingest-side counterpart** to the
query-side reflection in `query.md §Workflow` step 5. Same asymmetric bias,
opposite default type.

## Example — prose

```bash
xu ingest-file   --wiki research --file ~/Downloads/bert.pdf
# → {"status": "success", "data": {"pending": "/tmp/bert-pre.md", "parser": "pdf", ...}, ...}
# Agent reviews /tmp/bert-pre.md, then:
xu ingest-commit --wiki research \
  --pending /tmp/bert-pre.md \
  --title "BERT: Pre-training of Deep Bidirectional Transformers"
# → {"status": "success", "data": {"uid": "WXYZ5678", "title": "BERT: ..."}, ...}
```

## Example — album

```bash
xu ingest-album --wiki research \
  --title "SGW001 #1 完工照片" \
  --files ~/uploads/001.jpg,~/uploads/002.jpg,~/uploads/003.jpg \
  --vision
# → {"status": "success", "data": {"uid": "...", "rows": 3}, ...}

### Verify

After commit, verify the node integrity (read-only, non-destructive):

```bash
xu ingest-verify --wiki research --uid <uid from commit response>
# → {"status": "success", "data": {"passed": ["DB record", "nodes_file", ...], "failed": [], "checks": [...]}, ...}
```

5 checks: DB record, nodes/ frontmatter completeness, content_hash match, raw file exists (non-native), content_type ↔ body format match.
```

## Common pitfalls

- **Wrong body form** — applying `ingest-file` to an album produces N
  disjoint L1 pages with no album structure. Always confirm form first.
- **Deciding vision for the user** — if the user didn't say, ASK. Setting
  `--vision` when the build has no vision backend records the intent
  (PRIN-SOP-7) but does NOT crash. This is the right way to defer.
- **Splitting an album** — never call `ingest-file` N times then
  `ingest-commit` N times for an album. Use `ingest-album` once.
- **Editing the L1 body after commit** — the L1 markdown is immutable
  (PRIN-ARCH-2/3, hard rule 1 in `SKILL.md`). To "add another photo to
  the album" use `ingest-album` with a fresh `ingest-album` call — wait,
  see `ingest-add` (album-add CLI; see 02-album-scenario.md for the
  pattern; otherwise just use `ingest-album` against the existing node-path).
- **Empty raws/ despite L1 pages** — if `nodes/page/` has content but
  `raws/` is empty, PRIN-ING-6 was bypassed (usually from using `--native`
  on a document). `data.created[].raw_path` in the response would be null.
  Fix: delete the L1 and re-ingest via `--pending` path.
- **Skip ingest-verify after commit** — run `xu ingest-verify <wiki> <uid>` to
  confirm DB / nodes/ / content_hash / raw file / body format are all consistent;
  do not treat `ingest-commit` returning success as sufficient proof of integrity.
- **Phase 1 temp file not deleted after commit** — if `ingest-commit` succeeded
   but the temp file at `data.pending` still exists on disk, that is a bug.
   Re-running `ingest-commit` with the same temp file will reject as duplicate
   (Level-2 dedup), but will confirm the file is deleted.

## Cross-references

- Cross-cutting rules (immutability, JSON, paths, missing-args) → `SKILL.md §Hard rules`
- The `query` and `read` CLIs (for reading the ingest result) → `SKILL.md §SOP map` (query SOP); use `ingest-verify` for integrity checks
- The 50-edge LRU semantics → `SKILL.md §Architecture in 30 seconds`
- Full ingest architecture → `design-docs/05-ingest.md`

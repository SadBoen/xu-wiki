# ingest — add content to a wiki

`/xu-wiki ingest` adds content to a wiki as **L1 Node_Page** (immutable). It
is the most complex SOP because L1 body style **must match the content
type**. The `content_type` frontmatter key stores the body form
(`article` for prose, `table` for tabular, `gallery` for album).

This file is **self-contained** (PRIN-SKILL-1). Cross-cutting rules
(L1 immutability, 4-key JSON, missing-args, paths-must-be-absolute) live in
`SKILL.md`; the body-form decision tree lives here because it only applies
to ingest.

## Hard rule for this SOP

> **Route by content form first; Phase 1↔2 intermediate values are LLM-generated.**
>
> Content form routing (before Phase 1 — only this step requires a user question):
>
> | User says | Route to | Agent action |
> |---|---|---|
> | PDF / DOCX / XLSX / MD / text / single image | `ingest-file` → `ingest-commit` | Auto-fill `--content-type` from `CONTENT_TYPE_MAP` (`.xlsx/.csv`→`table`, images→`gallery`, rest→`article`); do not ask |
> | N images, one theme | `ingest-album` | Ask "vision per-photo? (yes/no)" before calling |
> | code block / terminal output | `ingest-commit --native` | Auto-fill `--content-type=article`; do not ask |
> | After commit: verify integrity | `ingest-verify` | 5 read-only checks (DB / nodes/ / hash / raw / format); run before declaring task done |
>
> After `ingest-file` succeeds, the Agent reads the temp file and synthesizes ALL
> intermediate values **without asking the user**: title, node_path, relations,
> content_type — these are LLM-generated decisions. The user never
> sees or approves these values.
>
> **content_type body validation**: the CLI validates body format
> before write — `article` accepts free text; `table` requires YAML list of dicts;
> `gallery` requires YAML list of dicts each with a `filename` field. Mismatch
> returns `BodyFormatMismatch` error and blocks commit.
>
> **Never split a single album into N parallel `ingest-file` + `ingest-commit`
> cycles** — that breaks the body-form rule and leaves N disjoint L1 pages
> with no album structure.

## CLI palette

```bash
# Two-phase prose flow
xu ingest-file   --wiki <w> --file <abs> [--node-path <p>]   # Phase 1: parse → pending
xu ingest-commit --wiki <w> --pending <f> --title <t> \
                      [--content-type article|table|gallery] \
                      [--node-path <p>] [--relations '<json>'] \
                      [--native '<md>'] --source <abs-path> [--author <a>]
                      # NOTE: --source is required when using --native

# Album single-shot flow
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
| `--vision` | no | Flag that user wants per-photo captions; sets intent even if backend absent |
| `--captions` | no | Pre-computed captions as JSON; if absent, vision backend runs at view time |
| `--author` | no | L1 frontmatter author field |

## Workflow — prose / document (PDF / DOCX / MD / image)

1. **Confirm wiki exists and file is absolute** (rule 8, rule 9 in `SKILL.md`).
2. **Phase 1 — `ingest-file`**: computes SHA256 → Level-2 dedup check (Phase 1,
   before calling any parser) → if duplicate, returns warning immediately
   (no parser called, no money spent). If unique: parses via MinerU →
   markitdown chain → writes a temp file to the system temp directory.
   Returns the temp file path in `data.pending`. No node is created at this stage.
3. **Agent synthesizes all metadata** from the temp file:
   title, node_path, relations, content_type — all LLM-generated, never asked
   of the user. `--title` is required by CLI but the value comes from the LLM.
4. **取证副本**: after `ingest-commit` succeeds, the CLI copies
   the source file to `raws/<node_path>/<original_name>` (first page only).
   **This is mandatory for all document types** — `.md / .pdf / .docx / .pptx`
   must all be physically stored. The response `data.created[].raw_path` should
   be non-null. If it is null, the copy step was bypassed — stop and investigate.
   > **Exception**: `--native` mode has no source file (agent-synthesized text),
   > so `raw_path` is null by design. But `--native` still requires `--source`
   > (a reference path) for dedup. Use `--pending` for any external document.
5. **Phase 2 — `ingest-commit --pending <f> --title <t>`**: promotes temp file
   to L1. All intermediate values (content_type, node_path, relations, author)
   are synthesized by the LLM and passed as CLI arguments.
6. **Page splitting notice**: if `data.page_count > 1`, tell the user
   "文档较长，已自动按容量分片为 N 个 L1 节点"。This is normal behavior, not an error.
7. **Verify raws/**: after commit, confirm `raw_path` in the response is non-null.
   An empty `raws/` directory with populated `nodes/page/` = copy was
   bypassed (usually from `--native` on a document).
8. **(Optional) Wire relations** with `query-relation add`.
9. **(Optional) Group into L2/L3** with `list create` / `report create`.

## Workflow — album (multiple images, one theme)

1. **Verify files**: all `--files` must be absolute paths to images.
2. **Ask vision intent**: "需要每张照片的 AI 描述吗？" — set `--vision` if yes
   (never decide for the user).
3. **Single-shot `ingest-album`**: writes ONE L1 page with a markdown
   table (or list if `--layout list`). Album theme = `--title`.
4. **(Optional) Wire relations / group** as in prose flow.

## Workflow — code block / terminal output

1. **`ingest-commit --native "<code>" --source <abs-path>`**: skips Phase 1 (no parse),
   goes through dedup / patches v1 / IDF directly. `--source` is required even
   for `--native` (for Level-2 dedup via source_hash).
   > **Warning — bypass**: `--native` has **no physical source file**
   > (it is agent-synthesized text), so `raw_path` in the response is null by
   > design. **Do NOT use `--native` for external `.md / .pdf / .docx / .pptx`
   > ingestion** — that silently skips the raws/ forensic copy. Use the
   > `--pending` path (Phase 1 + Phase 2) for any external document.

## Phase 1 temp file lifecycle

Phase 1 writes to a **system temp file** (not `nodes/pending/`). The temp file
path is returned in `data.pending` of the `ingest-file` response. Its lifecycle:

| Event | What happens |
|---|---|
| `ingest-file` runs | Creates temp file via `tempfile.gettempdir()` (e.g. `/tmp/<stem>-pre.md`) |
| `ingest-commit` succeeds | CLI deletes temp file immediately |
| `ingest-commit` fails | Temp file **retained** for debug / retry |
| Any leftover temp file after success | **Bug** — fix the error and re-run `ingest-commit` to trigger deletion |

**There is no `nodes/pending/` directory.** The two-phase separation is achieved
by the system temp file; no wiki-internal staging directory exists.

## Reorganize — move a page to a different partition

If the user is dissatisfied with a page's location after ingest, **never delete
and re-ingest**. Use `xu reorganize`:

```bash
xu reorganize --wiki <w> --uid <uid> --new-node-path certificates/qsa
# → nodes/page/old/slug.md  →  nodes/page/certificates/qsa/slug.md
# → raws/old/file.pdf         →  raws/certificates/qsa/file.pdf
# → DB node_path updated atomically
```

This is atomic: nodes/ + raws/ + DB are all updated in one transaction. No
content is re-parsed; the page body and all metadata are preserved.

When to call reorganize:
- User says "move this to X folder"
- `doctor-node-path-organization` reports the page is at root with no organization
- Agent decides the page belongs in a different logical partition after review

## Post-commit reflection

After **every** `ingest-commit` (single page, album, or batch), the agent runs
a creation-value reflection **before declaring the task done**. LLM decides
autonomously — no user approval needed. The CLI does not run this reflection
The CLI does not run this reflection and never auto-creates.

**Step 1 — Find similar List (mandatory, before any creation decision):**
Run a query to find existing Lists that overlap with the new page(s) on
dimension or members. If one exists → call `list create` with existing +
new members combined (extend the existing List). Do not ask the user.

**Step 2 — Assess List value (only if no similar found):**
- Did this ingest add ≥ 1 page comparable to ≥ 1 existing L1 on an obvious
  axis (parameter count / accuracy / date / location / category / model family / phase)?
- Or did this ingest add ≥ 2 pages sharing an obvious dimension?
- Would a Node_List save future "find me the X" queries or prevent duplication?
→ If yes: call `list create` autonomously. Do not ask the user.

**Step 3 — Report valuation (SECONDARY, opportunistic):**
Only if the new page clearly contradicts or forces re-evaluation of an
existing Report. Otherwise, by default, do not propose Report after ingest.

**Single-page ingest also triggers this reflection** — "just one page" is not
an excuse; the value can be "this page joins an existing group".

This section is the **ingest-side counterpart** to the query-side reflection
in `query.md §Workflow` step 5. Same asymmetric bias (List primary after
ingest, Report primary after query), opposite default type.

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

### Multi-file serial ingest

When ingesting N files, repeat the two-phase cycle **per file** — serial, not parallel:

```bash
# File 1
xu ingest-file --wiki <w> --file /abs/path/to/a.pdf
# Agent reads temp file, decides title/node_path/relations, then:
xu ingest-commit --wiki <w> --pending <temp_a.md> --title a ...
xu ingest-verify --wiki <w> --uid <uid_from_commit_a>
# Only proceed if ingest-verify passes; fix and re-commit if it fails

# File 2
xu ingest-file --wiki <w> --file /abs/path/to/b.pdf
xu ingest-commit --wiki <w> --pending <temp_b.md> --title b ...
xu ingest-verify --wiki <w> --uid <uid_from_commit_b>

# ... repeat for each file
```

**Rule**: if `ingest-verify` fails for any file, stop and fix that node before moving to the next. Do not skip a failed verify and continue the batch.

## Common pitfalls

- **Wrong body form** — applying `ingest-file` to an album produces N
  disjoint L1 pages with no album structure. Always confirm form first.
- **Deciding vision for the user** — if the user didn't say, ASK. Setting
  `--vision` when the build has no vision backend records the intent
   but does NOT crash. This is the right way to defer.
- **Splitting an album** — never call `ingest-file` N times then
  `ingest-commit` N times for an album. Use `ingest-album` once.
- **Editing the L1 body after commit** — the L1 markdown is immutable
   (L1 is immutable; see hard rule 1 in `SKILL.md`). To "add another photo to
  the album", use `ingest-album` with a fresh call targeting the existing
  node-path — this creates a new L1 node; there is currently no CLI
  for appending photos to an existing album node.
- **Empty raws/ despite L1 pages** — if `nodes/page/` has content but
   `raws/` is empty, the copy step was bypassed (usually from using `--native`
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

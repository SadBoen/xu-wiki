# ingest — add content to a wiki

`/xu-wiki ingest` adds content to a wiki as **L1 Node_Page** (immutable). It
is the most complex SOP because L1 body style **must match the content
type** (PRIN-ING-13). The first question to the user is always: **what body
form does this content want?**

This file is **self-contained** (PRIN-SKILL-1). Cross-cutting rules
(L1 immutability, 4-key JSON, missing-args, paths-must-be-absolute) live in
`SKILL.md`; the body-form decision tree lives here because it only applies
to ingest.

## Hard rule for this SOP (PRIN-ING-13)

> **Ask content-form first; route to the right flow.**
>
> When the user wants to ingest content, the **first** question is the body
> form: "table (album) / prose (document) / code block (snippet)?"
> Each form has a fixed CLI route:
>
> - **table / album** (multiple images, one themed page) →
>   `xu ingest-album` (single-shot, PRIN-ING-14). Body is a markdown
>   table with one row per photo (Filename / Path / Resolution / GPS /
>   Captured / Description). The album theme IS the L1 title.
> - **prose** (PDF / DOCX / MD / text / single image) →
>   `ingest-file` → `ingest-commit` (PRIN-ING-1 two-phase).
> - **code block / terminal output** →
>   `ingest-commit --native "<code block>"` (no parse, but still
>   goes through the commit pipeline including dedup / patches v1 / IDF).
>
> Never split a single album into N parallel `ingest-file` + `ingest-commit`
> cycles — that breaks the body-form rule and leaves N disjoint L1 pages
> with no album structure. The L1 body style MUST match the content type;
> `template` is just a frontmatter label, the body is the file content.
> For albums, the agent should also ask "vision per-photo? (yes/no)"
> BEFORE calling — if the user wants per-photo captions and the build
> has no vision backend, set `--vision` so the intent is recorded
> (PRIN-SOP-7). Never decide for the user.

## CLI palette

```bash
# Two-phase prose flow (PRIN-ING-1)
xu ingest-file   --wiki <w> --file <abs> [--node-path <p>]   # Phase 1: parse → pending
xu ingest-commit --wiki <w> [--pending <f>] [--title <t>] [--node-path <p>] \
                      [--template article|table|gallery] [--digest <d>] \
                      [--relations '<json>'] [--native '<md>'] [--author <a>]

# Album single-shot flow (PRIN-ING-14)
xu ingest-album  --wiki <w> --title <t> --files <abs1,abs2,...> \
                      [--node-path <p>] [--layout table|list] [--vision] \
                      [--captions '<json>'] [--digest <d>] [--author <a>]

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
| `--node-path` | no | Where in the wiki tree to place the page; user-specified preferred, else LLM judges |
| `--layout` | no | `table` (default) or `list` |
| `--vision` | no | Flag that user wants per-photo captions; sets intent even if backend absent (PRIN-SOP-7) |
| `--captions` | no | Pre-computed captions as JSON; if absent, vision backend runs at view time |
| `--digest` | no | One-paragraph summary for the L1 page frontmatter |
| `--author` | no | L1 frontmatter author field |

## Workflow — prose / document (PDF / DOCX / MD / image)

1. **Verify content-form** with the user (rule above): "this is prose, OK?"
2. **Verify wiki + file** (rule 8, rule 9 in `SKILL.md`). Wiki must exist;
   `--file` must be absolute.
3. **Phase 1 — `ingest-file`**: parses the file via the offline-first
   fallback chain (MinerU → markitdown → text → image, CONST-ING-1) and
   writes a pending file. Returns the pending file path.
4. **取证副本 (PRIN-ING-6)**: after `ingest-commit` succeeds, the CLI copies
   the source file to `raws/<node_path>/<original_name>` (first page only).
   **This is mandatory for all document types** — `.md / .pdf / .docx / .pptx`
   must all be physically stored. The response `data.created[].raw_path` should
   be non-null. If it is null, PRIN-ING-6 was bypassed — stop and investigate.
   > **Exception**: `--native` mode has no source file (agent-synthesized text),
   > so `raw_path` is null by design. But `--native` still requires `--source`
   > (a reference path) for dedup. Use `--pending` for any external document.
5. **(Optional) Review the pending file** with `read --wiki W --uid <pending-uid>`.
6. **Phase 2 — `ingest-commit`**: promotes pending to L1. Required:
   `--title`. Optional: `--template`, `--node-path`, `--relations`,
   `--digest`, `--author`.
7. **Verify raws/**: after commit, confirm `raw_path` in the response is non-null.
   An empty `raws/` directory with populated `nodes/page/` = PRIN-ING-6 was
   bypassed (usually from `--native` on a document).
8. **(Optional) Wire relations** with `query-relation add`.
9. **(Optional) Group into L2/L3** with `list create` / `report create`.

## Workflow — album (multiple images, one theme)

1. **Verify content-form**: "this is a table-form album, OK?"
2. **Verify vision intent** (rule above): "want per-photo captions? yes/no"
3. **Verify files**: all `--files` must be absolute paths to images.
4. **Single-shot `ingest-album`**: writes ONE L1 page with a markdown
   table (or list if `--layout list`). Album theme = `--title`.
5. **(Optional) Wire relations / group** as in prose flow.

## Workflow — code block / terminal output

1. **Verify content-form**: "this is a code block, OK?"
2. **Single `ingest-commit --native "<code>"`**: skips Phase 1 (no parse),
   goes through dedup / patches v1 / IDF directly.
   > **Warning — PRIN-ING-6 bypass**: `--native` has **no physical source file**
   > (it is agent-synthesized text), so `raw_path` in the response is null by
   > design. **Do NOT use `--native` for external `.md / .pdf / .docx / .pptx**
   > ingestion** — that silently skips the raws/ forensic copy. Use the
    > `--pending` path (Phase 1 + Phase 2) for any external document.

## Pending lifecycle (PRIN-ING-7)

`nodes/pending/` is the Phase 1 staging area. Its lifecycle:

| Event | What happens |
|---|---|
| `ingest-file` runs | Creates `nodes/pending/<name>-pre.md` |
| `ingest-commit` succeeds | CLI deletes pending file immediately (PRIN-ING-7) |
| `ingest-commit` fails | Pending file **retained** (debug / retry evidence) |
| Any残留 | **Bug** — run `xu doctor-all --wiki W` to detect |

**An empty `nodes/pending/` directory after a successful ingest is correct.
A non-empty directory is a signal that something went wrong mid-flow.**

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
# → {"status": "success", "data": {"pending": ".../pending/2026-ABCD.json"}, ...}
xu ingest-commit --wiki research \
  --title "BERT: Pre-training of Deep Bidirectional Transformers" \
  --template article --digest "Masked LM + NSP pre-training achieves SOTA on 11 NLP tasks."
# → {"status": "success", "data": {"uid": "2026-WXYZ5678", "title": "BERT: ..."}, ...}
```

## Example — album

```bash
xu ingest-album --wiki research \
  --title "SGW001 #1 完工照片" \
  --files ~/uploads/001.jpg,~/uploads/002.jpg,~/uploads/003.jpg \
  --vision
# → {"status": "success", "data": {"uid": "...", "rows": 3}, ...}
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
- **`nodes/pending/` has leftover files** — pending files should not exist
  after a successful `ingest-commit` (PRIN-ING-7). If they do, something
  crashed mid-flow. Run `xu doctor-all --wiki W` to detect and fix.

## Cross-references

- Cross-cutting rules (immutability, JSON, paths, missing-args) → `SKILL.md §Hard rules`
- The `query` and `read` CLIs (for verifying the ingest) → `SKILL.md §SOP map` (query SOP)
- The 50-edge LRU semantics → `SKILL.md §Architecture in 30 seconds`
- Full ingest architecture → `design-docs/05-ingest.md`

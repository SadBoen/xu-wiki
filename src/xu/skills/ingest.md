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
>   `xu-wiki ingest-album` (single-shot, PRIN-ING-14). Body is a markdown
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
xu-wiki ingest-file   --wiki <w> --file <abs> [--node-path <p>]   # Phase 1: parse → pending
xu-wiki ingest-commit --wiki <w> [--pending <f>] [--title <t>] [--node-path <p>] \
                      [--template article|table|gallery] [--digest <d>] \
                      [--relations '<json>'] [--native '<md>'] [--author <a>]

# Album single-shot flow (PRIN-ING-14)
xu-wiki ingest-album  --wiki <w> --title <t> --files <abs1,abs2,...> \
                      [--node-path <p>] [--layout table|list] [--vision] \
                      [--captions '<json>'] [--digest <d>] [--author <a>]

# Optional follow-up (still in the ingest SOP — wiring happens here)
xu-wiki query-relation add  --wiki <w> --from-uid <uid> --to-uid <uid> \
                            --relation-name <r> [--comment <c>]
xu-wiki list create --wiki <w> --title <t> --members <uid,uid,...> \
                    [--dimension <d>] [--node-path <p>]
xu-wiki report create --wiki <w> --title <t> --body <md> \
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
4. **(Optional) Review the pending file** with `read --wiki W --uid <pending-uid>`.
5. **Phase 2 — `ingest-commit`**: promotes pending to L1. Required:
   `--title`. Optional: `--template`, `--node-path`, `--relations`,
   `--digest`, `--author`.
6. **(Optional) Wire relations** with `query-relation add`.
7. **(Optional) Group into L2/L3** with `list create` / `report create`.

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

## Example — prose

```bash
xu-wiki ingest-file   --wiki research --file ~/Downloads/bert.pdf
# → {"status": "success", "data": {"pending": ".../pending/2026-ABCD.json"}, ...}
xu-wiki ingest-commit --wiki research \
  --title "BERT: Pre-training of Deep Bidirectional Transformers" \
  --template article --digest "Masked LM + NSP pre-training achieves SOTA on 11 NLP tasks."
# → {"status": "success", "data": {"uid": "2026-WXYZ5678", "title": "BERT: ..."}, ...}
```

## Example — album

```bash
xu-wiki ingest-album --wiki research \
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

## Cross-references

- Cross-cutting rules (immutability, JSON, paths, missing-args) → `SKILL.md §Hard rules`
- The `query` and `read` CLIs (for verifying the ingest) → `SKILL.md §SOP map` (query SOP)
- The 50-edge LRU semantics → `SKILL.md §Architecture in 30 seconds`
- Full ingest architecture → `design-docs/05-ingest.md`

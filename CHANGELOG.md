# Changelog

## Unreleased

### Skill documentation: ingest SOP clarity

Five issues identified during real-world ingest session (NepTune/SGW001 — LITA QUEST
vessel specifications) where the agent followed the docs literally and produced an
orphan Page. Fixes below make `node_path` ownership, hint semantics, and verify
check severity unambiguous so a careful agent reading the docs is not misled.

- **`node_path` is Phase 2's responsibility, not Phase 1's**: `ingest.md` now opens
  with a dedicated "node_path: which phase owns it" section. `ingest-file --node-path`
  is documented as a no-op (only validates format, never persists or propagates).
  Phase 2 (`ingest-commit`) is the **only** command that decides the directory
  layout. The OMISSION RULE in the same section mandates `--node-path` for any
  source with a "ship name / project / category" semantic.
- **Phase 2 CLI example promotes `--node-path` to the visible signature**: the
  `xu ingest-commit` template now shows `--node-path <p>` as a primary argument
  (not a hidden optional), and includes a hard reminder that omitting it creates
  an orphan node. `--relations '<json>'` is also added to the visible signature.
- **6-checks severity table**: `ingest.md` now lists every check's `pass` /
  `warning` / `skip` / `fail` semantics. `raw_path_node_path_mirror: skip` is
  explicitly called out as a **post-mortem signal** (node landed at
  `nodes/pages/` root), not a green light. A 4-step recovery recipe
  (`delete-node` → re-`ingest-file` → re-`ingest-commit` with `--node-path` →
  re-`ingest-verify`) is documented inline. `xu doctor-node-path-organization`
  is mentioned as the batch alternative.
- **`hints` field semantics clarified in `SKILL.md`**: previously described as
  "reference for Agent's next step" (suggesting pre-flight advice); now
  described as **post-mortem deferred-work signals** (telling the agent what
  cleanup the just-completed command left behind). The wording is tightened
  with a "hints is todo list, not advisory" rule to prevent the agent from
  reading successful-response hints as future suggestions.
- **New `wire` SOP entry in `SKILL.md`**: explicit `/xu-wiki wire` row in the
  SOP table, even though it has no dedicated `references/wire.md` — it points
  readers at `ingest.md`'s "Reflection triggers" block. A new "Reflection
  trigger" line for **Entity describes chaining** is added (previously only
  List / Report overlap was mentioned), so a new Page matching an existing
  Entity is wired automatically. SOP-call discipline at session end:
  `xu doctor-node-path-organization` for hygiene, `xu query` to find related
  Entities for describe chaining.

### Tooling baseline

- **Lint/format baseline**: applied `ruff format` across `src/` and `tests/`
  (38 files reformatted, no semantic changes). Pre-commit hook ruff version
  bumped from `v0.4.0` → `v0.15.20` to match the locally installed ruff,
  which fixes the format loop where hook and CLI disagreed.
- **Type-check baseline**: mypy now passes clean (0 errors) on `src/`. Fixes:
  - `src/xu/commands/ingest.py`: annotate Pillow `Image.open(...).convert(...)`
    return with `# type: ignore[assignment]` (Pillow stub types `Image` vs
    `ImageFile` more strictly than the runtime).
  - `src/xu/parsers/image_meta.py`: annotate `exif` as `Any` to satisfy
    `var-annotated` rule.
- **Test imports**: removed unused imports across the test suite
  (`tempfile` in `test_config.py` / `test_core.py`; `tempfile` redefined in
  `test_uninstall.py` collapsed to a single top-level import; `subprocess`
  in `test_logging.py`; `now_ts` in `test_layers.py`; `SKILL_SRC_DIR` in
  `test_deploy_skill.py`; `album_mod` in `test_logging.py`). Removed unused
  local `list_uid` in `tests/test_layers.py`.

### Install/Uninstall Redesign

- **Skill bundle deployment**: `xu deploy skill --target <agent>` now defaults to symlink
  instead of copy. Canonical skill source is at `~/.local/share/xu-wiki/skills/`.
  Agent harness paths (`~/.hermes/skills/xu-wiki/`, etc.) symlink to the canonical
  source. Use `--copy` for environments that do not support symlinks.

- **Deployment manifest**: `xu deploy skill` writes `~/.local/share/xu-wiki/manifest.json`
  tracking every deployment (agent, path, mode, install time). `xu uninstall` reads
  this manifest to cleanly reverse each deployment.

- **Uninstall is a single command**: `xu uninstall --target <agent> --execute` now handles
  all three surfaces internally — pip/pipx package, skill bundle (per manifest),
  and `~/.xu-wiki/` config. The old two-step README flow (manual `pipx uninstall` as
  separate step) is retired.

- **pipx uninstall automated**: `xu uninstall --execute` inside a pipx-managed venv now
  calls `pipx uninstall xu-wiki` automatically instead of returning a `next_action`
  hint that agents frequently skipped.

- **Extras completeness**: `pyproject.toml` now includes all four extras
  (`pdf`, `parse`, `nlp`, `vision`, `all`). PDF text extraction (`pdf` extra,
  `pypdf` + `pdfplumber`) was previously missing from the extras table.

- **`MissingExtra` guard**: `xu ingest-file` now raises `MissingExtra` immediately
  when called on a PDF/DOCX/PPTX file and the `markitdown` package is not
  installed. No silent fall-back to empty parse result.

- **Uninstall CLI flags**: Added `--target` (multi, agent harness), `--keep-skill`.
  `--preserve-config` and `--keep-pip` retained.

- **Dry-run plan is human-readable**: `xu uninstall` (dry-run) now prints a
  formatted plan to stdout before returning the JSON envelope.

- **Wiki data is a hard invariant**: Wiki data (registered wiki directories) is
  never deleted under any combination of flags.

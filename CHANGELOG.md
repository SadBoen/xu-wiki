# Changelog

## Unreleased

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

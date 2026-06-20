# Changelog

## Unreleased

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
  `--preserve-config` and `--keep-pip` retained. `--purge-wikis` accepted but
  ignored — wiki data is never deleted regardless.

- **Dry-run plan is human-readable**: `xu uninstall` (dry-run) now prints a
  formatted plan to stdout before returning the JSON envelope.

- **Wiki data is a hard invariant**: Wiki data (registered wiki directories) is
  never deleted under any combination of flags. `--purge-wikis` is a no-op.

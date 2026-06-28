# update — upgrade xu-wiki

Upgrade xu-wiki to the latest version and re-deploy skill bundles.

**Wiki data is NEVER touched.** pip upgrade is in-place; `~/.xu-wiki/` config is preserved.

## CLI palette

```bash
xu update                    # upgrade pip package + re-deploy skills to all manifest targets
xu update --check            # check PyPI for newer version, no side effects
xu update --no-redeploy      # only upgrade pip package, skip skill re-deploy
```

## Workflow — update

**Step 1 — check (optional):**
```bash
xu update --check
```
Reports `{status, data: {current, latest, update_available}}`. If `update_available: true`, proceed.

**Step 2 — upgrade:**
```bash
xu update
```
1. pip upgrade (pipx or pip, auto-detected)
2. Re-deploy skill bundle to every agent target in manifest

**Step 3 — verify:**
```bash
xu selfcheck
```

## Workflow — update without skill re-deploy

```bash
xu update --no-redeploy
```
Useful when skill files haven't changed and you want a faster update.

## How it works

- **pip upgrade**: `pipx upgrade xu-wiki` (pipx install) or `pip install --upgrade xu-wiki` (pip install)
- **Skill re-deploy**: reads `~/.local/share/xu-wiki/manifest.json` → deploys updated skill files to each agent target
- **Version check**: fetches latest from PyPI JSON API (`https://pypi.org/pypi/xu-wiki/json`)

## Safety table

| Command | Wiki data? | pip pkg? | Skill bundles? | ~/.xu-wiki/? |
|---|---|---|---|---|
| `update --check` | never | never | never | never |
| `update` | never | upgraded in-place | re-deployed | preserved |
| `update --no-redeploy` | never | upgraded in-place | skipped | preserved |

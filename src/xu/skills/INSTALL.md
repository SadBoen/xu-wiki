# xu-wiki post-install checklist

This file ships in the skill bundle. The Agent loads it alongside
SKILL.md / create.md / ingest.md / query.md / doctor.md / config.md /
reference/error-catalog.md / reference/pitfalls.md. When a user says
"install xu-wiki" or "uninstall xu-wiki", work through this list — do
not skip steps based on what `xu selfcheck` reports.

> **Why this file exists**: `xu selfcheck` is a *package* self-test,
> not a *deployment* verification. It can report all green while the
> user's Agent can't find the skill. The Agent is the only thing that
> knows which discovery directory the user is on, so the deployment
> step must be Agent-driven and Agent-verified.

---

## Install (user says "装 xu-wiki" / "install xu-wiki")

### 1. Pick the install surface

| Step | Command (in the agent's bash tool) | Pass criterion |
|---|---|---|
| 1a | `python3 -c "import sys; print(sys.version_info >= (3, 10))"` | prints `True` |
| 1b | `pip --version` | exits 0 |

### 2. Bootstrap venv if PEP 668 system

Skip this step if the user's Python is non-PEP-668 (macOS pre-3.12,
custom builds). Otherwise:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
```

If `python3 -m venv` complains about `ensurepip`, tell the user to
install `python3-venv` via apt / dnf / brew.

### 3. Install the package

```bash
.venv/bin/pip install "xu-wiki[parse,nlp,vision]"
```

(The agent always uses the absolute `.venv/bin/xu` path; do NOT add
to global PATH unless the user explicitly asks.)

### 4. Verify package-level health

```bash
.venv/bin/xu --version
# → "xu-wiki 0.1.0"
.venv/bin/xu selfcheck
# → status in {success, warning} with checks.agent_skill_deployed.ok = false
#    (expected: the skill isn't deployed yet)
```

`xu selfcheck` will show `agent_skill_deployed.ok = false` at this
point. That is **expected**, not a bug — the next step deploys it.

### 5. Deploy the skill to the agent's discovery dir

Pick the destination per the user agent:

| Agent | Discovery dir |
|---|---|
| Hermes | `~/.hermes/skills/xu-wiki/` |
| Trae IDE | `<project>/.trae/skills/xu-wiki/` (project-local) |
| Claude Desktop | `~/Library/Application Support/Claude/skills/xu-wiki/` (macOS) |
| Cursor | `<project>/.cursor/skills/xu-wiki/` (project-local) |

Then run (Hermes example; substitute the destination):

```bash
SRC=$(.venv/bin/xu skills path | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['source_dir'])")
DEST="$HOME/.hermes/skills/xu-wiki"
mkdir -p "$DEST"
cp -r "$SRC/." "$DEST/"
ls "$DEST"            # 6 top-level files (SKILL + 5 SOP)
ls "$DEST/reference"  # 2 reference files
```

> **Common mistake**: `cp -r "$SRC" "$DEST"` (without trailing `/.`)
> creates `$DEST/xu/skills/...` — wrong. Always write `$SRC/.`.

### 6. Verify deployment

```bash
.venv/bin/xu selfcheck
# → status = success; checks.agent_skill_deployed.ok = true
```

If still `agent_skill_deployed.ok = false`, you copied to the wrong
dir; re-check step 5's table. You can also override the probe with:

```bash
XU_AGENT_SKILL_DIR=/path/to/custom/skill .venv/bin/xu selfcheck
```

### 7. End-to-end smoke

```bash
.venv/bin/xu create --name smoke --path /tmp/xw-smoke --alias s
.venv/bin/xu wikis
.venv/bin/xu unregister --name smoke
```

All three should return `status: success`. If any fails, see
[reference/error-catalog.md](reference/error-catalog.md).

### 8. Tell the user

In the agent's reply: "Installed xu-wiki X.Y.Z; deployed the skill
to <agent>; smoke test passed." Do NOT paste raw JSON; translate.

---

## Uninstall (user says "卸 xu-wiki" / "uninstall xu-wiki")

Always go through the `/xu-wiki config` SOP → `xu uninstall`. Never
call `pip uninstall` directly via the bash tool — that bypasses
SKILL.md discoverability and the dry-run safety contract.

### 1. Dry-run first

```bash
.venv/bin/xu uninstall
```

Show the user `data.wikis_found` (every registered wiki) and the
3 scope options:

| Scope | Flags | What it removes |
|---|---|---|
| (a) pip only | `--execute` | pip package only — wiki data + `~/.xu/` preserved |
| (b) pip + wikis | `--execute --purge-wikis` | pip + every registered wiki dir |
| (c) nuclear | `--execute --purge-wikis --purge-config` | pip + wikis + `~/.xu/` |

**Folding rule (rule 9)**: if `data.wikis_found == []`, scopes (a)
and (b) are functionally identical (no wikis to purge). Do not list
three options when one is a no-op for the user's data — collapse to
"a (or b; same effect when no wikis) or c".

### 2. Confirm with the user

Default to scope (a). User must explicitly type "yes" / "确认" /
"proceed" before any `--execute` runs (PRIN-UNINST-6).

### 3. Execute

```bash
.venv/bin/xu uninstall --execute [--purge-wikis] [--purge-config]
```

### 4. Remove the skill from the agent's discovery dir

The agent uses its own skill manager (NOT `xu uninstall`):

- Hermes: `rm -rf ~/.hermes/skills/xu-wiki` + reload skills
- Trae: `rm -rf <project>/.trae/skills/xu-wiki`
- Claude Desktop: `rm -rf ~/Library/Application\ Support/Claude/skills/xu-wiki` + restart app
- Cursor: `rm -rf <project>/.cursor/skills/xu-wiki`

### 5. Independent verification (rule 7, P0)

After `--execute`, **DO NOT trust the CLI's word**. Run these
independent checks in your bash tool:

```bash
# 5a. pip uninstall: confirm 'xu' command no longer exists
command -v xu || echo "OK: xu removed"
# Expected: prints "OK: xu removed" or empty (with non-zero exit)

# 5b. --purge-wikis: confirm every removed path actually gone
# Read paths from data.result.wikis.removed[*].path in the response
test -e /path/from/response && echo "FAIL: wiki still exists" || echo "OK"
# Do this for EACH removed path.

# 5c. --purge-config: confirm ~/.xu/ actually gone
test -e ~/.xu && echo "FAIL: ~/.xu still exists" || echo "OK: ~/.xu removed"

# 5d. cross-check the CLI's reported counts
# If response said "files_removed_count=12" but your ls only found 8,
# something is wrong.
```

**Contradiction rule (rule 8)**: if any check contradicts the CLI
report — for example, the CLI says `config_dir.ok = true` and
`existed_before = true` but `~/.xu/` is still on disk — surface
this to the user in plain language. Do NOT report "卸载完成" if
independent verification failed.

### 6. Tell the user

Only after verification passes, reply: "Uninstalled xu-wiki X.Y.Z;
removed from <agent>." Do not paste raw JSON or pip stdout.

---

## Pitfalls

- **Do not skip step 5** because `pip install` succeeded. Pip only
  installs the *package*; the Agent needs the skill deployed to its
  discovery dir.
- **Do not write `cp SRC DEST`** (no `-r`): the bundle has a
  `reference/` subdirectory and the file list is relative. Without
  `-r`, the two reference files end up at the wrong path.
- **Do not trust `xu selfcheck` alone**. Even if all checks pass, the
  deployment step must be run separately (steps 5–6 above).
- **Do not assume `pip uninstall`** works the same way. Always route
  through `xu uninstall` so the dry-run contract and
  `is_wiki_root()` safety check (3.1) kick in.
- **Do not paste the 4-key JSON at the user**. Translate to natural
  language per SKILL.md hard rule 0.

See also: [SKILL.md](SKILL.md), [reference/pitfalls.md](reference/pitfalls.md).
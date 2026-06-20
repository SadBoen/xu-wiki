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
| 1b | `command -v pipx` | exits 0 (preferred path) |
| 1c | `command -v pip` | exits 0 (alternative path) |

If `pipx` is unavailable, tell the user to install it
(`apt install pipx`, `brew install pipx`, or `python3 -m pip
install --user pipx`). pipx is strongly preferred — it handles PEP
668, venv creation, and `~/.local/bin` symlink in one command.

### 2. Ensure PATH is set up

```bash
pipx ensurepath
```
`pipx install` puts the `xu` symlink in `~/.local/bin`. If that dir is not on
PATH, `xu` won't be found even though install succeeded. `pipx ensurepath`
adds it to your shell profile — **open a new shell** (or re-source your
profile) afterward so the change takes effect. The fact-based gate is Stage 4:
`xu --version` must print `xu-wiki 0.1.0` before you continue.

### 3. Install the package (PREFERRED — pipx)

```bash
pipx install "xu-wiki[parse,nlp,vision] @ git+https://github.com/SadBoen/xu-wiki.git"
```

**Syntax warning**: use PEP 508 `name[extra] @ git+URL`, NOT the
deprecated `git+URL#egg=name[extra]`. Modern pip rejects the latter
as `invalid-egg-fragment`.

If the user later upgrades, use `pipx upgrade xu-wiki` — same
one-liner, no migration needed (the venv and symlink layout are
identical between git+URL and PyPI installs).

### 3-alt. Install the package (ALTERNATIVE — pip + venv)

If pipx is unavailable or the user explicitly wants pip:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install "xu-wiki[parse,nlp,vision]"
```

(Always use the absolute `.venv/bin/xu` path; do NOT add to global
PATH unless the user explicitly asks.)

### 3. Verify package-level health

```bash
# pipx users:
xu --version
# → "xu-wiki 0.1.0"
xu selfcheck
# → deployment_status.installer == "pipx"
# → status in {success, warning} with checks.agent_skill_deployed.ok = false
#    (expected: the skill isn't deployed yet — step 4 handles it)

# pip+venv users (use absolute path until activate):
.venv/bin/xu --version
.venv/bin/xu selfcheck
```

### 4. Deploy the skill to the agent's discovery dir

This step requires the agent — only the agent knows its own
discovery directory. Use `xu deploy skill --target <agent>`:

```bash
# pipx users:
xu deploy skill --target hermes
xu deploy skill --target trae       # project-local
xu deploy skill --target claude     # macOS only
xu deploy skill --target cursor     # project-local
xu deploy skill --target auto       # probe existing dirs, deploy to first match

# pip+venv users:
.venv/bin/xu deploy skill --target hermes
```

`auto` resolves to whichever target's parent directory already
exists on the machine — meaning that agent is installed there. If
none match, `auto` falls back to `hermes`.

**Don't write `cp -r` by hand.** The deploy command handles three
things the manual flow gets wrong:

1. Preserves the `reference/` subdir (per-file copy with relative paths).
2. Filters out Python artifacts (`__init__.py`, `__pycache__/`) so
   they don't leak into the agent's discovery dir.
3. Maps `--target` to the right discovery dir for each agent platform.

### 5. Verify deployment

```bash
xu selfcheck
# → checks.agent_skill_deployed.ok = true
# → deployment_status.skill_deployed_to == ["hermes"]
# → next_actions == []   ← the high-signal "nothing left to do"
```

If `next_actions` is non-empty, walk the list before declaring
"install complete" — each entry is something still left undone
(reload agent, fix permissions, install missing extras, etc.).

### 6. End-to-end smoke

```bash
xu create --name smoke --path /tmp/xw-smoke --alias s
xu wikis
xu unregister --name smoke
```

All three should return `status: success`. If any fails, see
[reference/error-catalog.md](reference/error-catalog.md).

### 7. Tell the user

In the agent's reply: "Installed xu-wiki X.Y.Z via pipx; deployed
the skill to <agent>; smoke test passed." Do NOT paste raw JSON;
translate.

---

## Uninstall (user says "卸 xu-wiki" / "uninstall xu-wiki")

Always go through the `/xu-wiki config` SOP → `xu uninstall`. Never
call `pip uninstall` directly via the bash tool — that bypasses
SKILL.md discoverability and the dry-run safety contract. In a
pipx-managed install, `pipx uninstall xu-wiki` is the canonical
program-body removal tool (NOT `pip uninstall`).

### 1. Dry-run first

```bash
xu uninstall --dry-run    # or just `xu uninstall` — dry-run is default
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

The execution flow depends on `data.plan.installer` from step 1.

**pipx users** (the typical case on Debian/Ubuntu/Fedora/Homebrew
after `pipx install`):

```bash
# 3a. xu uninstall cleans the DATA layer only (program body is pipx's job)
xu uninstall --execute --purge-wikis --purge-config

# 3b. pipx uninstall removes the PROGRAM body
pipx uninstall xu-wiki
```

If you accidentally call `xu uninstall --execute` and the response
says `data.installer == "pipx"`, the CLI will refuse to call
`pip uninstall` itself; it returns `next_action:
"pipx uninstall xu-wiki"` for the agent to act on. **Do not
substitute `pip uninstall xu-wiki` for `pipx uninstall`** — that
leaves a ghost venv in pipx's registry.

**pip+venv users**:

```bash
xu uninstall --execute --purge-wikis --purge-config
# (everything in one call: pip uninstall + data layer cleanup)
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
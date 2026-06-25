# doctor — health checks

```bash
xu doctor --wiki <w>
```

## Steps

1. `xu doctor --wiki <w>`
2. Read response: checks list with `ok: true/false`.
3. If all checks pass -> tell user.
4. If issues found -> report each failure. Do NOT auto-fix.

## Destructive operations

```bash
xu delete-node --wiki <w> --uid <uid>
```

Reference-safe. Deletes outgoing relations first, then the node itself. If the node is referenced by a List or Report, or is a relation target, the command refuses and returns all referrers.

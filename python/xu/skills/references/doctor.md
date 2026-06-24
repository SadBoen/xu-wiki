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
xu delete-node --wiki <w> --uid <uid> [--force]
```

Check references before deleting. If node is referenced by a List or Report -> refuse unless `--force`.

```bash
xu rebuild --wiki <w> --granularity keep-l1|keep-l1-l2|full
```

Rebuild derived layers (L2/L3). L1 never touched.

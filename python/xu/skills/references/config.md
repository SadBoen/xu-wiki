# config — registry + uninstall

## Wiki registry

```bash
xu wikis                        # list all registered
xu alias set --wiki <w> --alias <a>    # add/change alias
xu alias unset --wiki <w>              # remove alias
xu alias show --wiki <w>               # show current alias
xu register --name <n> --path <abs>    # register existing dir
xu unregister --name <n>               # deregister (no files touched)
```

## Global config

```bash
xu config set-mineru-key     # reads from MINERU_API_KEY env
xu config show               # show config (secrets masked)
```

## Uninstall

**Always dry-run first. Never skip.**

```bash
xu uninstall                  # dry-run (default)
xu uninstall --execute        # actually remove
xu uninstall --execute --preserve-config   # keep ~/.xu-wiki/
xu uninstall --execute --keep-pip          # keep pip package
```

Wiki data is NEVER deleted. No flag changes this.

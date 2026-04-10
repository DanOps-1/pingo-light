# pingo-light

Bash CLI tool for maintaining forks of open-source projects. Single file, zero dependencies beyond git + bash.

## Project structure

- `pingo-light` — The entire tool (single executable bash script, ~1300 lines)
- `install.sh` — Copies pingo-light to /usr/local/bin
- `llms.txt` — Complete reference documentation for LLM consumption

## How it works

User's customizations are maintained as a linear stack of git commits (patches) on a `pingo-patches` branch, rebased on top of an `upstream-tracking` branch that mirrors the upstream project. Each patch commit has the prefix `[pl] <name>:`. Syncing fetches upstream and rebases the patch stack. git rerere auto-remembers conflict resolutions.

## Development

No build step. Edit `pingo-light` directly. Test by running it in a git repo.

Quick test setup:
```bash
mkdir /tmp/test-upstream && cd /tmp/test-upstream && git init && echo "hello" > file.txt && git add -A && git commit -m "init"
git clone /tmp/test-upstream /tmp/test-fork && cd /tmp/test-fork
pingo-light init /tmp/test-upstream
```

## Key internals

- Config: `.pingolight` file (git-config format) with section `[pingolight]`
- Patch identification: commit messages matching `[pl] <name>: <desc>`
- Dry-run sync: creates temp branches `pl-dryrun-$$`, cleaned up after
- Doctor test: creates temp branch `pl-doctor-$$`, cleaned up after
- Patch resolution: by name (exact → partial match) or 1-based index

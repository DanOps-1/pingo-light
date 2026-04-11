# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

bingo-light is an AI-native fork maintenance tool. It manages customizations as a clean patch stack on top of upstream, with `--json` and `--yes` flags for AI agent consumption. Single bash script (~2500 lines) + MCP server (Python 3, 27 tools).

## Commands

```bash
make test          # run core test suite (tests/test.sh)
make lint          # shellcheck on bingo-light

# Full test pipeline (178 tests across 4 suites):
./tests/run-all.sh              # all suites + coverage report
./tests/test.sh                 # core functional tests
./tests/test-json.sh            # JSON fuzz with dangerous inputs
./tests/test-edge.sh            # git state boundary tests
python3 ./tests/test-mcp.py     # MCP protocol tests

# Run a single test section (by number):
# Not directly supported — run full suite. Tests take ~10s.

# Syntax check without running:
bash -n bingo-light
python3 -c "import py_compile; py_compile.compile('mcp-server.py', doraise=True)"
```

## Architecture

**bingo-light** (bash) — The entire CLI. All business logic lives here. Uses `set -euo pipefail`. Every command has two output paths: human-readable (default) and JSON (`--json` flag). JSON output uses `json_out()` + `json_escape()` (awk-based, POSIX-compatible). Config stored in `.bingolight` via `git config --file`.

**mcp-server.py** (Python 3, stdlib only) — Thin MCP wrapper over the CLI. Calls `run_bl()` which spawns `bingo-light --json --yes` as a subprocess. Adds `--json --yes` to ALL commands automatically. Has `try/except` around `handle_tool_call()` to prevent crashes from bad input. Uses Content-Length framed JSON-RPC 2.0 over stdio.

**agent.py** — Advisor agent. Observe → Analyze → Safe-act or Report. LLM is used for analysis ONLY, never code execution. Can run without API key (graceful degradation).

**tui.py** — Curses dashboard. Read-only status viewer with sync/dry-run.

## Critical patterns to follow when editing

**JSON output**: Every `json_out` call with a user-controlled variable MUST use `json_escape`:
```bash
# CORRECT:
json_out '{"ok":true,"name":"'"$(echo "$name" | json_escape)"'"}'
# WRONG (injection risk):
json_out '{"ok":true,"name":"'"$name"'"}'
```
Only exception: known integers (`$behind`, `$count`) and controlled constants (`$TRACKING_BRANCH`).

**JSON mode guard**: Every function that produces output MUST have a JSON mode path. No function should return 0 with empty stdout when `JSON_MODE=true`.

**Git output suppression**: All `git checkout`, `git branch -f`, `git commit`, `git rebase`, `git am` calls MUST use `&>/dev/null` to prevent stdout leaking into JSON output.

**No shell interpolation in python3 -c**: Pass data via stdin, not `$VAR` in the Python string:
```bash
# CORRECT:
printf '%s' "$var" | python3 -c "import sys; data=sys.stdin.read()"
# WRONG:
python3 -c "data='$var'"
```

**awk must be POSIX**: No gawk extensions. No 3-argument `match(s, r, array)`. Use `match()` + `substr()` + `sub()`.

**Conflict detection**: Use `git ls-files --unmerged | cut -f2 | sort -u`, NOT `git diff --name-only --diff-filter=U` (misses delete/modify and rename conflicts).

**Undo state**: sync saves `.bingo/.undo-head` + `.bingo/.undo-tracking`. Undo writes `.bingo/.undo-active` to prevent `_fix_stale_tracking()` from auto-advancing tracking. Sync clears `.undo-active`.

## Key internals

- Config: `.bingolight` (git-config format), excluded via `.git/info/exclude`
- Patch ID: commit messages matching `[bl] <name>: <desc>`
- Patch names: validated to `^[a-zA-Z0-9][a-zA-Z0-9_-]*$`
- Branches: `upstream-tracking` (mirror), `bingo-patches` (patches on top)
- MCP server version must match CLI VERSION (currently 1.2.0)
- `_fix_stale_tracking()`: auto-repairs tracking branch after manual conflict resolution, skipped if `.bingo/.undo-active` exists or rebase is in progress

## When adding a new command

1. Add the function in `bingo-light`
2. Add JSON output path with `json_out` + proper escaping
3. Add to `show_help()` function
4. Add to `main()` dispatch
5. Add to all 3 shell completions (`completions/*.bash`, `.zsh`, `.fish`)
6. Add to `llms.txt` command reference
7. Update README.md and README.zh-CN.md if user-facing

## When adding a new MCP tool

1. Add tool definition to `TOOLS` array in `mcp-server.py`
2. Add handler in `handle_tool_call()`
3. `run_bl()` auto-adds `--json --yes` — don't add them manually
4. Update MCP tool tables in README.md, README.zh-CN.md, CLAUDE.md
5. Update badge count if it changed

## For AI agents: prefer MCP or --json

```bash
bingo-light status --json
bingo-light sync --json --yes
bingo-light conflict-analyze --json
BINGO_DESCRIPTION="add feature X" bingo-light patch new feature-x --yes
```

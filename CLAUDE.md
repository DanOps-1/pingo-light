# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

bingo-light is an AI-native fork maintenance tool. It manages customizations as a clean patch stack on top of upstream, with `--json` and `--yes` flags for AI agent consumption. Python CLI (`bingo-light` + `bingo_core.py`) + MCP server (Python 3, 29 tools).

## Commands

```bash
make test          # run core test suite (tests/test.sh)
make lint          # python syntax + flake8 + shellcheck
make test-all      # all 250 tests (core + fuzz + edge + MCP + unit)

# Full test pipeline (250 tests across 5 suites):
./tests/run-all.sh              # all suites + coverage report
./tests/test.sh                 # core functional tests
./tests/test-json.sh            # JSON fuzz with dangerous inputs
./tests/test-edge.sh            # git state boundary tests
python3 ./tests/test-mcp.py     # MCP protocol tests
python3 ./tests/test_core.py    # Python unit tests

# Syntax check without running:
python3 -c "import py_compile; py_compile.compile('bingo-light', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('mcp-server.py', doraise=True)"
```

## Architecture

**bingo-light** (Python 3) — CLI entry point. Delegates all business logic to `bingo_core.Repo`. Handles argparse, human-readable formatting, and exit codes. Every command has two output paths: human-readable (default) and JSON (`--json` flag).

**bingo_core.py** (Python 3) — Core library. All business logic: sync, patches, conflict analysis, workspace, doctor, etc. Config stored in `.bingolight` via `git config --file`. Uses `.bingo/.lock` for concurrency protection.

**mcp-server.py** (Python 3, stdlib only) — Thin MCP wrapper over the CLI. Calls `run_bl()` which spawns `bingo-light --json --yes` as a subprocess. Adds `--json --yes` to ALL commands automatically. Has `try/except` around `handle_tool_call()` to prevent crashes from bad input. Uses Content-Length framed JSON-RPC 2.0 over stdio.

**agent.py** — Advisor agent. Observe → Analyze → Safe-act or Report. LLM is used for analysis ONLY, never code execution. Can run without API key (graceful degradation).

**tui.py** — Curses dashboard. Read-only status viewer with sync/dry-run.

## Critical patterns to follow when editing

**Return dicts, not prints**: Every `Repo` method returns a dict with `ok` key. The CLI formats it for human output. Never `print()` from `bingo_core.py`.

**Git subprocess safety**: All `git` calls go through `Git.run()` / `Git.run_ok()` / `Git.run_unchecked()`. Never use `subprocess.run(["git", ...])` directly except in rebase continue paths (which need custom env).

**Concurrency**: Destructive operations (sync, smart_sync) must use `self.state.acquire_lock()` / `release_lock()` in a try/finally.

**Config security**: `.bingolight` must NOT be tracked by git. `_load()` checks this and rejects tracked configs (upstream injection risk). `test.command` runs via `bash -c` — the value comes from config, so this is a trust boundary.

**Conflict detection**: Use `git ls-files --unmerged | cut -f2 | sort -u`, NOT `git diff --name-only --diff-filter=U` (misses delete/modify and rename conflicts).

**Undo state**: sync saves `.bingo/.undo-head` + `.bingo/.undo-tracking`. Undo writes `.bingo/.undo-active` to prevent `_fix_stale_tracking()` from auto-advancing tracking. Sync clears `.undo-active`.

## Key internals

- Config: `.bingolight` (git-config format), excluded via `.git/info/exclude`
- Patch ID: commit messages matching `[bl] <name>: <desc>`
- Patch names: validated to `^[a-zA-Z0-9][a-zA-Z0-9_-]*$`
- Branches: `upstream-tracking` (mirror), `bingo-patches` (patches on top)
- MCP server version must match CLI VERSION (currently 2.0.0)
- `_fix_stale_tracking()`: auto-repairs tracking branch after manual conflict resolution, skipped if `.bingo/.undo-active` exists or rebase is in progress

## Sync points — data that lives in multiple files

**VERSION** (currently 2.0.0) — change ALL of these together:
- `bingo_core.py:25` — source of truth

- `mcp-server.py` — `"version"` in initialize response
- `contrib/homebrew/bingo-light.rb` — tar.gz URL
- `CHANGELOG.md` — must have a matching `## [x.x.x]` entry

**MCP tool count** (currently 29) — change ALL of these together:
- `mcp-server.py` TOOLS array — source of truth
- `README.md` — badge + body text (4+ places)
- `README.zh-CN.md` — badge + body text (4+ places)
- `docs/getting-started.md` — tool count
- `install.sh` — display text
- `tests/test.sh` section 15 — count assertion



**README.md ↔ README.zh-CN.md** — parallel documents. Structural changes must be mirrored: badges, features, comparison table, install methods, MCP tool table, project ecosystem.

## When adding a new command

1. `bingo_core.py` — add method to `Repo` class, return dict with `ok` key
2. `bingo-light` — add argparse + dispatch + formatter
3. `completions/*.bash`, `.zsh`, `.fish` — add to completion list
5. `llms.txt` — add to command reference
6. `README.md` + `README.zh-CN.md` — add to Command Reference
7. Tests — add to `test.sh` or `test_core.py`

## When adding a new MCP tool

1. `mcp-server.py` — add to TOOLS array + `handle_tool_call()`
2. `run_bl()` auto-adds `--json --yes` — don't add them manually
3. Update MCP tool count in ALL files listed in "Sync points" above
4. `tests/test-mcp.py` — add smoke test

## For AI agents: prefer MCP or --json

```bash
bingo-light status --json
bingo-light sync --json --yes
bingo-light conflict-analyze --json
BINGO_DESCRIPTION="add feature X" bingo-light patch new feature-x --yes
```

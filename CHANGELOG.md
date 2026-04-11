# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [1.1.0] - 2026-04-11

### Added
- CODE_OF_CONDUCT.md (Contributor Covenant v2.0)
- .editorconfig for consistent code style
- .github/ISSUE_TEMPLATE/config.yml with discussion links
- .github/FUNDING.yml for GitHub Sponsors
- FAQ section in README (7 common questions)
- Comparison table vs git rebase / quilt / stacked diffs
- Animated terminal demo SVG (docs/demo.svg)
- Separate README.zh-CN.md (full Chinese README with language switcher)
- ShellCheck job in CI pipeline (separate from tests)
- GitHub Discussions enabled
- Release assets (bingo-light, mcp-server.py, install.sh)

### Fixed
- `patch new`: piped descriptions now work (`echo "desc" | bingo-light patch new name`)
- `patch meta`: positional args now work (`patch meta name reason "value"`, not just `--set-reason`)
- `conflict-analyze --json`: diff3 base section no longer leaks into `ours` field
- MCP server: all 22 tools now return `--json --yes` output (was human text for most commands)
- MCP server: `patch_new` uses `BINGO_DESCRIPTION` env var instead of fragile stdin piping
- All remaining `pingo` references renamed to `bingo` across codebase
- 12 Python injection vulnerabilities: all `python3 -c` calls now pass data via stdin
- LICENSE, contrib/hooks, issue templates: naming consistency
- Internal variables: PINGO → BL, run_pingo → run_bl
- Sync history uses atomic writes

### Changed
- README: complete overhaul (TOC, demo SVG, FAQ, feature tables, comparison, centered header)
- i18n: English and Chinese READMEs fully separated with language switcher
- CI: split into Tests + ShellCheck jobs with explicit permissions
- CONTRIBUTING.md: expanded with project structure, commit conventions, test patterns
- SECURITY.md: updated to reflect actual security measures
- PR template: added python3 injection check to checklist

## [1.0.0] - 2026-04-10

### Added
- SECURITY.md with vulnerability reporting policy
- docs/: getting-started.md, concepts.md
- contrib/hooks/: Slack, Discord, generic webhook examples
- Homebrew formula: contrib/homebrew/bingo-light.rb
- `/bingo` skill for Claude Code AI agents
- Interactive install wizard with animated TUI
- API stability guarantee for CLI, JSON, MCP, config, hooks

### Fixed
- MCP path traversal in conflict_resolve (security, pathlib)
- json_escape corruption from rename (rewrote to correct sed)
- eval in test command → bash -c (security)
- Python injection in 14 python3 -c calls (stdin instead of interpolation)
- rerere auto-continue infinite loop (max 50 iteration guard)
- 6 regex patterns still using old prefix
- undo now restores tracking branch (.bingo/.undo-tracking)
- undo "cannot force update branch in use" (git reset --hard)

## [0.9.0] - 2026-04-10

### Added
- `workspace` command: init/add/list/status/sync across multiple repos
- `tui.py`: curses-based terminal dashboard
- Workspace config at ~/.config/bingo-light/workspace.json

## [0.8.0] - 2026-04-10

### Added
- Notification hooks: .bingo/hooks/on-sync-success, on-conflict, on-test-fail
- `test` command: run configurable test suite
- `sync --test`: run tests after sync, auto-undo on failure
- diff3 merge style enabled on init
- Shallow clone auto-unshallow support

## [0.7.0] - 2026-04-10

### Added
- `config` command: get/set/list configuration values
- `patch meta`: reason, tags, expires, upstream_pr per patch (.bingo/metadata.json)
- `patch squash`: merge two patches non-interactively
- `patch reorder --order "3,1,2"`: non-interactive reorder
- `history` command: sync history with patch hash mappings
- Sync history auto-recorded on successful sync

## [0.6.0] - 2026-04-10

### Added
- `--json` output on ALL commands (status, patch list/show/drop/export, sync, doctor, diff, log, conflict-analyze)
- `--yes` / `-y` non-interactive mode, auto-detected on non-TTY
- `BINGO_DESCRIPTION` env var for patch descriptions
- `conflict-analyze` with structured JSON output
- MCP tools: conflict_analyze, conflict_resolve
- 63 tests (up from 50)

### Fixed
- MCP path traversal vulnerability
- Export default directory mismatch
- json_escape multiline handling
- auto-sync URL-safe template substitution
- Version number consistency

## [0.1.0] - 2026-04-10

### Added
- Initial release: init, patch (new/list/show/edit/drop/export/import/reorder), sync, status, doctor, undo, diff, log, auto-sync
- MCP server (15 tools), Python 3 stdlib only
- Advisor agent (agent.py): monitor, analyze, auto-sync-if-safe
- Shell completions: bash, zsh, fish
- GitHub Actions CI
- 50 tests

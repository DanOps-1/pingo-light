# bingo-light

AI-native fork maintenance tool. Single-file bash CLI + MCP server designed for LLM agents to manage upstream sync.

## AI-native features

- `--json` flag: structured JSON output on all commands
- `--yes` / `-y` flag: fully non-interactive (no prompts)
- Auto-detects non-TTY stdin → enables non-interactive mode automatically
- `BINGO_DESCRIPTION` env var: set patch description without stdin
- `conflict-analyze --json`: structured conflict info for AI resolution
- MCP server: 27 tools including `bingo_conflict_resolve` (AI writes resolved content directly)

## For AI agents: prefer MCP or --json

When helping users with fork maintenance, use the MCP tools or CLI with `--json --yes`:

```bash
# AI-friendly: structured output, no prompts
bingo-light status --json
bingo-light sync --json --yes
bingo-light conflict-analyze --json
BINGO_DESCRIPTION="add feature X" bingo-light patch new feature-x --yes
```

## Project structure

- `bingo-light` — The entire tool (single bash script)
- `mcp-server.py` — MCP server (zero-dep Python 3, 27 tools)
- `agent.py` — Advisor agent (monitor + analyze + auto-sync-if-safe)
- `tui.py` — Curses terminal dashboard
- `install.sh` — Copies to /usr/local/bin
- `llms.txt` — Complete reference for LLM consumption
- `tests/test.sh` — 71 tests
- `completions/` — bash/zsh/fish tab completion

## MCP Server setup

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "bingo-light": {
      "command": "python3",
      "args": ["/home/kali/bingo-light/mcp-server.py"]
    }
  }
}
```

## MCP Tools (22)

| Tool | Purpose |
|------|---------|
| `bingo_status` | JSON status: behind count, patches, conflict risk |
| `bingo_init` | Initialize fork tracking |
| `bingo_sync` | Rebase patches onto latest upstream |
| `bingo_undo` | Undo last sync |
| `bingo_patch_new` | Create named patch |
| `bingo_patch_list` | List patch stack |
| `bingo_patch_show` | Show patch diff |
| `bingo_patch_drop` | Remove patch |
| `bingo_patch_export` | Export as .patch files |
| `bingo_patch_import` | Import .patch files |
| `bingo_patch_meta` | Get/set patch metadata (reason, tags, expires) |
| `bingo_patch_squash` | Squash two patches into one |
| `bingo_patch_reorder` | Reorder patches non-interactively |
| `bingo_doctor` | Diagnostic check |
| `bingo_diff` | Total diff vs upstream |
| `bingo_auto_sync` | Generate GitHub Actions workflow |
| `bingo_conflict_analyze` | Structured conflict info (ours/theirs/hints) |
| `bingo_conflict_resolve` | Write resolved content, stage, continue rebase |
| `bingo_config` | Get/set/list configuration |
| `bingo_history` | Sync history with hash mappings |
| `bingo_test` | Run configured test suite |
| `bingo_workspace_status` | Multi-repo workspace overview |

All tools require `cwd` parameter.

## Key internals

- Config: `.bingolight` (git-config format), excluded via `.git/info/exclude`
- Patch ID: commit messages matching `[bl] <name>: <desc>`
- JSON mode: `--json` suppresses all human-readable output, emits single JSON object
- Non-interactive: `--yes` or non-TTY stdin auto-confirms all prompts
- MCP server: JSON-RPC 2.0 over stdio, Python 3 stdlib only

## Development

```bash
make test    # run test suite
make lint    # shellcheck
```

# pingo-light

AI-native fork maintenance tool. Single-file bash CLI + MCP server designed for LLM agents to manage upstream sync.

## AI-native features

- `--json` flag: structured JSON output on all commands
- `--yes` / `-y` flag: fully non-interactive (no prompts)
- Auto-detects non-TTY stdin → enables non-interactive mode automatically
- `PINGO_DESCRIPTION` env var: set patch description without stdin
- `conflict-analyze --json`: structured conflict info for AI resolution
- MCP server: 15 tools including `pingo_conflict_resolve` (AI writes resolved content directly)

## For AI agents: prefer MCP or --json

When helping users with fork maintenance, use the MCP tools or CLI with `--json --yes`:

```bash
# AI-friendly: structured output, no prompts
pingo-light status --json
pingo-light sync --json --yes
pingo-light conflict-analyze --json
PINGO_DESCRIPTION="add feature X" pingo-light patch new feature-x --yes
```

## Project structure

- `pingo-light` — The entire tool (single bash script)
- `mcp-server.py` — MCP server (zero-dep Python 3, 22 tools)
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
    "pingo-light": {
      "command": "python3",
      "args": ["/home/kali/pingo-light/mcp-server.py"]
    }
  }
}
```

## MCP Tools (22)

| Tool | Purpose |
|------|---------|
| `pingo_status` | JSON status: behind count, patches, conflict risk |
| `pingo_init` | Initialize fork tracking |
| `pingo_sync` | Rebase patches onto latest upstream |
| `pingo_undo` | Undo last sync |
| `pingo_patch_new` | Create named patch |
| `pingo_patch_list` | List patch stack |
| `pingo_patch_show` | Show patch diff |
| `pingo_patch_drop` | Remove patch |
| `pingo_patch_export` | Export as .patch files |
| `pingo_patch_import` | Import .patch files |
| `pingo_patch_meta` | Get/set patch metadata (reason, tags, expires) |
| `pingo_patch_squash` | Squash two patches into one |
| `pingo_patch_reorder` | Reorder patches non-interactively |
| `pingo_doctor` | Diagnostic check |
| `pingo_diff` | Total diff vs upstream |
| `pingo_auto_sync` | Generate GitHub Actions workflow |
| `pingo_conflict_analyze` | Structured conflict info (ours/theirs/hints) |
| `pingo_conflict_resolve` | Write resolved content, stage, continue rebase |
| `pingo_config` | Get/set/list configuration |
| `pingo_history` | Sync history with hash mappings |
| `pingo_test` | Run configured test suite |
| `pingo_workspace_status` | Multi-repo workspace overview |

All tools require `cwd` parameter.

## Key internals

- Config: `.pingolight` (git-config format), excluded via `.git/info/exclude`
- Patch ID: commit messages matching `[pl] <name>: <desc>`
- JSON mode: `--json` suppresses all human-readable output, emits single JSON object
- Non-interactive: `--yes` or non-TTY stdin auto-confirms all prompts
- MCP server: JSON-RPC 2.0 over stdio, Python 3 stdlib only

## Development

```bash
make test    # run 50 tests
make lint    # shellcheck
```

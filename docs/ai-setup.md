# bingo-light Installation Guide

## Quick Install

```bash
pip install bingo-light    # or: npm install -g bingo-light
bingo-light setup          # interactive: pick AI tools to configure
```

Requirements: Python 3.8+, git 2.20+. Zero dependencies.

## Step-by-Step Setup

### Step 0: Choose options

The installer needs to know your preferences. Here are the options:

| Option | Choices | Default |
|--------|---------|---------|
| Install method | `pip` / `npm` / `brew` | pip |
| Configure MCP | yes / no | yes (29 tools for fork management) |
| Install AI Skill | yes / no | yes (teaches the AI bingo-light workflows) |
| Initialize a fork | upstream URL / skip | skip |

If initializing a fork: the "upstream URL" is the GitHub URL of the original project you forked from (e.g. `https://github.com/original-author/project.git`). You can find it with `git remote -v` in your fork directory.

### Step 1: Install

```bash
# pip (recommended)
pip install bingo-light

# npm alternative
npm install -g bingo-light

# brew alternative
brew install DanOps-1/tap/bingo-light
```

Verify: `bingo-light --version` should print `bingo-light 2.1.2` or newer.

### Step 2: Configure MCP + Skills

Run the interactive setup wizard:

```bash
bingo-light setup
```

This detects installed AI tools (Claude Code, Cursor, Windsurf, VS Code, Zed, Gemini CLI, etc.), lets you pick which ones to configure, and writes the correct MCP config + AI skill files.

For non-interactive mode (CI or scripted installs):

```bash
bingo-light setup --yes --json
```

The JSON output contains `"configured"` (MCP tools) and `"skills"` (installed skill files).

#### Claude Code MCP troubleshooting

If `/mcp` shows "No MCP servers configured" after running setup, the config may have been written to the wrong file. Fix with:

```bash
claude mcp add bingo-light -- $(which bingo-light-mcp || echo bingo-light-mcp)
```

This registers the MCP server in Claude Code's native config (`~/.claude.json`).

#### MCP config paths (for manual setup)

| AI Tool | Config File | JSON Key |
|---------|-------------|----------|
| Claude Code | `~/.claude.json` (use `claude mcp add`) | `mcpServers` |
| Cursor | `~/.cursor/mcp.json` | `mcpServers` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `mcpServers` |
| VS Code / Copilot | `.vscode/mcp.json` | `servers` |
| Zed | `~/.config/zed/settings.json` | `context_servers` |
| Gemini CLI | `~/.gemini/settings.json` | `mcpServers` |
| Amazon Q | `~/.aws/amazonq/mcp.json` | `mcpServers` |

The MCP server binary is `bingo-light-mcp` (installed alongside `bingo-light`).

#### Skill file manual install

If `bingo-light setup` didn't install skills (the `"skills"` array is empty in JSON output), download manually:

```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/.claude/commands/bingo.md \
  -o ~/.claude/commands/bingo.md
```

Other skill locations: `~/.continue/rules/bingo.md`, `~/.roo/rules/bingo.md`, `~/.codeium/windsurf/memories/global_rules.md` (append).

### Step 3: Initialize a fork (optional)

```bash
cd /path/to/your-fork
bingo-light init https://github.com/original-author/project.git
```

### Step 4: Verify

```bash
bingo-light --version        # installed
bingo-light status --json    # fork status (only after init)
bingo-light doctor --json    # diagnostics (only after init)
```

## Usage

All commands support `--json` (structured output) and `--yes` (skip confirmations).

### Sync with upstream

```bash
bingo-light status --json --yes          # check recommended_action first
bingo-light smart-sync --json --yes      # sync (handles conflicts automatically)
bingo-light undo --json --yes            # revert if something went wrong
```

The `status` command returns a `recommended_action` field: `up_to_date`, `sync_safe`, `sync_risky`, or `resolve_conflict`.

### Conflict resolution

```bash
bingo-light conflict-analyze --json      # structured conflict data per file
```

Returns `ours` (upstream version), `theirs` (your patch), and `hint` (suggested resolution strategy) for each conflicted file. After resolving:

```bash
git add <file>
git rebase --continue
```

Note: do not run `bingo-light sync` after resolving — `git rebase --continue` finishes the job.

### Patch management

```bash
BINGO_DESCRIPTION="description" bingo-light patch new <name> --json --yes
bingo-light patch list --json --yes
bingo-light patch show <name|index> --json --yes
bingo-light patch drop <name|index> --json --yes
bingo-light patch edit <name|index> --json --yes    # stage changes with git add first
bingo-light patch reorder --order "3,1,2" --json --yes
bingo-light patch squash <idx1> <idx2> --json --yes
```

### Dependency patching (npm/pip)

```bash
bingo-light dep patch <package> [name] --json --yes   # generate patch from modified node_modules/
bingo-light dep apply --json --yes                     # re-apply all patches after npm install
bingo-light dep sync --json --yes                      # re-apply after npm update + detect conflicts
bingo-light dep status --json --yes                    # show patch health
bingo-light dep list --json --yes                      # list all dependency patches
bingo-light dep drop <package> --json --yes            # remove patches
```

### Diagnostics

```bash
bingo-light doctor --json --yes          # full health check
bingo-light diff --json --yes            # all changes vs upstream
bingo-light history --json --yes         # sync history with hash mappings
```

## Key facts

- Patch names: alphanumeric, hyphens, underscores only (`[a-zA-Z0-9][a-zA-Z0-9_-]*`)
- `BINGO_DESCRIPTION` env var sets the patch description when creating
- rerere is auto-enabled: conflict resolutions are remembered, same conflict won't recur
- MCP server binary: `bingo-light-mcp` (not `bingo-light mcp-server` — that command doesn't exist)
- Re-run `bingo-light setup` anytime to reconfigure MCP/Skills

## Links

- Repository: https://github.com/DanOps-1/bingo-light
- Issues: https://github.com/DanOps-1/bingo-light/issues
- PyPI: https://pypi.org/project/bingo-light/
- npm: https://www.npmjs.com/package/bingo-light

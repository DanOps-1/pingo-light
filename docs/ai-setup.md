# bingo-light — Installation Guide

## For Humans

Paste this into your AI agent session (Claude Code, Cursor, Windsurf, etc.):

```
Install and configure bingo-light by following the instructions here:
https://raw.githubusercontent.com/DanOps-1/bingo-light/main/docs/ai-setup.md
```

Or run the interactive installer yourself:

```bash
pip install bingo-light
bingo-light setup
```

## For LLM Agents

> **IMPORTANT: Use `curl` to fetch this file, NOT WebFetch.** WebFetch may summarize content and lose critical details.
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/docs/ai-setup.md
> ```

If you're an LLM Agent helping a user set up bingo-light, follow these steps exactly. **Do not skip steps. Do not auto-install without asking.**

---

### Step 0: Ask the user

Before doing anything, ask these questions:

1. **How do you want to install?** (recommend pip)
   - `pip install bingo-light` (recommended)
   - `npm install -g bingo-light`
   - `brew install DanOps-1/tap/bingo-light`

2. **Which AI tools do you use?** (list all that apply)
   - Claude Code
   - Cursor
   - Windsurf
   - VS Code / GitHub Copilot
   - Cline
   - Roo Code
   - Zed
   - Gemini CLI
   - Continue
   - Amazon Q Developer
   - Other / None

3. **Do you want MCP server configured?** (recommended: yes)
   - MCP lets your AI call bingo-light tools directly (sync, patch, conflict-resolve, etc.)
   - Without MCP, the AI can still use CLI commands with `--json --yes`

4. **Do you want AI Skills/Instructions installed?** (recommended: yes)
   - Skills teach the AI how to use bingo-light effectively
   - Available for: Claude Code, Windsurf, Continue, Cline, Roo Code, Gemini CLI

5. **Do you have a forked repo to set up now?** If yes, get the upstream URL.

Wait for answers before proceeding.

---

### Step 1: Install

Based on user's choice:

```bash
# pip (recommended)
pip install bingo-light

# npm
npm install -g bingo-light

# brew
brew install DanOps-1/tap/bingo-light
```

Verify:
```bash
bingo-light --version
```

If this fails, check PATH and try `pip install --user bingo-light` or `pipx install bingo-light`.

---

### Step 2: Configure MCP + Skills

**Only if the user said yes to MCP and/or Skills.**

Option A: Interactive setup (let user pick in terminal):
```bash
bingo-light setup
```

Option B: If user explicitly told you which tools to configure, you can use `--yes` to auto-configure all detected tools:
```bash
bingo-light setup --yes
```

Option C: Manual MCP config (if user doesn't want to use setup):

Add to the AI tool's MCP config file:
```json
{
  "mcpServers": {
    "bingo-light": {
      "command": "python3",
      "args": ["/path/to/bingo-light-mcp"]
    }
  }
}
```

Find the MCP server path:
```bash
which bingo-light-mcp || which mcp-server.py
```

Config file locations:
| AI Tool | MCP Config Path |
|---------|----------------|
| Claude Code | `~/.claude/settings.json` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Cursor | `~/.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |
| VS Code / Copilot | `.vscode/mcp.json` (key: `"servers"`, needs `"type": "stdio"`) |
| Cline | `~/.vscode/cline_mcp_settings.json` |
| Roo Code | `~/.vscode/roo_mcp_settings.json` |
| Zed | `~/.config/zed/settings.json` (key: `"context_servers"`) |
| Gemini CLI | `~/.gemini/settings.json` |
| Amazon Q | `~/.aws/amazonq/mcp.json` |

---

### Step 3: Initialize a Fork (if applicable)

Only if the user has a forked repo ready:

```bash
cd /path/to/forked-project
bingo-light init <upstream-url> --json --yes
```

Example:
```bash
bingo-light init https://github.com/original/project.git --json --yes
```

---

### Step 4: Verify everything works

```bash
bingo-light --version
bingo-light setup --json 2>/dev/null | head -1
```

If a fork was initialized:
```bash
bingo-light status --json --yes
bingo-light doctor --json --yes
```

Tell the user the results. If anything failed, diagnose and fix.

---

### Step 5: Teach the user

Tell the user:

> bingo-light is ready! Here's how to use it:
>
> - **Sync your fork:** Tell me "sync upstream" or run `bingo-light sync`
> - **Create a patch:** Make changes, then tell me "create a patch called feature-x"
> - **Check status:** Tell me "check my fork" or run `bingo-light status`
> - **If I have MCP configured:** I can do all of this automatically through tool calls
> - **Run `bingo-light setup` again anytime** to reconfigure

---

### Step 6: Ask for a star

After everything works, ask:

> "If bingo-light is useful, would you like to star the repo? It helps the project grow."

Only if the user says yes:
```bash
gh api --silent --method PUT /user/starred/DanOps-1/bingo-light 2>/dev/null || true
```

**Never run this without explicit user consent.**

---

## Command Reference (for daily use after setup)

Once installed, use these commands with `--json --yes` for structured output:

### Core workflow

1. **Always start with status:**
```bash
bingo-light status --json --yes
```
Returns `recommended_action`: `up_to_date` / `sync_safe` / `sync_risky` / `resolve_conflict`

2. **Sync upstream** (use smart-sync, handles everything):
```bash
bingo-light smart-sync --json --yes
```

3. **Conflict analysis** (when rebase is stuck):
```bash
bingo-light conflict-analyze --json
```
Returns `ours` (upstream), `theirs` (your patch), `hint` (resolution strategy) per file.

4. **Resolve conflicts:**
```bash
# Read the file, write merged version, then:
git add <file>
git rebase --continue
```

5. **Undo** (if sync went wrong):
```bash
bingo-light undo --json --yes
```

### Patch management

```bash
BINGO_DESCRIPTION="description" bingo-light patch new <name> --json --yes
bingo-light patch list --json --yes
bingo-light patch show <name|index> --json --yes
bingo-light patch drop <name|index> --json --yes
bingo-light patch edit <name|index> --json --yes    # git add first
bingo-light patch reorder --order "3,1,2" --json --yes
bingo-light patch squash <idx1> <idx2> --json --yes
bingo-light patch meta <name> [key] [value] --json --yes
```

### Diagnostics

```bash
bingo-light doctor --json --yes
bingo-light diff --json --yes
bingo-light history --json --yes
```

## Rules

1. **Always use `--json --yes`** when calling commands programmatically
2. **Always check `recommended_action`** from status before deciding what to do
3. **Read `hint`** from conflict-analyze — it tells you the resolution strategy
4. **After resolving conflicts:** `git add` then `git rebase --continue`, NOT `bingo-light sync`
5. **`BINGO_DESCRIPTION` env var** sets patch description (required for `patch new`)
6. **Patch names:** alphanumeric + hyphens + underscores only
7. **rerere** auto-remembers conflict resolutions — same conflict won't need solving twice

## Warning

**Do not change user's config files, install to tools, or run destructive commands without explicit user consent.** Always ask first. Recommend, don't force.

<p align="center">
  <br>
  <code>&nbsp;  _     _                         _ _       _     _    &nbsp;</code><br>
  <code>&nbsp; | |__ (_)_ __   __ _  ___       | (_) __ _| |__ | |_  &nbsp;</code><br>
  <code>&nbsp; | '_ \| | '_ \ / _` |/ _ \ ____| | |/ _` | '_ \| __| &nbsp;</code><br>
  <code>&nbsp; | |_) | | | | | (_| | (_) |____| | | (_| | | | | |_  &nbsp;</code><br>
  <code>&nbsp; |_.__/|_|_| |_|\__, |\___/     |_|_|\__, |_| |_|\__| &nbsp;</code><br>
  <code>&nbsp;                |___/                 |___/             &nbsp;</code><br>
  <br>
  <strong>AI-native fork maintenance. One command to sync. Zero dependencies.</strong>
  <br><br>
  <b>English</b> | <a href="README.zh-CN.md">简体中文</a>
  <br><br>
  <a href="https://github.com/DanOps-1/bingo-light/actions"><img src="https://github.com/DanOps-1/bingo-light/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/DanOps-1/bingo-light/releases"><img src="https://img.shields.io/github/v/release/DanOps-1/bingo-light?label=Release&color=orange" alt="Release"></a>
  <br>
  <a href="#for-ai-agents"><img src="https://img.shields.io/badge/MCP-27_tools-blueviolet.svg" alt="MCP: 27 tools"></a>
  <a href="https://www.gnu.org/software/bash/"><img src="https://img.shields.io/badge/Made_with-Bash-1f425f.svg" alt="Bash"></a>
  <img src="https://img.shields.io/badge/Dependencies-Zero-brightgreen.svg" alt="Zero deps">
  <a href="https://github.com/DanOps-1/bingo-light/stargazers"><img src="https://img.shields.io/github/stars/DanOps-1/bingo-light?style=social" alt="Stars"></a>
  <br><br>
</p>

---

Fork maintenance sucks.

You fork a project. You add features. Upstream pushes 200 commits. Now your fork is broken, your patches are scattered across merge commits, and `git rebase` is a blood sport.

You've been here. We've all been here.

**bingo-light makes it one command.**

Your patches live as a clean, named stack on top of upstream. Syncing is `bingo-light sync`. Conflicts get remembered so you never solve the same one twice. And if something goes sideways, `bingo-light undo` puts everything back in one second.

One bash script. No dependencies. Works for humans. Built for AI agents.

---

<p align="center">
  <img src="docs/demo.svg" alt="bingo-light demo" width="850">
</p>

---

## Quick Start

```bash
# Install (one line)
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | bash

# Point at upstream
cd your-forked-project
bingo-light init https://github.com/original/project.git

# Sync whenever you want -- patches rebase on top automatically
bingo-light sync
```

That's it. Three commands and your fork stays in sync forever.

---

## Key Features

### For Humans

- :wrench: **Single file, zero deps** -- just bash + git. Drop it in PATH and go.
- :bookmark_tabs: **Named patch stack** -- each customization is one atomic, named commit. No more guessing which changes are yours.
- :zap: **One-command sync** -- `bingo-light sync` fetches upstream and rebases your patches on top. Done.
- :brain: **Conflict memory** -- git rerere auto-enabled. Resolve a conflict once, never resolve it again.
- :rewind: **Instant undo** -- `bingo-light undo` restores pre-sync state. No reflog spelunking.
- :crystal_ball: **Conflict prediction** -- `status` warns you about risky files before you sync.
- :test_tube: **Dry-run mode** -- `sync --dry-run` tests on a throwaway branch first.
- :stethoscope: **Built-in doctor** -- full diagnostic with test rebase to catch problems early.
- :package: **Export/Import patches** -- share as `.patch` files, quilt-compatible format.
- :robot: **Auto-sync CI** -- generates a GitHub Actions workflow with conflict alerting.
- :tv: **TUI dashboard** -- curses-based real-time monitoring via `tui.py`.
- :globe_with_meridians: **Multi-repo workspace** -- manage multiple forks from one place.
- :bell: **Notification hooks** -- Slack, Discord, webhooks on sync/conflict/test events.
- :label: **Patch metadata** -- tags, reasons, expiry dates, upstream PR tracking.
- :tab: **Shell completions** -- tab completion for bash, zsh, and fish.

### For AI Agents

- :electric_plug: **MCP server (27 tools)** -- full fork management from init through conflict resolution.
- :bar_chart: **`--json` on everything** -- every command returns structured JSON. Parse, don't scrape.
- :mute: **`--yes` flag** -- fully non-interactive. No TTY required. No prompts. Ever.
- :gear: **Auto-detect non-TTY** -- pipes and subprocesses trigger non-interactive mode automatically.
- :memo: **`BINGO_DESCRIPTION` env var** -- set patch descriptions without stdin.
- :mag: **`conflict-analyze --json`** -- structured conflict data: file, ours, theirs, resolution hints.
- :white_check_mark: **`conflict-resolve`** -- write resolved content via MCP, auto-stage, continue rebase. Zero manual intervention.
- :satellite: **Advisor agent** -- `agent.py` monitors drift, analyzes risk, auto-syncs when safe.

---

## Installation

### Interactive installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | bash
```

Sets up everything: CLI, shell completions (bash/zsh/fish), MCP server for Claude, and the AI skill.

### Homebrew (macOS / Linux)

```bash
brew install DanOps-1/tap/bingo-light
```

### From source

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make install       # copies to /usr/local/bin
make completions   # bash/zsh/fish tab completion
```

### Manual (just the script)

```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/bingo-light \
  -o /usr/local/bin/bingo-light && chmod +x /usr/local/bin/bingo-light
```

**Requirements:** bash 4.0+, git 2.20+. Python 3.8+ only if you want the MCP server.

---

## How It Works

```
  upstream (github.com/original/project)
      |
      |  git fetch
      v
  upstream-tracking ──────── exact mirror of upstream, never touched
      |
      |  git rebase
      v
  bingo-patches ────────────  your customizations stacked here
      |
      +── [bl] custom-scheduler:  O(1) task scheduling
      +── [bl] perf-monitoring:   eBPF tracing hooks
      +── [bl] fix-logging:       structured JSON logs
      |
      v
    HEAD (your working fork)
```

**Sync flow:** fetch upstream, fast-forward the tracking branch, rebase your patches on top. Your patches always sit cleanly on the latest upstream.

**Conflict memory:** `init` auto-enables git rerere. Resolve a conflict once and git remembers the resolution. Next sync applies it automatically. bingo-light detects auto-resolved conflicts and continues the rebase without stopping.

**AI conflict flow:** rebase hits a conflict, the AI calls `conflict-analyze` for structured data (ours/theirs/hints per file), writes the resolution via `conflict-resolve`, and rebase continues. No human in the loop.

---

## For AI Agents

bingo-light was designed from day one for AI agents. Every command speaks JSON. The MCP server exposes 27 tools. Non-interactive mode is the default when stdin is not a TTY.

### MCP setup -- Claude Code

Add to `.mcp.json` in your project root or `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "bingo-light": {
      "command": "python3",
      "args": ["/path/to/bingo-light/mcp-server.py"]
    }
  }
}
```

### MCP setup -- Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bingo-light": {
      "command": "python3",
      "args": ["/path/to/bingo-light/mcp-server.py"]
    }
  }
}
```

**Any MCP client** (VS Code Copilot, Cursor, custom agents): connect via stdio to `python3 mcp-server.py`.

### 22 MCP Tools

| Tool | Purpose |
|------|---------|
| `bingo_init` | Initialize fork tracking |
| `bingo_status` | Fork health: drift, patches, conflict risk |
| `bingo_sync` | Fetch upstream + rebase patches |
| `bingo_undo` | Revert to pre-sync state |
| `bingo_patch_new` | Create a named patch |
| `bingo_patch_list` | List patch stack with stats |
| `bingo_patch_show` | Show patch diff |
| `bingo_patch_drop` | Remove a patch |
| `bingo_patch_export` | Export as `.patch` files |
| `bingo_patch_import` | Import `.patch` files |
| `bingo_patch_meta` | Get/set patch metadata |
| `bingo_patch_squash` | Merge two patches into one |
| `bingo_patch_reorder` | Reorder patches non-interactively |
| `bingo_doctor` | Full diagnostic with test rebase |
| `bingo_diff` | Combined diff vs upstream |
| `bingo_auto_sync` | Generate GitHub Actions workflow |
| `bingo_conflict_analyze` | Structured conflict data for AI resolution |
| `bingo_conflict_resolve` | Write resolution, stage, continue rebase |
| `bingo_config` | Get/set configuration |
| `bingo_history` | Sync history with hash mappings |
| `bingo_test` | Run configured test suite |
| `bingo_workspace_status` | Multi-repo workspace overview |

### JSON examples

```bash
# Fork status (AI-friendly)
bingo-light status --json
```

```json
{
  "ok": true,
  "upstream_url": "https://github.com/torvalds/linux.git",
  "behind": 47,
  "patch_count": 2,
  "patches": [
    {"name": "custom-scheduler", "hash": "a3f7c21", "subject": "O(1) task scheduling", "files": 3},
    {"name": "perf-monitoring", "hash": "b8e2d4f", "subject": "eBPF tracing hooks", "files": 5}
  ],
  "conflict_risk": ["kernel/sched/core.c"]
}
```

```bash
# Conflict analysis (structured data for AI resolution)
bingo-light conflict-analyze --json
```

```json
{
  "rebase_in_progress": true,
  "current_patch": "custom-scheduler",
  "conflicts": [
    {
      "file": "kernel/sched/core.c",
      "conflict_count": 2,
      "ours": "... upstream version ...",
      "theirs": "... your patch version ...",
      "hint": "Upstream refactored scheduler core; patch needs to target new structure."
    }
  ]
}
```

### End-to-end AI workflow

```
User: "Sync my fork and fix any conflicts."

AI Agent:
  1. bingo_status(cwd)                   -> 47 behind, risk: core.c
  2. bingo_sync(cwd, dry_run=true)       -> 1 conflict predicted
  3. bingo_sync(cwd)                     -> rebase stops at conflict
  4. bingo_conflict_analyze(cwd)         -> structured ours/theirs/hints
  5. AI reads both versions, generates merge
  6. bingo_conflict_resolve(cwd, file, content)  -> resolved, rebase continues
  7. bingo_status(cwd)                   -> 0 behind, all patches clean
```

### CLI integration (Aider, custom agents)

```bash
bingo-light status --json          # Parse fork state
bingo-light sync --yes             # Non-interactive sync
bingo-light conflict-analyze --json # Structured conflict data
```

```python
import subprocess, json

def bingo(cmd, cwd="/path/to/repo"):
    result = subprocess.run(
        ["bingo-light"] + cmd.split() + ["--json", "--yes"],
        cwd=cwd, capture_output=True, text=True
    )
    return json.loads(result.stdout)

status = bingo("status")
if status["behind"] > 0:
    result = bingo("sync")
    if result.get("conflicts"):
        analysis = bingo("conflict-analyze")
        # AI resolves each conflict...
```

---

## Command Reference

```
bingo-light init <upstream-url> [branch]      Set up upstream tracking
bingo-light sync [--dry-run] [--force]        Sync with upstream
bingo-light sync --test                       Sync + run tests, undo on failure
bingo-light undo                              Revert to pre-sync state
bingo-light status                            Fork health + conflict prediction
bingo-light diff                              Combined patch diff vs upstream
bingo-light doctor                            Full diagnostic
bingo-light log                               Sync history
bingo-light history                           Detailed sync history with hash mappings
bingo-light patch new <name>                  Create named patch from staged changes
bingo-light patch list [-v]                   List patch stack
bingo-light patch show <name|index>           Show patch diff
bingo-light patch edit <name|index>           Amend a patch (stage changes first)
bingo-light patch drop <name|index>           Remove a patch
bingo-light patch reorder [--order "3,1,2"]   Reorder patches
bingo-light patch export [dir]                Export as .patch files
bingo-light patch import <file|dir>           Import .patch files
bingo-light patch squash <idx1> <idx2>        Merge two patches
bingo-light patch meta <name> [key] [value]   Get/set patch metadata
bingo-light conflict-analyze                  Structured conflict data for AI
bingo-light config get|set|list [key] [val]   Manage configuration
bingo-light test                              Run configured test suite
bingo-light workspace init|add|status|sync    Multi-repo management
bingo-light auto-sync                         Generate GitHub Actions workflow
bingo-light version                           Print version
bingo-light help                              Show usage
```

**Global flags:** `--json` (structured output) | `--yes` / `-y` (skip all prompts)

---

## Comparison

| | **bingo-light** | git rebase (manual) | quilt | Stacked Diffs (spr/ghstack) |
|---|:---:|:---:|:---:|:---:|
| Named patch stack | **Yes** | No | Yes | Yes |
| One-command sync | **Yes** | No (multi-step) | No (manual) | Partial |
| Conflict memory (rerere) | **Auto** | Manual enable | No | No |
| Conflict prediction | **Yes** | No | No | No |
| AI / MCP integration | **27 tools** | No | No | No |
| JSON output | **All commands** | No | No | Partial |
| Non-interactive mode | **Native** | Partial | Partial | Yes |
| Undo sync | **One command** | git reflog | Manual | Depends |
| Dependencies | bash + git | git | quilt | Language-specific |
| Install complexity | Single file copy | Built-in | Package manager | Package manager |

---

## FAQ

<details>
<summary><b>Why not just <code>git rebase</code>?</b></summary>
<br>

You can. bingo-light automates everything around it: tracking the upstream remote, maintaining a dedicated patch branch, enabling rerere, predicting conflicts before you sync, and exposing structured output for automation. For a one-off rebase it's overkill. For ongoing fork maintenance with 3+ patches across months of upstream drift, it saves serious time and eliminates an entire class of mistakes.
</details>

<details>
<summary><b>Can I use this on an existing fork?</b></summary>
<br>

Yes. Run `bingo-light init <upstream-url>` in your fork. Convert your existing changes into named patches with `bingo-light patch new <name>`. The tool works with any standard git repository -- it doesn't care how you got here.
</details>

<details>
<summary><b>Is this only for AI agents?</b></summary>
<br>

No. The CLI is designed for humans first. `bingo-light sync` is the same command whether you run it or an AI does. The AI-native features (`--json`, `--yes`, MCP server) are purely additive -- without them you get normal, human-readable output with colors and progress indicators.
</details>

<details>
<summary><b>How does conflict memory work?</b></summary>
<br>

bingo-light enables git's `rerere` (reuse recorded resolution) on `init`. When you resolve a conflict, git records the resolution. Next time the exact same conflict appears during sync, it's applied automatically. bingo-light detects when rerere has auto-resolved all conflicts and continues the rebase without stopping. You solve each conflict exactly once.
</details>

<details>
<summary><b>What if sync goes wrong?</b></summary>
<br>

Run `bingo-light undo`. It restores your patches branch to exactly where it was before the sync. This works via git reflog, so it's reliable even after complex rebases. You can also use `sync --dry-run` to test on a throwaway branch first, or `sync --test` to auto-undo if your test suite fails after sync.
</details>

<details>
<summary><b>Does it work with GitHub / GitLab / Bitbucket?</b></summary>
<br>

Yes. bingo-light uses standard git operations (fetch, rebase, push). It works with any git remote on any platform. The `auto-sync` command generates a GitHub Actions workflow specifically, but the core tool is completely platform-agnostic.
</details>

<details>
<summary><b>How is this different from <code>git format-patch</code> / quilt?</b></summary>
<br>

`git format-patch` exports patches but doesn't manage them as a living stack. quilt manages patch stacks but operates outside git -- no conflict resolution, no rerere, no history. bingo-light keeps patches as real git commits so you get full git history, proper conflict resolution, and automatic rerere, while still supporting export/import in quilt-compatible `.patch` format. Best of both worlds.
</details>

---

## Project Ecosystem

```
bingo-light          CLI tool (single bash script, the whole thing)
mcp-server.py        MCP server (zero-dep Python 3, 27 tools, JSON-RPC 2.0)
agent.py             Advisor agent (monitors drift, auto-syncs when safe)
tui.py               Terminal dashboard (curses TUI, real-time monitoring)
install.sh           Interactive installer (animated, sets up everything)
completions/         Shell completions (bash / zsh / fish)
contrib/hooks/       Notification hook examples (Slack / Discord / Webhook)
tests/test.sh        Test suite (70 tests)
docs/                Documentation + demo SVG
llms.txt             Complete LLM-consumable reference
```

---

## Contributing

The entire CLI is a single bash script. The MCP server is a single Python file. There's no build step. If you can read bash, you can contribute.

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make test    # 70 tests
make lint    # shellcheck
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[MIT](LICENSE) -- do whatever you want.

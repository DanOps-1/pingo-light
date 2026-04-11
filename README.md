<p align="center">
  <br>
  <code>&nbsp;  _     _                         _ _       _     _    &nbsp;</code><br>
  <code>&nbsp; | |__ (_)_ __   __ _  ___       | (_) __ _| |__ | |_  &nbsp;</code><br>
  <code>&nbsp; | '_ \| | '_ \ / _` |/ _ \ ____| | |/ _` | '_ \| __| &nbsp;</code><br>
  <code>&nbsp; | |_) | | | | | (_| | (_) |____| | | (_| | | | | |_  &nbsp;</code><br>
  <code>&nbsp; |_.__/|_|_| |_|\__, |\___/     |_|_|\__, |_| |_|\__| &nbsp;</code><br>
  <code>&nbsp;                |___/                 |___/             &nbsp;</code><br>
  <br>
  <strong>AI-native fork maintenance. Keep your patches. Stay in sync.</strong>
  <br><br>
  <a href="https://github.com/DanOps-1/bingo-light/actions"><img src="https://github.com/DanOps-1/bingo-light/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/DanOps-1/bingo-light/releases"><img src="https://img.shields.io/github/v/release/DanOps-1/bingo-light?label=Release&color=orange" alt="Release"></a>
  <a href="#mcp-server"><img src="https://img.shields.io/badge/MCP-22_tools-blueviolet.svg" alt="MCP: 22 tools"></a>
  <a href="https://www.gnu.org/software/bash/"><img src="https://img.shields.io/badge/Made_with-Bash-1f425f.svg" alt="Bash"></a>
  <a href="https://github.com/DanOps-1/bingo-light/stargazers"><img src="https://img.shields.io/github/stars/DanOps-1/bingo-light?style=social" alt="Stars"></a>
  <br><br>
</p>

You maintain a fork. You add features upstream doesn't have. Then upstream pushes 50 commits and your fork is stuck. **bingo-light fixes this** -- your patches live as a clean stack on top of upstream, and syncing is one command.

Built for **AI agents** (MCP server, structured JSON, non-interactive mode) and **humans** (single file, zero dependencies, just bash + git).

---

## Table of Contents

- [Quick Start](#quick-start)
- [Demo](#demo)
- [Installation](#installation)
- [Features](#features)
- [How It Works](#how-it-works)
- [MCP Server](#mcp-server)
- [Command Reference](#command-reference)
- [Integration Guide](#integration-guide)
- [Configuration](#configuration)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## Quick Start

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | bash

# Set up fork tracking
cd my-forked-project
bingo-light init https://github.com/original/project.git

# Make changes, create a named patch
vim src/feature.py
bingo-light patch new my-feature

# Sync with upstream (your patches rebase on top automatically)
bingo-light sync
```

That's it. Your patches are a clean stack on top of upstream. Sync as often as you want.

## Demo

### Fork status at a glance

```
$ bingo-light status

  bingo-light status
  ──────────────────────────────────────────

    Upstream   https://github.com/original/project.git (main)
    Behind     12 commits
    Patches    3 in stack

    #1  dark-mode       support dark color scheme          3 files
    #2  api-cache       add Redis caching layer            5 files
    #3  fix-logging     structured JSON logs               1 file

    Conflict risk
      src/config.py — modified by both upstream and patch #2
```

### One-command sync

```
$ bingo-light sync

  Fetching upstream...
  Upstream: 12 new commits
  Rebasing 3 patches onto upstream...
    [1/3] dark-mode .......... ok
    [2/3] api-cache .......... ok
    [3/3] fix-logging ........ ok
  Sync complete. 3 patches rebased onto 12 upstream commits.
```

### AI gets structured JSON

```
$ bingo-light status --json
```
```json
{
  "ok": true,
  "upstream_url": "https://github.com/original/project.git",
  "behind": 12,
  "patch_count": 3,
  "patches": [
    {"name": "dark-mode", "hash": "a3f7c21", "subject": "support dark color scheme", "files": 3},
    {"name": "api-cache", "hash": "b8e2d4f", "subject": "add Redis caching layer", "files": 5}
  ],
  "conflict_risk": ["src/config.py"]
}
```

### Conflict resolution (AI workflow)

```
$ bingo-light conflict-analyze --json
```
```json
{
  "rebase_in_progress": true,
  "current_patch": "api-cache",
  "conflicts": [
    {
      "file": "src/config.py",
      "conflict_count": 2,
      "ours": "... upstream version ...",
      "theirs": "... your patch version ...",
      "hint": "Upstream refactored Config class; patch needs to target new structure."
    }
  ]
}
```

## Installation

### Interactive installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | bash
```

The installer sets up: CLI, shell completions, MCP server for Claude, and the `/bingo` AI skill.

### Homebrew (macOS/Linux)

```bash
brew install DanOps-1/tap/bingo-light
```

### From source

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make install       # installs to /usr/local/bin
make completions   # bash/zsh/fish tab completion
```

### Manual

```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/bingo-light \
  -o /usr/local/bin/bingo-light && chmod +x /usr/local/bin/bingo-light
```

**Requirements:** bash 4.0+, git 2.20+, Python 3.8+ (for MCP server only)

## Features

### For AI agents

| Feature | Description |
|---------|-------------|
| **MCP server** | 22 tools covering init through conflict resolution |
| **`--json` flag** | Every command returns structured JSON |
| **`--yes` flag** | Fully non-interactive, no TTY required |
| **Auto-detect non-TTY** | Suppresses prompts when called via pipe or subprocess |
| **`BINGO_DESCRIPTION`** | Set patch descriptions via environment variable |
| **`conflict-analyze`** | Structured conflict data: file, ours, theirs, hints |
| **`conflict-resolve`** | Write resolved content via MCP, auto-stage, continue rebase |
| **Advisor agent** | `agent.py` monitors drift, analyzes risk, auto-syncs when safe |

### For humans

| Feature | Description |
|---------|-------------|
| **Single file, zero deps** | Just bash + git. Drop in PATH and go |
| **Named patch stack** | Each customization is one atomic, named commit |
| **One-command sync** | `bingo-light sync` rebases your patches onto upstream |
| **Dry-run** | `sync --dry-run` tests on a temp branch first |
| **Conflict memory** | git rerere auto-enabled; resolve once, never again |
| **Undo** | `bingo-light undo` restores pre-sync state instantly |
| **Conflict prediction** | `status` warns about files changed by both you and upstream |
| **Doctor** | Full diagnostic with test rebase |
| **Export/Import** | Share patches as `.patch` files (quilt-compatible) |
| **Auto-sync CI** | Generates GitHub Actions workflow with conflict alerting |
| **TUI dashboard** | Curses-based real-time monitoring (`tui.py`) |
| **Workspace** | Manage multiple forks from one place |
| **Shell completions** | Tab completion for bash, zsh, fish |
| **Notification hooks** | Discord, Slack, generic webhook on sync/conflict/test events |
| **Patch metadata** | Tags, reasons, expiry dates, upstream PR tracking |
| **Test integration** | Run test suite after sync, auto-undo on failure |

## How It Works

```
  upstream (github.com/original/project)
      |
      |  git fetch
      v
  upstream-tracking ─────── exact mirror of upstream, never touched
      |
      |  git rebase
      v
  bingo-patches ─────────── your customizations stacked here
      |
      +── [bl] dark-mode:    support dark color scheme
      +── [bl] api-cache:    add Redis caching layer
      +── [bl] fix-logging:  structured JSON logs
      |
      v
    HEAD (your working fork)
```

**Sync flow:** fetch upstream -> fast-forward tracking branch -> rebase patches on top. Your patches always sit cleanly on upstream.

**Conflict memory:** git rerere is auto-enabled on init. Resolve a conflict once, and git remembers -- next sync applies the same fix automatically.

**AI conflict flow:** when rebase hits a conflict, the AI calls `conflict-analyze` to get structured data (ours/theirs/hints per file), writes the resolution via `conflict-resolve`, and rebase continues. No manual intervention.

## MCP Server

`mcp-server.py` is a zero-dependency Python 3 MCP server exposing 22 tools over stdio (JSON-RPC 2.0).

### Setup

**Claude Code** -- add to `.mcp.json` or `~/.claude/settings.json`:

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

**Claude Desktop** -- add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

### Available tools

| Tool | Purpose |
|------|---------|
| `bingo_init` | Initialize fork tracking |
| `bingo_status` | Fork health: drift, patches, conflict risk |
| `bingo_sync` | Fetch upstream and rebase patches |
| `bingo_undo` | Revert to pre-sync state |
| `bingo_patch_new` | Create a named patch |
| `bingo_patch_list` | List patch stack with stats |
| `bingo_patch_show` | Show patch diff |
| `bingo_patch_drop` | Remove a patch |
| `bingo_patch_export` | Export as `.patch` files |
| `bingo_patch_import` | Import `.patch` files |
| `bingo_patch_meta` | Get/set patch metadata |
| `bingo_patch_squash` | Merge two patches |
| `bingo_patch_reorder` | Reorder patches non-interactively |
| `bingo_doctor` | Full diagnostic with test rebase |
| `bingo_diff` | Combined diff vs upstream |
| `bingo_auto_sync` | Generate GitHub Actions workflow |
| `bingo_conflict_analyze` | Structured conflict data for AI |
| `bingo_conflict_resolve` | Write resolution, stage, continue rebase |
| `bingo_config` | Get/set configuration |
| `bingo_history` | Sync history with hash mappings |
| `bingo_test` | Run configured test suite |
| `bingo_workspace_status` | Multi-repo workspace overview |

## Command Reference

```
bingo-light init <upstream-url> [branch]     Set up upstream tracking
bingo-light patch new <name>                 Create named patch from staged changes
bingo-light patch list [-v]                  List patches in the stack
bingo-light patch show <name|index>          Show patch diff
bingo-light patch edit <name|index>          Amend a patch (stage changes first)
bingo-light patch drop <name|index>          Remove a patch
bingo-light patch reorder [--order "3,1,2"]  Reorder patches
bingo-light patch export [dir]               Export as .patch files
bingo-light patch import <file|dir>          Import .patch files
bingo-light patch squash <idx1> <idx2>       Merge two patches
bingo-light patch meta <name> [key] [value]  Get/set patch metadata
bingo-light sync [--dry-run] [--force]       Sync with upstream
bingo-light sync --test                      Sync + run tests, undo on failure
bingo-light undo                             Revert to pre-sync state
bingo-light status                           Fork health and conflict prediction
bingo-light doctor                           Full diagnostic
bingo-light diff                             Combined patch diff vs upstream
bingo-light log                              Sync history
bingo-light conflict-analyze                 Analyze rebase conflicts
bingo-light config get|set|list [key] [val]  Manage configuration
bingo-light history                          Detailed sync history with mappings
bingo-light test                             Run configured test suite
bingo-light workspace init|add|status|sync   Multi-repo management
bingo-light auto-sync                        Generate GitHub Actions workflow
bingo-light version                          Print version
bingo-light help                             Print usage summary
```

**Global flags:** `--json` (structured JSON output) | `--yes` (skip all prompts)

## Integration Guide

### Claude Code (MCP)

With the MCP server configured, Claude Code manages your fork end-to-end:

```
You: "Sync my fork with upstream and fix any conflicts."

Claude Code:
  1. bingo_status(cwd)        -> 12 behind, risk: src/config.py
  2. bingo_sync(cwd, dry_run) -> 1 conflict predicted
  3. bingo_sync(cwd)          -> rebase stops at conflict
  4. bingo_conflict_analyze() -> structured ours/theirs/hints
  5. Reads both versions, generates merged content
  6. bingo_conflict_resolve(cwd, file, content) -> done
  7. bingo_status(cwd)        -> 0 behind, all patches clean
```

### Aider / CLI agents

```bash
bingo-light status --json          # Parse fork state
bingo-light sync --yes             # Non-interactive sync
bingo-light conflict-analyze --json # Structured conflict data
```

### Custom Python agent

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
        for c in analysis["conflicts"]:
            resolved = my_llm_resolve(c["ours"], c["theirs"], c["hint"])
            # resolve via CLI or MCP
```

## Configuration

Config is stored in `.bingolight` (git-config format), excluded from version control via `.git/info/exclude`.

```bash
bingo-light config set sync.auto-test true     # Run tests after sync
bingo-light config set test.command "make test" # Test command to run
bingo-light config list                         # Show all settings
```

### Notification hooks

Place executable scripts in `.bingo/hooks/`:

| Hook | Triggered when |
|------|---------------|
| `on-sync-success` | Sync completes successfully |
| `on-conflict` | Rebase hits a conflict |
| `on-test-fail` | Post-sync tests fail |

Each hook receives a JSON payload on stdin. See [contrib/hooks/](contrib/hooks/) for Slack, Discord, and generic webhook examples.

## FAQ

<details>
<summary><b>Why not just <code>git rebase</code> manually?</b></summary>

You can. bingo-light automates the ceremony around it: tracking the upstream remote, maintaining a dedicated patch branch, enabling rerere, predicting conflicts before sync, and providing structured output for automation. For a one-off rebase it's overkill. For ongoing fork maintenance with 3+ patches, it saves real time.
</details>

<details>
<summary><b>Can I use this on an existing fork?</b></summary>

Yes. Run `bingo-light init <upstream-url>` in your fork. Then convert your existing changes into named patches with `bingo-light patch new <name>`. The tool works with any standard git repository.
</details>

<details>
<summary><b>Is this only for AI agents?</b></summary>

No. The CLI works great for humans -- `bingo-light sync` is the same command whether you or an AI runs it. The AI-native features (`--json`, `--yes`, MCP) are purely additive. Without them, you get normal human-friendly output.
</details>

<details>
<summary><b>How does conflict memory work?</b></summary>

bingo-light enables git's `rerere` (reuse recorded resolution) on `init`. When you resolve a conflict, git remembers the resolution. Next time the same conflict appears during sync, it's applied automatically. bingo-light also detects auto-resolved conflicts and continues the rebase without stopping.
</details>

<details>
<summary><b>What happens if sync goes wrong?</b></summary>

Run `bingo-light undo`. It restores your patches branch to exactly where it was before the sync. The undo is based on git reflog, so it's reliable even after complex rebases.
</details>

<details>
<summary><b>Does it work with GitHub/GitLab/Bitbucket?</b></summary>

Yes. bingo-light works with any git remote. It uses standard git operations (fetch, rebase, push). The `auto-sync` command generates a GitHub Actions workflow, but the core tool is platform-agnostic.
</details>

<details>
<summary><b>How is this different from <code>git format-patch</code> / quilt?</b></summary>

`format-patch` exports patches but doesn't manage them as a living stack. quilt manages patches but operates outside git. bingo-light keeps patches as real git commits, so you get full git history, conflict resolution, and rerere -- while still supporting export/import in quilt-compatible format.
</details>

## Contributing

Contributions are welcome. The entire CLI is a single bash script (`bingo-light`). The MCP server is a single Python file (`mcp-server.py`). No build step.

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make test    # run 71 tests
make lint    # shellcheck
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[MIT](LICENSE)

---

<details>
<summary><b>简体中文</b></summary>

## bingo-light -- AI 原生的 Fork 维护工具

你维护了一个 Fork，添加了上游没有的功能。然后上游推送了 50 个 commit，你的 Fork 就卡住了。**bingo-light 解决这个问题** -- 你的补丁作为干净的栈叠在上游之上，同步只需一条命令。

### 快速开始

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | bash

# 初始化
cd my-forked-project
bingo-light init https://github.com/original/project.git

# 创建补丁
vim src/feature.py
bingo-light patch new my-feature

# 与上游同步（补丁自动变基到上游之上）
bingo-light sync
```

### 核心特性

- **MCP 服务器** -- 22 个工具覆盖从初始化到冲突解决的完整生命周期
- **`--json`** -- 所有命令返回结构化 JSON
- **`--yes`** -- 完全非交互模式，无需 TTY
- **冲突分析** -- `conflict-analyze` 返回结构化冲突数据
- **冲突解决** -- AI 通过 MCP 直接写入解决内容，自动继续 rebase
- **单文件，零依赖** -- 只需 bash + git
- **冲突记忆** -- git rerere 自动记住解决方案，同样的冲突只需解决一次
- **一键撤销** -- `bingo-light undo` 恢复同步前状态

### MCP 配置

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

配置后，AI 代理可以直接调用 22 个 MCP 工具管理你的 Fork。

[完整文档](https://github.com/DanOps-1/bingo-light)

</details>

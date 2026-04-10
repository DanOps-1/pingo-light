```
        _                         _ _       _     _
  _ __ (_)_ __   __ _  ___       | (_) __ _| |__ | |_
 | '_ \| | '_ \ / _` |/ _ \ ____| | |/ _` | '_ \| __|
 | |_) | | | | | (_| | (_) |____| | | (_| | | | | |_
 | .__/|_|_| |_|\__, |\___/     |_|_|\__, |_| |_|\__|
 |_|            |___/                 |___/
```

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![AI-native](https://img.shields.io/badge/AI--native-MCP%20%2B%20JSON-blueviolet.svg)](#why-ai-native)
[![Bash](https://img.shields.io/badge/Made_with-Bash-1f425f.svg)](https://www.gnu.org/software/bash/)
[![Tests](https://img.shields.io/badge/Tests-Passing-brightgreen.svg)](.github/workflows)
[![Version](https://img.shields.io/badge/Version-1.0.0-orange.svg)](pingo-light)

**AI-native fork maintenance. One tool for agents to manage upstream sync.**

**AI 原生的 Fork 维护工具 ---- 让大模型自主管理上游同步。**

---

## Why AI-native?

AI coding agents -- Claude Code, Aider, Cursor agents, custom pipelines -- are increasingly doing real work inside forked repositories. They add features, fix bugs, backport patches. But when upstream moves forward, the fork drifts, and nobody has a good answer for "how does the AI keep this fork in sync?"

No existing tool is designed for an AI agent to manage fork maintenance end-to-end. The agent needs:

- **Structured output** it can parse (not human-formatted tables)
- **Non-interactive mode** it can call without a TTY
- **Conflict analysis** it can read as data, not as diff markers in a file
- **Conflict resolution** it can write back through an API, not through an editor

pingo-light is the bridge. The AI calls MCP tools, patches are managed as a clean stack, and upstream stays in sync -- including fully automated conflict resolution.

```
AI Agent                                    pingo-light
---------                                   -----------
pingo_init(cwd, upstream_url)           --> Set up tracking
pingo_patch_new(cwd, name, description) --> Create patch
pingo_status(cwd)                       --> {"behind": 5, "conflict_risk": ["app.py"]}
pingo_sync(cwd, dry_run=true)           --> Test rebase safely
pingo_sync(cwd)                         --> Rebase patches onto upstream
pingo_conflict_analyze(cwd)             --> {"conflicts": [{file, ours, theirs}]}
pingo_conflict_resolve(cwd, file, content) --> Write fix, stage, continue rebase
```

The agent gets structured JSON at every step. No parsing `git status` output. No hoping `expect` scripts will handle prompts. No guessing where the conflict markers are.

## Features

### For AI agents (primary interface)

- **MCP server** (`mcp-server.py`) -- 15 tools covering the full lifecycle from init to conflict resolution
- **`--json` flag** -- every command returns structured JSON that agents parse reliably
- **`--yes` flag** -- fully non-interactive mode; no prompts, no TTY required
- **Auto-detects non-TTY** -- when called via pipe or subprocess, interactive prompts are suppressed automatically
- **`PINGO_DESCRIPTION` env var** -- AI sets patch descriptions without needing stdin
- **`conflict-analyze`** -- returns structured conflict data (file paths, ours/theirs content, conflict count, hints)
- **`pingo_conflict_resolve`** -- AI writes resolved content directly through MCP; file is written, staged, and rebase continues

### For humans (also works great)

- **Single file, zero dependencies** -- just bash + git. Drop it in your PATH and go.
- **Named patch stack** -- each customization is one atomic, named commit
- **One-command sync** -- `pingo-light sync` fetches upstream and rebases your entire patch stack
- **Dry-run sync** -- `sync --dry-run` tests on a temporary branch without touching anything
- **Conflict memory** -- git rerere is auto-enabled; resolve a conflict once, never again
- **Undo** -- `pingo-light undo` restores your patches branch to its pre-sync state
- **Conflict prediction** -- `pingo-light status` warns about files both you and upstream changed
- **Doctor** -- `pingo-light doctor` runs a full diagnostic with a test rebase
- **Export / Import** -- share patches as `.patch` files (quilt-compatible `series` file included)
- **Auto-sync CI** -- `pingo-light auto-sync` generates a GitHub Actions workflow with conflict alerting

## Also works for humans

You do not need an AI agent to use pingo-light. It works exactly as you would expect from a terminal:

```bash
cd my-forked-project
pingo-light init https://github.com/original/project.git

# Make changes, create a patch
vim src/theme.py
pingo-light patch new dark-mode

# Sync with upstream at any time
pingo-light sync

# Check health
pingo-light status
```

The `--json` and `--yes` flags are purely additive. Without them, you get the same human-friendly output as always.

## JSON Output Examples

### `pingo-light status --json`

```json
{
  "initialized": true,
  "upstream": "https://github.com/original/project.git",
  "upstream_branch": "main",
  "behind": 5,
  "patches": [
    {
      "index": 1,
      "name": "dark-mode",
      "hash": "a3f7c21",
      "description": "support dark color scheme",
      "insertions": 84,
      "deletions": 12,
      "files_changed": 3
    }
  ],
  "conflict_risk": ["src/theme.py", "src/config.py"]
}
```

### `pingo-light conflict-analyze --json`

```json
{
  "rebase_in_progress": true,
  "current_patch": "dark-mode",
  "conflicts": [
    {
      "file": "src/theme.py",
      "conflict_count": 2,
      "ours": "... upstream version of conflicting section ...",
      "theirs": "... your patch version of conflicting section ...",
      "hint": "Upstream refactored the Theme class; your dark-mode additions need to target the new class structure."
    }
  ]
}
```

## MCP Server Setup

pingo-light ships with `mcp-server.py` -- a zero-dependency Python 3 MCP server that exposes all 15 tools over stdio (JSON-RPC 2.0).

### Claude Code

Add to your project's `.mcp.json` or `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "pingo-light": {
      "command": "python3",
      "args": ["/path/to/pingo-light/mcp-server.py"]
    }
  }
}
```

Then in Claude Code, the agent can call `pingo_status`, `pingo_sync`, `pingo_conflict_analyze`, etc. directly as MCP tools.

### Claude Desktop

Add to your Claude Desktop MCP config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "pingo-light": {
      "command": "python3",
      "args": ["/path/to/pingo-light/mcp-server.py"]
    }
  }
}
```

### Generic MCP client

Any MCP-compatible client (VS Code Copilot, Cursor, custom agents) can connect over stdio:

```bash
python3 /path/to/pingo-light/mcp-server.py
```

The server speaks standard MCP stdio transport (Content-Length headers + JSON-RPC 2.0). It exposes `tools/list` and `tools/call` methods.

### Available MCP tools

| Tool | Description |
|---|---|
| `pingo_init` | Initialize tracking for a forked repo |
| `pingo_status` | Fork health: drift, patches, conflict risk |
| `pingo_sync` | Fetch upstream and rebase patches (supports `dry_run`) |
| `pingo_undo` | Revert to pre-sync state |
| `pingo_patch_new` | Create a named patch from current changes |
| `pingo_patch_list` | List all patches with stats |
| `pingo_patch_show` | Show full diff for a patch |
| `pingo_patch_drop` | Remove a patch from the stack |
| `pingo_patch_export` | Export patches as `.patch` files |
| `pingo_patch_import` | Import `.patch` files into the stack |
| `pingo_doctor` | Full diagnostic with test rebase |
| `pingo_diff` | Combined diff of all patches vs upstream |
| `pingo_auto_sync` | Generate GitHub Actions workflow |
| `pingo_conflict_analyze` | Structured conflict data for AI resolution |
| `pingo_conflict_resolve` | Write resolved content, stage, continue rebase |

## Command Reference

| Command | Description |
|---|---|
| `init <upstream-url> [branch]` | Initialize pingo-light, set up upstream tracking and patch branch |
| `patch new <name>` | Create a new named patch from current changes |
| `patch list [-v]` | List all patches in the stack with stats |
| `patch show <name\|index>` | Show full diff for a specific patch |
| `patch edit <name\|index>` | Amend an existing patch (stage fixes first) |
| `patch drop <name\|index>` | Remove a patch from the stack |
| `patch reorder` | Interactively reorder, squash, or drop patches |
| `patch export [dir]` | Export patches as `.patch` files with series file |
| `patch import <file\|dir>` | Import `.patch` files into the stack |
| `sync [--dry-run] [--force]` | Fetch upstream and rebase all patches |
| `undo` | Revert patches branch to pre-sync state |
| `status` | Health check: drift, patches, conflict prediction |
| `doctor` | Full diagnostic with test rebase |
| `diff` | Combined diff of all patches vs upstream |
| `log` | Show sync history (tracking branch reflog) |
| `conflict-analyze` | Analyze rebase conflicts with structured output |
| `auto-sync` | Generate GitHub Actions workflow for automated syncing |
| `version` | Print version |
| `help` | Print usage summary |

**Global flags:**

| Flag | Description |
|---|---|
| `--json` | Structured JSON output on all commands (for AI agents and scripts) |
| `--yes` | Non-interactive mode: skip all confirmation prompts |

## How It Works

```
  upstream (github.com/original/project)
      |
      |  git fetch
      v
  upstream-tracking -------- exact mirror, never touched manually
      |
      |  rebase
      v
  pingo-patches ------------ your customizations live here
      |
      +-- [pl] dark-mode:     support dark color scheme
      +-- [pl] api-cache:     add Redis caching layer
      +-- [pl] fix-typo:      fix README typo
      |
      v
    HEAD (your working fork)
```

**Sync flow:** `fetch upstream` -> `fast-forward upstream-tracking` -> `rebase pingo-patches onto upstream-tracking`. Your patches always sit cleanly on top. Rerere remembers every conflict resolution automatically.

**AI conflict flow:** when rebase hits a conflict, the AI calls `pingo_conflict_analyze` to get structured data about each conflicted file (ours, theirs, hints), writes the resolved content via `pingo_conflict_resolve`, and the rebase continues. No manual intervention.

**Config** is stored in `.pingolight` (git-config format) and excluded from version control via `.git/info/exclude` -- zero noise in your repo.

## Integration Guide

### Claude Code

With the MCP server configured, Claude Code can manage your fork autonomously. Example session:

```
You: "Sync my fork with upstream and fix any conflicts."

Claude Code:
  1. Calls pingo_status(cwd="/path/to/repo")
     -> sees 12 commits behind, 2 conflict-risk files
  2. Calls pingo_sync(cwd="/path/to/repo", dry_run=true)
     -> dry run shows 1 conflict in src/config.py
  3. Calls pingo_sync(cwd="/path/to/repo")
     -> rebase starts, stops at conflict
  4. Calls pingo_conflict_analyze(cwd="/path/to/repo")
     -> gets structured conflict data with ours/theirs content
  5. Reads both versions, writes merged content
  6. Calls pingo_conflict_resolve(cwd="/path/to/repo", file="src/config.py", content="...")
     -> conflict resolved, rebase continues to completion
  7. Calls pingo_status(cwd="/path/to/repo")
     -> confirms: 0 behind, all patches applied cleanly
```

### Aider

Aider can call pingo-light directly through shell commands with JSON output:

```bash
# In your aider session or automation script:
pingo-light status --json          # Parse fork state
pingo-light sync --yes             # Non-interactive sync
pingo-light conflict-analyze --json # Get conflict data if sync fails
```

Aider reads the JSON, understands the conflict structure, edits the file, then:

```bash
git add src/config.py
git rebase --continue
```

### Custom Python agent

```python
import subprocess
import json

def pingo(cmd, cwd="/path/to/repo"):
    """Call pingo-light with JSON output."""
    result = subprocess.run(
        ["pingo-light"] + cmd.split() + ["--json", "--yes"],
        cwd=cwd, capture_output=True, text=True
    )
    return json.loads(result.stdout)

# Check fork state
status = pingo("status")
print(f"Behind upstream by {status['behind']} commits")
print(f"Conflict risk: {status['conflict_risk']}")

# Sync with upstream
result = pingo("sync")
if result.get("conflicts"):
    # Analyze conflicts
    analysis = pingo("conflict-analyze")
    for conflict in analysis["conflicts"]:
        resolved = my_llm_resolve(conflict["ours"], conflict["theirs"], conflict["hint"])
        # Write resolution through CLI
        subprocess.run(
            ["pingo-light", "conflict-resolve", conflict["file"], "--content", resolved],
            cwd="/path/to/repo"
        )

# Verify
status = pingo("status")
assert status["behind"] == 0
```

## Quick Install

**One-liner:**

```bash
curl -fsSL https://raw.githubusercontent.com/user/pingo-light/main/pingo-light -o /usr/local/bin/pingo-light && chmod +x /usr/local/bin/pingo-light
```

**From source:**

```bash
git clone https://github.com/user/pingo-light.git
cd pingo-light
./install.sh            # installs to /usr/local/bin (uses sudo if needed)
```

**Manual:**

```bash
cp pingo-light /usr/local/bin/pingo-light
chmod +x /usr/local/bin/pingo-light
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

The entire tool is a single bash script (`pingo-light`, ~1300 lines). The MCP server is a single Python file (`mcp-server.py`, zero dependencies beyond Python 3.8+). No build step -- edit and test directly.

```bash
# Quick test setup
mkdir /tmp/test-upstream && cd /tmp/test-upstream && git init && echo "hello" > file.txt && git add -A && git commit -m "init"
git clone /tmp/test-upstream /tmp/test-fork && cd /tmp/test-fork
pingo-light init /tmp/test-upstream
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

## License

[MIT](LICENSE) -- use it, fork it, patch it (with pingo-light, of course).

---

<details>
<summary><b>简体中文</b></summary>

## pingo-light -- AI 原生的 Fork 维护工具

### 为什么是 AI 原生？

AI 编程代理（Claude Code、Aider、Cursor 代理、自定义流水线）正在越来越多地处理 Fork 仓库中的实际工作。它们添加功能、修复 Bug、回移补丁。但当上游推进时，Fork 开始漂移，没有人能很好地回答 "AI 如何让这个 Fork 保持同步？"

pingo-light 就是那座桥梁。AI 调用 MCP 工具，补丁作为干净的栈来管理，上游保持同步 ---- 包括全自动的冲突解决。

### 核心特性

- **MCP 服务器** -- 15 个工具覆盖从初始化到冲突解决的完整生命周期
- **`--json` 标志** -- 所有命令返回结构化 JSON，代理可靠解析
- **`--yes` 标志** -- 完全非交互模式，无需 TTY
- **`conflict-analyze`** -- 返回结构化冲突数据（文件路径、ours/theirs 内容、冲突数量、提示）
- **`pingo_conflict_resolve`** -- AI 通过 MCP 直接写入解决后的内容，自动暂存并继续 rebase
- **单文件，零依赖** -- 只需 bash + git
- **命名补丁栈** -- 每个自定义修改都是一个独立的、命名的补丁
- **一键同步** -- `pingo-light sync` 获取上游更新并变基所有补丁
- **冲突预测** -- `pingo-light status` 提前警告潜在冲突
- **冲突记忆** -- git rerere 自动记住冲突解决方案，同样的冲突只需解决一次

### AI 工作流程

```
AI 代理                                     pingo-light
------                                      -----------
pingo_init(cwd, upstream_url)           --> 设置上游追踪
pingo_patch_new(cwd, name, description) --> 创建补丁
pingo_status(cwd)                       --> {"behind": 5, "conflict_risk": ["app.py"]}
pingo_sync(cwd)                         --> 变基补丁到上游
pingo_conflict_analyze(cwd)             --> {"conflicts": [{file, ours, theirs}]}
pingo_conflict_resolve(cwd, file, content) --> 写入修复，暂存，继续 rebase
```

### 快速开始

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/user/pingo-light/main/pingo-light -o /usr/local/bin/pingo-light && chmod +x /usr/local/bin/pingo-light

# 初始化
cd my-forked-project
pingo-light init https://github.com/original/project.git

# 创建补丁
vim src/feature.py
pingo-light patch new my-feature

# 与上游同步
pingo-light sync
```

### MCP 服务器配置

在 Claude Code 的 `.mcp.json` 或 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "pingo-light": {
      "command": "python3",
      "args": ["/path/to/pingo-light/mcp-server.py"]
    }
  }
}
```

配置后，AI 代理可以直接调用 `pingo_status`、`pingo_sync`、`pingo_conflict_analyze` 等 MCP 工具来管理你的 Fork。

</details>

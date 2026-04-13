<p align="center">
  <br>
  <img src="docs/logo.svg" alt="bingo-light logo" width="200">
  <br><br>
  <strong>面向人类和 AI 代理的 Fork 维护工具。<br>一条命令同步。零依赖。</strong>
  <br><br>
  <a href="README.en.md">English</a> | <b>简体中文</b>
  <br><br>
  <a href="https://github.com/DanOps-1/bingo-light/actions"><img src="https://github.com/DanOps-1/bingo-light/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/DanOps-1/bingo-light/releases"><img src="https://img.shields.io/github/v/release/DanOps-1/bingo-light?label=Release&color=orange" alt="Release"></a>
  <a href="#mcp-服务器"><img src="https://img.shields.io/badge/MCP_Server-29_tools-blueviolet.svg" alt="MCP: 27 tools"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.8+-3776ab.svg" alt="Python 3.8+"></a>
  <img src="https://img.shields.io/badge/Dependencies-Zero-brightgreen.svg" alt="Zero deps">
  <a href="https://github.com/DanOps-1/bingo-light/stargazers"><img src="https://img.shields.io/github/stars/DanOps-1/bingo-light?style=social" alt="Stars"></a>
  <br><br>
</p>

GitHub 的 "Sync fork" 按钮一碰到你的定制化改动就报废。`git rebase` 是个 6 步仪式。而且这些东西没一个能从 AI 代理调用。

**bingo-light 三个问题一起解决。**

你的补丁作为干净的栈叠在上游之上。同步就是 `bingo-light sync`。冲突自动记忆，解决一次永远不用再解决。出了问题 `bingo-light undo` 一秒复原。

每条命令都输出 JSON。内置 MCP 服务器提供 29 个工具，让 AI 代理自主管理你的 Fork — 从初始化到冲突解决，全程无需人工介入。

---

## 目录

- [快速开始](#快速开始)
- [演示](#演示)
- [安装](#安装)
- [功能特性](#功能特性)
- [工作原理](#工作原理)
- [MCP 服务器](#mcp-服务器)
- [命令参考](#命令参考)
- [集成指南](#集成指南)
- [配置](#配置)
- [常见问题](#常见问题)
- [与其他方案对比](#与其他方案对比)
- [项目生态](#项目生态)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

---

## 快速开始

```bash
# 安装（任选一种）
pip install bingo-light             # Python
npm install -g bingo-light          # Node.js
brew install DanOps-1/tap/bingo-light  # Homebrew

# 初始化 Fork 追踪
cd my-forked-project
bingo-light init https://github.com/original/project.git

# 改代码，创建命名补丁
vim src/feature.py
bingo-light patch new my-feature

# 与上游同步（补丁自动变基到最新上游之上）
bingo-light sync
```

搞定。你的补丁始终是干净的栈，叠在上游最新代码之上。想同步就同步。

## 演示

### 基本流程：初始化、创建补丁、同步

<p align="center">
  <img src="docs/demo.svg" alt="bingo-light 基本演示" width="850">
</p>

### 冲突解决：同步、分析、修复

<p align="center">
  <img src="docs/demo-conflict.svg" alt="bingo-light 冲突解决演示" width="850">
</p>

> AI 调用 `conflict-analyze --json`，读取结构化的 ours/theirs 数据，写入合并后的文件，rebase 自动继续。全程不需要人。

### AI 获取结构化 JSON

```
$ bingo-light status --json
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

### 冲突解决（AI 工作流）

```
$ bingo-light conflict-analyze --json
```
```json
{
  "rebase_in_progress": true,
  "current_patch": "custom-scheduler",
  "conflicts": [
    {
      "file": "kernel/sched/core.c",
      "conflict_count": 2,
      "ours": "... 上游版本 ...",
      "theirs": "... 你的补丁版本 ...",
      "hint": "上游重构了调度器核心；补丁需要适配新结构。"
    }
  ]
}
```

## 安装

任选一种安装方式，然后运行 `bingo-light setup` 交互式配置 MCP（支持 Claude Code、Cursor、Windsurf、VS Code/Copilot、Zed、Gemini CLI 等）。

### pip / pipx

```bash
pip install bingo-light        # 或: pipx install bingo-light
bingo-light setup              # 交互式选择要配置的 AI 工具
```

### npm / npx

```bash
npm install -g bingo-light     # 全局安装
bingo-light setup

# 或用 npx 免安装：
npx bingo-light setup
```

MCP 客户端可直接使用 npx：
```json
{"command": "npx", "args": ["-y", "bingo-light-mcp"]}
```

### Homebrew

```bash
brew install DanOps-1/tap/bingo-light
bingo-light setup
```

### Docker

```bash
# CLI
docker run --rm -v "$PWD:/repo" -w /repo ghcr.io/danops-1/bingo-light status

# MCP 服务器（stdio 传输）
docker run --rm -i -v "$PWD:/repo" -w /repo ghcr.io/danops-1/bingo-light mcp-server.py
```

### Shell 安装器

```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | sh

# 非交互模式（CI / Docker）
curl -fsSL .../install.sh | sh -s -- --yes
```

### 从源码安装

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make install && bingo-light setup
```

**依赖：** Python 3.8+, git 2.20+。零 pip 依赖。

## 功能特性

### 给 AI 代理用

| 功能 | 说明 |
|------|------|
| **MCP 服务器** | 29 个工具，覆盖从初始化到冲突解决的全流程 |
| **`--json` 标志** | 所有命令返回结构化 JSON |
| **`--yes` 标志** | 完全非交互，不需要 TTY |
| **自动检测非 TTY** | 管道或子进程调用时自动抑制交互提示 |
| **`BINGO_DESCRIPTION`** | 通过环境变量设置补丁描述 |
| **`conflict-analyze`** | 结构化冲突数据：文件、ours、theirs、提示 |
| **`conflict-resolve`** | 通过 MCP 写入解决内容，自动暂存，继续 rebase |
| **Advisor 代理** | `contrib/agent.py` 监控漂移、分析风险、安全时自动同步 |

### 给人类用

| 功能 | 说明 |
|------|------|
| **零依赖** | Python 3 + git，`pip install bingo-light` 即可 |
| **命名补丁栈** | 每个改动都是一个独立的、有名字的 commit |
| **一键同步** | `bingo-light sync` 把你的补丁变基到上游之上 |
| **预演模式** | `sync --dry-run` 先在临时分支上试跑 |
| **冲突记忆** | git rerere 自动启用；解决一次，永远不用再解决 |
| **一键撤销** | `bingo-light undo` 瞬间恢复同步前状态 |
| **冲突预测** | `status` 提前告诉你哪些文件可能冲突 |
| **诊断** | `doctor` 全面诊断 + 测试变基 |
| **导出/导入** | 补丁导出为 `.patch` 文件（兼容 quilt） |
| **CI 自动同步** | 生成 GitHub Actions 工作流，冲突时自动告警 |
| **TUI 面板** | 基于 curses 的实时监控面板（`contrib/tui.py`） |
| **多仓库** | `workspace` 一个地方管理所有 Fork |
| **Shell 补全** | bash、zsh、fish 全支持 |
| **通知 Hook** | Discord、Slack、通用 Webhook，同步/冲突/测试事件触发 |
| **补丁元数据** | 标签、原因、过期日期、上游 PR 追踪 |
| **测试集成** | 同步后自动跑测试，失败自动回滚 |

## 工作原理

```
  upstream (github.com/original/project)
      |
      |  git fetch
      v
  upstream-tracking ─────── 上游的精确镜像，从不手动碰
      |
      |  git rebase
      v
  bingo-patches ─────────── 你的改动叠在这里
      |
      +── [bl] custom-scheduler:  O(1) 任务调度
      +── [bl] perf-monitoring:   eBPF 追踪钩子
      +── [bl] fix-logging:       结构化 JSON 日志
      |
      v
    HEAD (你的工作 Fork)
```

**同步流程：** 拉取上游 -> 快进追踪分支 -> 把补丁变基到上游之上。你的补丁始终干净地叠在最新代码上。

**冲突记忆：** 初始化时自动启用 git rerere。解决一次冲突，git 就记住了 -- 下次同步碰到同样的冲突，自动应用之前的修复。

**AI 冲突流程：** rebase 碰到冲突时，AI 调用 `conflict-analyze` 获取结构化数据（每个文件的 ours/theirs/提示），通过 `conflict-resolve` 写入解决内容，rebase 自动继续。全程不需要人。

## MCP 服务器

`mcp-server.py` 是零依赖的 Python 3 MCP 服务器，通过 stdio 暴露 29 个工具（JSON-RPC 2.0）。

### 配置

**Claude Code** -- 添加到 `.mcp.json` 或 `~/.claude/settings.json`：

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

**Claude Desktop** -- 添加到 `~/Library/Application Support/Claude/claude_desktop_config.json`：

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

**任意 MCP 客户端**（VS Code Copilot、Cursor、自定义代理）：通过 stdio 连接 `python3 mcp-server.py`。

### 全部工具

| 工具 | 用途 |
|------|------|
| `bingo_init` | 初始化 Fork 追踪 |
| `bingo_status` | 健康检查：漂移、补丁、冲突风险 |
| `bingo_sync` | 拉取上游并变基补丁 |
| `bingo_undo` | 恢复到同步前状态 |
| `bingo_patch_new` | 创建命名补丁 |
| `bingo_patch_list` | 列出补丁栈 |
| `bingo_patch_show` | 查看补丁 diff |
| `bingo_patch_drop` | 移除补丁 |
| `bingo_patch_export` | 导出为 `.patch` 文件 |
| `bingo_patch_import` | 导入 `.patch` 文件 |
| `bingo_patch_meta` | 获取/设置补丁元数据 |
| `bingo_patch_squash` | 合并两个补丁 |
| `bingo_patch_reorder` | 非交互式重排补丁 |
| `bingo_doctor` | 全面诊断 + 测试变基 |
| `bingo_diff` | 补丁总 diff vs 上游 |
| `bingo_auto_sync` | 生成 GitHub Actions 工作流 |
| `bingo_conflict_analyze` | AI 用的结构化冲突数据 |
| `bingo_conflict_resolve` | 写入解决内容，暂存，继续 rebase |
| `bingo_config` | 获取/设置配置 |
| `bingo_history` | 同步历史 + hash 映射 |
| `bingo_test` | 运行测试套件 |
| `bingo_workspace_status` | 多仓库工作区概览 |
| `bingo_patch_edit` | 修改已有补丁 |
| `bingo_workspace_init` | 初始化多仓库工作区 |
| `bingo_workspace_add` | 添加仓库到工作区 |
| `bingo_workspace_sync` | 同步工作区所有仓库 |
| `bingo_workspace_list` | 列出工作区仓库 |

## 命令参考

```
bingo-light init <upstream-url> [branch]     初始化上游追踪
bingo-light patch new <name>                 创建命名补丁
bingo-light patch list [-v]                  列出补丁栈
bingo-light patch show <name|index>          查看补丁 diff
bingo-light patch edit <name|index>          修改补丁（先暂存变更）
bingo-light patch drop <name|index>          移除补丁
bingo-light patch reorder [--order "3,1,2"]  重排补丁
bingo-light patch export [dir]               导出为 .patch 文件
bingo-light patch import <file|dir>          导入 .patch 文件
bingo-light patch squash <idx1> <idx2>       合并两个补丁
bingo-light patch meta <name> [key] [value]  获取/设置补丁元数据
bingo-light sync [--dry-run] [--force]       与上游同步
bingo-light sync --test                      同步后跑测试，失败自动回滚
bingo-light undo                             恢复到同步前状态
bingo-light status                           健康检查 + 冲突预测
bingo-light doctor                           全面诊断
bingo-light diff                             补丁总 diff vs 上游
bingo-light log                              同步历史
bingo-light conflict-analyze                 分析 rebase 冲突
bingo-light config get|set|list [key] [val]  管理配置
bingo-light history                          详细同步历史 + 映射
bingo-light test                             运行测试套件
bingo-light workspace init|add|status|sync   多仓库管理
bingo-light auto-sync                        生成 GitHub Actions 工作流
bingo-light version                          打印版本
bingo-light help                             打印帮助
```

**全局标志：** `--json`（结构化 JSON 输出） | `--yes`（跳过所有确认提示）

## 集成指南

### Claude Code (MCP)

配置好 MCP 服务器后，Claude Code 端到端管理你的 Fork：

```
你: "把我的 Fork 和上游同步，修复所有冲突。"

Claude Code:
  1. bingo_status(cwd)        -> 落后 47 个 commit，风险文件: core.c
  2. bingo_sync(cwd, dry_run) -> 预测 1 个冲突
  3. bingo_sync(cwd)          -> rebase 在冲突处停下
  4. bingo_conflict_analyze() -> 结构化 ours/theirs/提示
  5. 读取双方版本，生成合并内容
  6. bingo_conflict_resolve(cwd, file, content) -> 搞定
  7. bingo_status(cwd)        -> 0 落后，所有补丁干净
```

### Aider / CLI 代理

```bash
bingo-light status --json          # 解析 Fork 状态
bingo-light sync --yes             # 非交互同步
bingo-light conflict-analyze --json # 结构化冲突数据
```

### 自定义 Python 代理

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
            # 通过 CLI 或 MCP 写入解决内容
```

## 配置

配置存储在 `.bingolight`（git-config 格式），通过 `.git/info/exclude` 排除在版本控制之外。

```bash
bingo-light config set sync.auto-test true     # 同步后自动跑测试
bingo-light config set test.command "make test" # 测试命令
bingo-light config list                         # 查看所有配置
```

### 通知 Hook

在 `.bingo/hooks/` 中放置可执行脚本：

| Hook | 触发时机 |
|------|---------|
| `on-sync-success` | 同步成功后 |
| `on-conflict` | rebase 碰到冲突时 |
| `on-test-fail` | 同步后测试失败时 |

每个 Hook 通过 stdin 接收 JSON 数据。示例见 [contrib/hooks/](contrib/hooks/)（Slack、Discord、通用 Webhook）。

## 常见问题

<details>
<summary><b>为什么不直接 <code>git rebase</code>？</b></summary>

可以啊。bingo-light 自动化了 rebase 周边那堆烦人的操作：追踪上游远程、维护专用补丁分支、启用 rerere、同步前预测冲突、给自动化提供结构化输出。一次性 rebase 用不着这工具。但如果你长期维护 3 个以上补丁，它能省下大量时间。
</details>

<details>
<summary><b>能用在已有的 Fork 上吗？</b></summary>

能。在你的 Fork 里跑 `bingo-light init <upstream-url>`，然后用 `bingo-light patch new <name>` 把已有的改动转成命名补丁。任何标准 git 仓库都行。
</details>

<details>
<summary><b>只给 AI 用吗？人也能用吗？</b></summary>

当然都能用。`bingo-light sync` 这条命令，你跑和 AI 跑效果完全一样。AI 原生功能（`--json`、`--yes`、MCP）是纯增量的附加能力。不加这些标志，输出就是正常的人类友好格式。
</details>

<details>
<summary><b>冲突记忆是怎么回事？</b></summary>

bingo-light 在 `init` 时自动启用 git 的 `rerere`（reuse recorded resolution）。你解决一次冲突，git 就记住了。下次同步碰到同样的冲突，自动应用之前的修复。bingo-light 还会检测已自动解决的冲突并继续 rebase，不会傻等你。
</details>

<details>
<summary><b>同步搞砸了怎么办？</b></summary>

跑 `bingo-light undo`。它把补丁分支恢复到同步前的精确状态。基于 git reflog 实现，即使经历了复杂的 rebase 也稳得很。
</details>

<details>
<summary><b>支持 GitHub/GitLab/Bitbucket 吗？</b></summary>

支持。bingo-light 用的是标准 git 操作（fetch、rebase、push），跟任何 git 远程都能配合。`auto-sync` 命令生成 GitHub Actions 工作流，但核心工具跟平台无关。
</details>

<details>
<summary><b>和 <code>git format-patch</code> / quilt 有什么区别？</b></summary>

`format-patch` 能导出补丁，但不管理活的补丁栈。quilt 管理补丁，但在 git 体系之外运作。bingo-light 把补丁保持为真正的 git commit，所以你拥有完整的 git 历史、冲突解决能力、rerere 记忆 -- 同时还能以 quilt 兼容格式导出/导入。
</details>

## 为什么不用...

<details>
<summary><b>...GitHub 的 "Sync fork" 按钮？</b></summary>
<br>

它只能做 fast-forward。只要你有任何定制化改动（fork 上有上游没有的 commit），它要么拒绝，要么创建一个 merge commit 把你的改动埋起来。它没有补丁栈的概念，没有冲突记忆，没有给 AI 代理用的 API。
</details>

<details>
<summary><b>...手动 <code>git rebase</code>？</b></summary>
<br>

你可以。需要 6 步：fetch、checkout tracking 分支、pull、checkout patches 分支、rebase、push。你得记住哪个分支是哪个，手动启用 rerere，出了问题还得祈祷 reflog 没搞乱。bingo-light 把这些全包进 `bingo-light sync`，带自动撤销、冲突预测和结构化输出。
</details>

<details>
<summary><b>...StGit / quilt / TopGit？</b></summary>
<br>

StGit（649 stars）管理补丁栈但没有 AI 集成、没有 MCP 服务器、没有 JSON 输出、没有冲突预测。quilt 完全在 git 体系之外运作 — 没有 rerere，没有历史。TopGit 基本已经废弃。它们都不是为 AI 代理时代设计的。
</details>

## 与其他方案对比

| | **bingo-light** | GitHub Sync | git rebase | quilt | StGit |
|---|:---:|:---:|:---:|:---:|:---:|
| 命名补丁栈 | **有** | 无 | 无 | 有 | 有 |
| 一键同步 | **有** | 仅按钮 | 无（6 步） | 无 | 无 |
| 处理定制化改动 | **有** | **不行** | 手动 | 手动 | 手动 |
| 冲突记忆 (rerere) | **自动** | 无 | 需手动启用 | 无 | 无 |
| 冲突预测 | **有** | 无 | 无 | 无 | 无 |
| AI/MCP 集成 | **29 个工具** | 无 | 无 | 无 | 无 |
| JSON 输出 | **所有命令** | 无 | 无 | 无 | 无 |
| 非交互模式 | **原生支持** | 无 | 部分 | 部分 | 部分 |
| 撤销同步 | **一条命令** | 无 | git reflog | 手动 | 手动 |
| 安装方式 | 一条命令 | 内置 | 内置 | 包管理器 | 包管理器 |

## 项目生态

```
bingo-light          CLI 入口（Python 3，零依赖）
bingo_core/          核心库包（全部业务逻辑）
mcp-server.py        MCP 服务器（零依赖 Python 3，29 个工具）
contrib/agent.py     Advisor 代理（监控 + 分析 + 安全时自动同步）
contrib/tui.py       终端面板（curses TUI）
install.sh           安装器（--yes 支持 CI，--help 查看选项）
completions/         Shell 补全（bash/zsh/fish）
contrib/hooks/       通知 Hook 示例（Slack/Discord/Webhook）
tests/               测试套件（250 个测试，5 个文件）
docs/                文档
```

## 参与贡献

欢迎贡献。纯 Python，零依赖，不需要构建。

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make test       # 核心测试
make test-all   # 全部 250 个测试
make lint       # Python 语法 + flake8 + shellcheck
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)

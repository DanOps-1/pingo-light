<p align="center">
  <br>
  <code>&nbsp;  _     _                         _ _       _     _    &nbsp;</code><br>
  <code>&nbsp; | |__ (_)_ __   __ _  ___       | (_) __ _| |__ | |_  &nbsp;</code><br>
  <code>&nbsp; | '_ \| | '_ \ / _` |/ _ \ ____| | |/ _` | '_ \| __| &nbsp;</code><br>
  <code>&nbsp; | |_) | | | | | (_| | (_) |____| | | (_| | | | | |_  &nbsp;</code><br>
  <code>&nbsp; |_.__/|_|_| |_|\__, |\___/     |_|_|\__, |_| |_|\__| &nbsp;</code><br>
  <code>&nbsp;                |___/                 |___/             &nbsp;</code><br>
  <br>
  <strong>AI 原生的 Fork 维护工具。保留你的补丁，与上游保持同步。</strong>
  <br><br>
  <a href="README.md">English</a> | <b>简体中文</b>
  <br><br>
  <a href="https://github.com/DanOps-1/bingo-light/actions"><img src="https://github.com/DanOps-1/bingo-light/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/DanOps-1/bingo-light/releases"><img src="https://img.shields.io/github/v/release/DanOps-1/bingo-light?label=Release&color=orange" alt="Release"></a>
  <a href="#mcp-服务器"><img src="https://img.shields.io/badge/MCP-22_tools-blueviolet.svg" alt="MCP: 22 tools"></a>
  <a href="https://www.gnu.org/software/bash/"><img src="https://img.shields.io/badge/Made_with-Bash-1f425f.svg" alt="Bash"></a>
  <br><br>
</p>

你维护了一个 Fork，添加了上游没有的功能。上游推送了 50 个 commit，你的 Fork 就卡住了。

**bingo-light 解决这个问题** -- 你的补丁作为干净的栈叠在上游之上，同步只需一条命令。

为 **AI 代理**设计（MCP 服务器、结构化 JSON、非交互模式），**人类**也能直接用（单文件、零依赖、bash + git 就够了）。

---

## 目录

- [快速开始](#快速开始)
- [演示](#演示)
- [安装](#安装)
- [功能](#功能)
- [工作原理](#工作原理)
- [MCP 服务器](#mcp-服务器)
- [命令参考](#命令参考)
- [集成指南](#集成指南)
- [配置](#配置)
- [常见问题](#常见问题)
- [与其他方案对比](#与其他方案对比)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

---

## 快速开始

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | bash

# 初始化 Fork 追踪
cd my-forked-project
bingo-light init https://github.com/original/project.git

# 修改代码，创建命名补丁
vim src/feature.py
bingo-light patch new my-feature

# 与上游同步（补丁自动变基到上游之上）
bingo-light sync
```

就这么简单。你的补丁始终是干净的栈，叠在上游最新代码之上。随时同步。

## 演示

<p align="center">
  <img src="docs/demo.svg" alt="bingo-light demo" width="850">
</p>

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

### AI 冲突解决流程

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

### 交互式安装器（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | bash
```

安装器会设置：CLI、Shell 补全、Claude MCP 服务器、`/bingo` AI 技能。

### Homebrew (macOS/Linux)

```bash
brew install DanOps-1/tap/bingo-light
```

### 从源码安装

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make install       # 安装到 /usr/local/bin
make completions   # bash/zsh/fish 补全
```

### 手动安装

```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/bingo-light \
  -o /usr/local/bin/bingo-light && chmod +x /usr/local/bin/bingo-light
```

**依赖：** bash 4.0+, git 2.20+, Python 3.8+（仅 MCP 服务器需要）

## 功能

### 给 AI 代理用

| 功能 | 说明 |
|------|------|
| **MCP 服务器** | 22 个工具覆盖从初始化到冲突解决的全流程 |
| **`--json` 标志** | 所有命令返回结构化 JSON |
| **`--yes` 标志** | 完全非交互，不需要 TTY |
| **自动检测非 TTY** | 管道调用时自动抑制交互提示 |
| **`BINGO_DESCRIPTION`** | 通过环境变量设置补丁描述 |
| **`conflict-analyze`** | 结构化冲突数据：文件、ours、theirs、提示 |
| **`conflict-resolve`** | 通过 MCP 写入解决内容，自动暂存，继续 rebase |
| **Advisor 代理** | `agent.py` 监控漂移、分析风险、安全时自动同步 |

### 给人类用

| 功能 | 说明 |
|------|------|
| **单文件，零依赖** | 只需 bash + git，放进 PATH 就能用 |
| **命名补丁栈** | 每个修改都是独立的、有名字的 commit |
| **一键同步** | `bingo-light sync` 把补丁变基到上游之上 |
| **预演模式** | `sync --dry-run` 先在临时分支上测试 |
| **冲突记忆** | git rerere 自动记住解决方案，同样的冲突只解决一次 |
| **一键撤销** | `bingo-light undo` 恢复同步前状态 |
| **冲突预测** | `status` 提前警告哪些文件有冲突风险 |
| **诊断** | `doctor` 全面诊断 + 测试变基 |
| **导出/导入** | 补丁导出为 `.patch` 文件（兼容 quilt） |
| **CI 自动同步** | 生成 GitHub Actions 工作流 |
| **TUI 面板** | 基于 curses 的实时监控 (`tui.py`) |
| **多仓库** | `workspace` 命令管理多个 Fork |
| **Shell 补全** | bash/zsh/fish 自动补全 |
| **通知 Hook** | Discord、Slack、通用 Webhook |
| **补丁元数据** | 标签、原因、过期日期、上游 PR 追踪 |
| **测试集成** | 同步后跑测试，失败自动回滚 |

## 工作原理

```
  upstream (github.com/original/project)
      |
      |  git fetch
      v
  upstream-tracking ─────── 上游的精确镜像，从不手动修改
      |
      |  git rebase
      v
  bingo-patches ─────────── 你的修改叠在这里
      |
      +── [bl] custom-scheduler:  O(1) 任务调度
      +── [bl] perf-monitoring:   eBPF 追踪钩子
      +── [bl] fix-logging:       结构化 JSON 日志
      |
      v
    HEAD (你的工作 Fork)
```

**同步流程：** 拉取上游 -> 快进追踪分支 -> 把补丁变基到上游之上。你的补丁始终干净地叠在最新的上游代码上。

**冲突记忆：** 初始化时自动启用 git rerere。解决一次冲突，git 就记住了 -- 下次同步自动应用同样的修复。

**AI 冲突流程：** rebase 碰到冲突时，AI 调用 `conflict-analyze` 获取结构化数据（每个文件的 ours/theirs/提示），通过 `conflict-resolve` 写入解决内容，rebase 自动继续。不需要人工干预。

## MCP 服务器

`mcp-server.py` 是零依赖的 Python 3 MCP 服务器，通过 stdio 暴露 22 个工具（JSON-RPC 2.0）。

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

**任意 MCP 客户端**（VS Code Copilot、Cursor 等）：通过 stdio 连接 `python3 mcp-server.py`。

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

配置 MCP 服务器后，Claude Code 可以端到端管理你的 Fork：

```
你: "把我的 Fork 和上游同步，修复所有冲突。"

Claude Code:
  1. bingo_status(cwd)        -> 落后 47 个 commit，风险文件: core.c
  2. bingo_sync(cwd, dry_run) -> 预测 1 个冲突
  3. bingo_sync(cwd)          -> rebase 在冲突处停止
  4. bingo_conflict_analyze() -> 结构化 ours/theirs/提示
  5. 读取双方版本，生成合并内容
  6. bingo_conflict_resolve(cwd, file, content) -> 完成
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

每个 Hook 通过 stdin 接收 JSON。示例见 [contrib/hooks/](contrib/hooks/)。

## 常见问题

<details>
<summary><b>为什么不直接 <code>git rebase</code>？</b></summary>

可以。bingo-light 自动化了周围的仪式：追踪上游远程、维护专用补丁分支、启用 rerere、同步前预测冲突、提供结构化输出给自动化。一次性 rebase 用不着它。3 个以上补丁的长期维护，它能省下真正的时间。
</details>

<details>
<summary><b>能用在已有的 Fork 上吗？</b></summary>

可以。在你的 Fork 里运行 `bingo-light init <upstream-url>`，然后用 `bingo-light patch new <name>` 把已有修改转为命名补丁。任何标准 git 仓库都能用。
</details>

<details>
<summary><b>只给 AI 用吗？人也能用吗？</b></summary>

人和 AI 都能用。`bingo-light sync` 无论是你还是 AI 运行都是同一个命令。AI 原生的功能（`--json`、`--yes`、MCP）是纯增量的。不加这些标志，你就看到正常的人类友好输出。
</details>

<details>
<summary><b>冲突记忆怎么工作的？</b></summary>

bingo-light 在 `init` 时启用 git 的 `rerere`（reuse recorded resolution）。你解决一次冲突，git 就记住了。下次同样的冲突出现，自动应用之前的修复。bingo-light 还会检测自动解决的冲突并继续 rebase，不会停下来。
</details>

<details>
<summary><b>同步出问题了怎么办？</b></summary>

运行 `bingo-light undo`。它把补丁分支恢复到同步前的状态。基于 git reflog 实现，即使经过复杂的 rebase 也是可靠的。
</details>

<details>
<summary><b>支持 GitHub/GitLab/Bitbucket 吗？</b></summary>

支持。bingo-light 使用标准 git 操作（fetch、rebase、push），与任何 git 远程都能工作。`auto-sync` 命令生成 GitHub Actions 工作流，但核心工具与平台无关。
</details>

<details>
<summary><b>和 <code>git format-patch</code> / quilt 有什么区别？</b></summary>

`format-patch` 导出补丁但不管理活的补丁栈。quilt 管理补丁但在 git 之外操作。bingo-light 把补丁保存为真正的 git commit，所以你有完整的 git 历史、冲突解决、rerere -- 同时还支持以 quilt 兼容格式导出/导入。
</details>

## 与其他方案对比

| | bingo-light | git rebase (手动) | quilt | Stacked Diffs (spr/ghstack) |
|---|:---:|:---:|:---:|:---:|
| 命名补丁栈 | **有** | 无 | 有 | 有 |
| 一键上游同步 | **有** | 无（多步） | 无（需手动） | 部分 |
| 冲突记忆 (rerere) | **自动** | 需手动启用 | 无 | 无 |
| 冲突预测 | **有** | 无 | 无 | 无 |
| AI/MCP 集成 | **22 个工具** | 无 | 无 | 无 |
| 结构化 JSON 输出 | **所有命令** | 无 | 无 | 部分 |
| 非交互模式 | **原生** | 部分 | 部分 | 有 |
| 依赖 | bash + git | git | quilt | 语言特定 |
| 安装 | 单文件复制 | 内置 | 包管理器 | 包管理器 |
| 撤销同步 | **一键** | git reflog | 手动 | 看情况 |

## 项目生态

```
bingo-light          CLI 核心（单文件 bash 脚本）
mcp-server.py        MCP 服务器（零依赖 Python 3，22 个工具）
agent.py             Advisor 代理（监控 + 分析 + 安全自动同步）
tui.py               终端面板（curses TUI）
install.sh           交互式安装器（动画 TUI）
completions/         Shell 补全（bash/zsh/fish）
contrib/hooks/       通知 Hook 示例（Slack/Discord/Webhook）
tests/test.sh        71 个测试
docs/                文档
```

## 参与贡献

欢迎贡献！整个 CLI 是一个 bash 脚本。MCP 服务器是一个 Python 文件。无需构建步骤。

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make test    # 运行 71 个测试
make lint    # shellcheck
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)

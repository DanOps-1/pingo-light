<p align="center">
  <br>
  <img src="docs/logo.svg" alt="bingo-light logo" width="200">
  <br><br>
  <strong>让 AI 接管你的 Fork 维护。<br>同步、冲突、补丁管理 — 全自动。</strong>
  <br><br>
  <a href="README.en.md">English</a> | <b>简体中文</b>
  <br><br>
  <a href="https://github.com/DanOps-1/bingo-light/actions"><img src="https://github.com/DanOps-1/bingo-light/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/DanOps-1/bingo-light/releases"><img src="https://img.shields.io/github/v/release/DanOps-1/bingo-light?label=Release&color=orange" alt="Release"></a>
  <a href="#mcp-服务器"><img src="https://img.shields.io/badge/MCP_Server-49_tools-blueviolet.svg" alt="MCP: 49 tools"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.8+-3776ab.svg" alt="Python 3.8+"></a>
  <img src="https://img.shields.io/badge/Dependencies-Zero-brightgreen.svg" alt="Zero deps">
  <a href="https://github.com/DanOps-1/bingo-light/stargazers"><img src="https://img.shields.io/github/stars/DanOps-1/bingo-light?style=social" alt="Stars"></a>
  <br><br>
</p>

Fork 维护是个苦差事 — 上游一更新，你的定制化改动就得手动 rebase。GitHub 的 "Sync fork" 按钮碰到自定义 commit 直接废了。手动操作六步起步，冲突反复解，搞砸了还得从 reflog 里捞。

**装完 bingo-light，跟你的 AI 说一句"帮我同步 Fork"，剩下的它全搞定。**

内置 MCP 服务器 35 个工具，AI 自主完成：拉上游、rebase 补丁、分析冲突、写合并代码、继续 rebase。冲突解过一次自动记住（rerere），下次不再问。搞砸了 `undo` 秒回。

> [!TIP]
> **不想读文档？** 把这段丢给你的 AI，让它帮你装：
>
> ```
> 帮我安装 bingo-light 并配置好 MCP，参考：
> https://raw.githubusercontent.com/DanOps-1/bingo-light/main/docs/ai-setup.md
> ```

---

## 目录

- [安装](#安装)
- [演示](#演示)
- [功能特性](#功能特性)
- [MCP 服务器（35 工具）](#mcp-服务器)
- [工作原理](#工作原理)
- [命令参考](#命令参考)
- [集成指南](#集成指南)
- [配置](#配置)
- [常见问题](#常见问题)
- [与其他方案对比](#与其他方案对比)
- [项目生态](#项目生态)
- [参与贡献](#参与贡献)

---

## 安装

### 让 AI 帮你装（推荐）

把下面这段丢给你的 AI（Claude Code、Cursor、Windsurf 等），它会自动装好并配好 MCP + Skill：

```
帮我安装并配置 bingo-light，参考这个文档：
https://raw.githubusercontent.com/DanOps-1/bingo-light/main/docs/ai-setup.md
```

### 自己装

| 方式 | 命令 |
|------|------|
| **pip** | `pip install bingo-light && bingo-light setup` |
| **npm** | `npm install -g bingo-light && bingo-light setup` |
| **npx** | `npx bingo-light setup` |
| **Homebrew** | `brew install DanOps-1/tap/bingo-light && bingo-light setup` |

<details>
<summary><b>更多安装方式</b>（Docker / Shell / 源码）</summary>

**Docker**
```bash
docker run --rm -v "$PWD:/repo" -w /repo ghcr.io/danops-1/bingo-light status
docker run --rm -i -v "$PWD:/repo" -w /repo ghcr.io/danops-1/bingo-light mcp-server.py
```

**Shell 一键安装**
```bash
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | sh
```

**从源码**
```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light && make install && bingo-light setup
```

</details>

> [!NOTE]
> **依赖：** Python 3.8+ / git 2.20+，没了。零 pip 依赖。
>
> MCP 客户端可直接用 npx：`{"command": "npx", "args": ["-y", "bingo-light-mcp"]}`

---

## 演示

<table>
<tr>
<td width="50%">

### 日常操作

初始化 → 建补丁 → 同步上游

<p align="center">
  <img src="docs/demo.svg" alt="bingo-light 基本演示" width="100%">
</p>

</td>
<td width="50%">

### 冲突解决

同步 → AI 分析 → 自动修复

<p align="center">
  <img src="docs/demo-conflict.svg" alt="bingo-light 冲突解决演示" width="100%">
</p>

</td>
</tr>
</table>

> [!NOTE]
> AI 调 `conflict-analyze --json` 拿到双方代码和解决提示，写好合并结果，rebase 自动继续。全程零人工。

---

### `--json` 输出：AI 直接消费

<details open>
<summary><b>Fork 状态</b> — <code>bingo-light status --json</code></summary>

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

</details>

<details>
<summary><b>冲突分析</b> — <code>bingo-light conflict-analyze --json</code></summary>

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

</details>

<details>
<summary><b>AI 全自动解冲突</b> — Claude Code 实际工作流</summary>

```
你: "同步上游，冲突帮我修了。"

Claude Code:
  1. bingo_status(cwd)            → 落后 47 commit，risk: core.c
  2. bingo_sync(cwd, dry_run)     → 预判 1 个冲突
  3. bingo_sync(cwd)              → rebase 卡在冲突
  4. bingo_conflict_analyze()     → 拿到双方代码 + 提示
  5. 读两边，写合并结果
  6. bingo_conflict_resolve(file) → 搞定
  7. bingo_status(cwd)            → 0 落后，补丁干净 ✓
```

</details>

### 交互式 Setup

```console
$ bingo-light setup

  ◆  bingo-light setup  v2.x.x
  │
  ◆  MCP Server
  │  Connect bingo-light tools to your AI coding assistants
  │
  │  › ■ Claude Code        ~/.claude/settings.json
  │    ■ Cursor              ~/.cursor/mcp.json
  │    □ Windsurf            (not detected)
  │    ■ VS Code / Copilot   ~/.vscode/mcp.json
  │
  ◆  Skills / Custom Instructions
  │  Teach your AI how to use bingo-light
  │
  │    ■ Claude Code         ~/.claude/commands/bingo.md
  │    ■ Continue            ~/.continue/rules/bingo.md
  │
  └  5 MCP + 2 skill(s) configured — ready to go!
```

> [!TIP]
> 支持 10 个 AI 工具的 MCP 配置 + 6 个平台的 Skill 安装。方向键多选，一次配完。

## AI 如何使用 bingo-light

这才是重点。bingo-light 是为 AI agent 设计的 Fork 维护工具。

### AI 拿到什么

|  | 能力 | 说明 |
|---|------|------|
| 🔌 | **MCP 服务器** | 35 个工具，AI 直接调用，从 init 到冲突解决全链路 |
| 📊 | **结构化输出** | 所有命令 `--json` 输出，AI 直接 parse |
| 🤖 | **零交互** | `--yes` + 非 TTY 自适应，不会卡在确认提示 |
| 🔍 | **冲突分析** | `conflict-analyze` 返回双方代码 + AI 可执行的解决提示 |
| ✏️ | **冲突解决** | `conflict-resolve` 直接写入合并代码，自动 stage + 继续 rebase |
| 🧠 | **冲突记忆** | rerere 自动记住解法，同样冲突不用 AI 再解第二次 |
| 📋 | **Skill / 指令** | `/bingo` 教 AI 整套工作流，不用你写 prompt |
| 📦 | **依赖补丁** | `dep patch/apply/sync` — npm/pip 包改了不怕 install 覆盖 |
| 🔄 | **Advisor 代理** | `contrib/agent.py` 后台监控漂移，安全时自动同步 |

### AI 实际工作流

你说一句 **"同步上游"**，AI 自己跑完整个流程：

```
bingo_status()            → 落后 47 commit，risk: core.c
bingo_sync(dry_run=true)  → 预判 1 个冲突
bingo_sync()              → rebase 卡在冲突
bingo_conflict_analyze()  → 拿到 ours/theirs + hint
  → AI 读两边代码，写合并结果
bingo_conflict_resolve()  → 写入、stage、rebase 继续
bingo_status()            → 0 落后，补丁干净 ✓
```

> [!IMPORTANT]
> **你不需要理解 rebase、rerere、tracking branch 这些概念。** AI 全部处理。你只需要装好工具，告诉 AI 你想干嘛。

### 支持哪些 AI 工具

`bingo-light setup` 一键配好 MCP + Skill：

| AI 工具 | MCP | Skill |
|---------|:---:|:-----:|
| Claude Code | ✅ | ✅ |
| Cursor | ✅ | — |
| Windsurf | ✅ | ✅ |
| VS Code / Copilot | ✅ | — |
| Cline | ✅ | ✅ |
| Roo Code | ✅ | ✅ |
| Zed | ✅ | — |
| Gemini CLI | ✅ | ✅ |
| Continue | — | ✅ |
| Amazon Q | ✅ | — |

---

## 人也能用

不用 AI 也完全没问题。同一套命令，人跑和 AI 跑效果一样。

<details>
<summary><b>人类功能一览</b></summary>

| 功能 | 说明 |
|------|------|
| **一键同步** | `bingo-light sync`，补丁自动 rebase 到最新上游 |
| **命名补丁** | 每个改动是独立的、有名字的 commit |
| **先试后跑** | `sync --dry-run` 临时分支预演，不碰真代码 |
| **秒级撤销** | `bingo-light undo` 恢复同步前状态 |
| **冲突预警** | `status` 提前告诉你哪些文件会出事 |
| **自检修复** | `doctor` 全面体检 + 试跑 rebase |
| **导出导入** | `.patch` 文件，quilt 兼容 |
| **CI 自动同步** | 生成 GitHub Actions 流水线，冲突自动告警 |
| **TUI 面板** | curses 实时仪表盘（`contrib/tui.py`） |
| **多仓管理** | `workspace` 统一管所有 Fork |
| **补全** | bash / zsh / fish |
| **通知推送** | Discord、Slack、Webhook，事件触发 |
| **测试联动** | 同步后自动跑测试，挂了自动回滚 |

</details>

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

**同步：** fetch 上游 → 快进追踪分支 → rebase 补丁到最新上游。补丁永远干净地叠在最新代码上。

**冲突记忆：** 初始化时自动开 rerere。解过一次，git 就记住了——下次碰到同样的冲突直接跳过。

**AI 解冲突：** rebase 卡住时，AI 调 `conflict-analyze` 拿双方代码和提示，写好合并结果扔给 `conflict-resolve`，rebase 自动继续，不用人管。

## MCP 服务器

`mcp-server.py`，纯 Python 3，零依赖，stdio 传输，35 个工具，JSON-RPC 2.0。

运行 `bingo-light setup` 自动配置，或手动添加：

**Claude Code**（`.mcp.json` 或 `~/.claude/settings.json`）：

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

**Claude Desktop**（`~/Library/Application Support/Claude/claude_desktop_config.json`）：

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

**其他客户端**（Cursor、Windsurf、VS Code Copilot 等）：stdio 连 `python3 mcp-server.py`，或跑 `bingo-light setup` 一键配。

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
bingo-light dep patch <package> [name]        补丁 npm/pip 依赖
bingo-light dep apply [package]              重新应用依赖补丁
bingo-light dep sync                         更新后重新应用 + 冲突检测
bingo-light dep status                       依赖补丁健康状态
bingo-light dep list                         列出所有依赖补丁
bingo-light dep drop <package> [patch]       删除依赖补丁
bingo-light workspace init|add|status|sync   多仓库管理
bingo-light auto-sync                        生成 GitHub Actions 工作流
bingo-light version                          打印版本
bingo-light help                             打印帮助
```

**全局标志：** `--json`（结构化 JSON 输出） | `--yes`（跳过所有确认提示）

## 集成指南

| 集成方式 | 适用场景 | 示例 |
|---------|---------|------|
| **MCP** (49 tools) | Claude Code / Cursor / Windsurf 等 | `bingo-light setup` 自动配 |
| **CLI `--json`** | 任何能跑 shell 的 AI | `bingo-light sync --json --yes` |
| **Skill** | Claude Code / Continue / Gemini 等 | `/bingo` 教 AI 用法 |

<details>
<summary><b>自定义 Python 代理</b></summary>

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

</details>

## 配置

配置存在 `.bingolight`（git-config 格式），自动排除在版本控制外。

```bash
bingo-light config set sync.auto-test true     # 同步后自动跑测试
bingo-light config set test.command "make test" # 测试命令
bingo-light config list                         # 查看所有配置
```

### 通知 Hook

在 `.bingo/hooks/` 放可执行脚本：

| Hook | 触发时机 |
|------|---------|
| `on-sync-success` | 同步成功后 |
| `on-conflict` | rebase 碰到冲突时 |
| `on-test-fail` | 同步后测试失败时 |

Hook 通过 stdin 接 JSON。示例见 [contrib/hooks/](contrib/hooks/)（Slack / Discord / Webhook）。

## 常见问题

<details>
<summary><b>为什么不直接 <code>git rebase</code>？</b></summary>

可以。bingo-light 包的是 rebase 周边那些烦事：追踪上游、维护补丁分支、开 rerere、预测冲突、输出结构化数据。偶尔 rebase 一次用不着它，但长期维护好几个补丁的话，省心省力。
</details>

<details>
<summary><b>能用在已有的 Fork 上吗？</b></summary>

能。进你的 Fork 目录，`bingo-light init <upstream-url>`，再 `bingo-light patch new <name>` 把现有改动转成补丁。标准 git 仓库就行。
</details>

<details>
<summary><b>只给 AI 用？</b></summary>

人和 AI 用的是同一套命令。`bingo-light sync` 谁跑都一样。`--json`、`--yes`、MCP 这些是给 AI 加的接口，不加就是正常的人类输出。
</details>

<details>
<summary><b>冲突记忆怎么回事？</b></summary>

`init` 时自动开了 git 的 `rerere`（reuse recorded resolution）。你解一次冲突，git 记住解法。下次碰到一样的冲突，直接套用，不再问你。bingo-light 还会检测到自动解决的冲突后自己继续 rebase，不会卡着等人。
</details>

<details>
<summary><b>同步搞砸了？</b></summary>

`bingo-light undo`。补丁分支秒回同步前的状态。底层用 reflog，再复杂的 rebase 也能回。
</details>

<details>
<summary><b>支持 GitHub/GitLab/Bitbucket 吗？</b></summary>

都支持。底层就是标准 git 操作（fetch、rebase、push），什么 git 远程都能用。`auto-sync` 能生成 GitHub Actions 流水线，但核心功能不绑平台。
</details>

<details>
<summary><b>和 <code>git format-patch</code> / quilt 有什么区别？</b></summary>

`format-patch` 能导出但不管活的补丁栈。quilt 管栈但脱离了 git。bingo-light 的补丁就是真正的 git commit，享受完整历史、冲突解决、rerere 记忆，同时支持 quilt 格式导出导入。
</details>

## 为什么不用...

<details>
<summary><b>...GitHub 的 "Sync fork" 按钮？</b></summary>
<br>

只能 fast-forward。你一有自己的改动，它要么拒绝要么生成 merge commit 把你的代码埋了。没有补丁栈，没有冲突记忆，没有 API。
</details>

<details>
<summary><b>...手动 <code>git rebase</code>？</b></summary>
<br>

可以，6 步：fetch、切 tracking 分支、pull、切 patches 分支、rebase、push。得记住分支名、手动开 rerere、搞砸了自己从 reflog 里捞。`bingo-light sync` 一条命令包了，还带撤销、冲突预测和结构化输出。
</details>

<details>
<summary><b>...StGit / quilt / TopGit？</b></summary>
<br>

StGit 管栈但没 AI 集成、没 MCP、没 JSON 输出、没冲突预测。quilt 脱离 git 体系，没 rerere 没历史。TopGit 基本废弃了。这些工具都不是为 AI 时代设计的。
</details>

## 与其他方案对比

| | **bingo-light** | GitHub Sync | git rebase | quilt | StGit |
|---|:---:|:---:|:---:|:---:|:---:|
| 命名补丁栈 | **有** | 无 | 无 | 有 | 有 |
| 一键同步 | **有** | 仅按钮 | 无（6 步） | 无 | 无 |
| 处理定制化改动 | **有** | **不行** | 手动 | 手动 | 手动 |
| 冲突记忆 (rerere) | **自动** | 无 | 需手动启用 | 无 | 无 |
| 冲突预测 | **有** | 无 | 无 | 无 | 无 |
| AI/MCP 集成 | **35 个工具** | 无 | 无 | 无 | 无 |
| JSON 输出 | **所有命令** | 无 | 无 | 无 | 无 |
| 非交互模式 | **原生支持** | 无 | 部分 | 部分 | 部分 |
| 撤销同步 | **一条命令** | 无 | git reflog | 手动 | 手动 |
| 安装方式 | 一条命令 | 内置 | 内置 | 包管理器 | 包管理器 |

## 项目生态

```
bingo-light          CLI 入口（Python 3，零依赖）
bingo_core/          核心库包（全部业务逻辑）
mcp-server.py        MCP 服务器（零依赖 Python 3，35 个工具）
contrib/agent.py     Advisor 代理（监控 + 分析 + 安全时自动同步）
contrib/tui.py       终端面板（curses TUI）
install.sh           安装器（--yes 支持 CI，--help 查看选项）
completions/         Shell 补全（bash/zsh/fish）
contrib/hooks/       通知 Hook 示例（Slack/Discord/Webhook）
tests/               测试套件（250 个测试，5 个文件）
docs/                文档
```

## 参与贡献

欢迎 PR。纯 Python，零依赖，不用构建。

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

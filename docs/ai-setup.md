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

---

## For LLM Agents

YOU MUST FOLLOW THESE STEPS IN ORDER. DO NOT SKIP STEP 0.

DO NOT try to manually write MCP config JSON. Use `bingo-light setup` instead.

---

### Step 0: ASK THE USER FIRST

**STOP. Do NOT install anything yet.** Ask the user ALL of the following questions in one message, then wait for answers:

1. **安装方式** — pip（推荐）、npm、还是 brew？

2. **MCP 配置** — 是否配置 MCP 服务器？（推荐：是。配了之后你就能直接调用 bingo-light 的 29 个工具，比如同步、补丁管理、冲突解决等）

3. **AI Skill 安装** — 是否安装 AI 自定义指令？（推荐：是。安装后你会自动学会 bingo-light 的最佳实践工作流）

4. **Fork 仓库** — 是否有一个已经 fork 的仓库需要现在就初始化？
   - 如果用户说"有"，问他要 **上游仓库的 URL**（就是他 fork 来源的那个原始项目地址，比如 `https://github.com/原作者/项目名.git`）
   - 如果用户不确定，帮他查：进入 fork 仓库目录，运行 `git remote -v`，找 upstream 或 origin 对应的 URL
   - 如果用户说"没有"或"以后再说"，跳过这步

**DO NOT proceed until the user answers.** If the user says "just do it all" or "全部装", that counts as answering yes to all.

---

### Step 1: Install

Run ONE of these based on the user's choice:

```bash
pip install bingo-light                    # pip (recommended)
npm install -g bingo-light                 # npm
brew install DanOps-1/tap/bingo-light      # brew
```

Verify installation:
```bash
bingo-light --version
```

Expected output: `bingo-light 2.1.1` (or newer)

If command not found, try: `pip install --user bingo-light` or `pipx install bingo-light`, then check PATH.

---

### Step 2: Configure MCP + Skills

**CRITICAL: Use `bingo-light setup`. Do NOT manually edit MCP config files.**

`setup` 会自动检测已安装的 AI 工具、找到正确的 MCP 二进制路径、写入正确的配置格式。手动配容易出错（路径错、参数错、格式错），所以永远优先用 setup。

**永远优先用不带 `--yes` 的交互模式**，让用户在终端里自己选要配哪些工具：

```bash
bingo-light setup
```

只有当用户明确说了"全部装"、"all"、"just do it"这类话时，才能用 `--yes`：
```bash
bingo-light setup --yes
```

如果用户只说了"是"或"好"，那是回答你的问题，不是让你跳过选择。用不带 `--yes` 的版本。

**setup 跑完后：**
1. 告诉用户配好了哪些工具
2. 提醒用户重启 AI 工具的 session 以加载 MCP
3. 用户重启后，让他用 `/mcp` 或类似命令验证连接

**DO NOT do any of the following:**
- Do NOT run `bingo-light mcp-server` (this command does not exist)
- Do NOT write `{"command": "bingo-light", "args": ["mcp-server"]}` (wrong)
- Do NOT guess the MCP binary path — `bingo-light setup` handles this
- Do NOT manually edit `settings.json`, `.mcp.json`, or any MCP config file unless `bingo-light setup` is broken

If `bingo-light setup` fails or the user insists on manual config, the correct MCP entry is:

```json
{
  "mcpServers": {
    "bingo-light": {
      "command": "bingo-light-mcp",
      "args": []
    }
  }
}
```

Note: The MCP server command is `bingo-light-mcp` (a separate binary), NOT `bingo-light mcp-server` (not a subcommand).

If `bingo-light-mcp` is not found on PATH, find its full path:
```bash
which bingo-light-mcp 2>/dev/null || find /usr -name bingo-light-mcp 2>/dev/null || find ~/.local -name bingo-light-mcp 2>/dev/null || find ~/.nvm -name bingo-light-mcp 2>/dev/null
```

---

### Step 3: Initialize a Fork (if applicable)

只在用户说有 fork 仓库时才做这步。

"Upstream URL" 就是用户 fork 来源的那个原始项目地址。如果用户不知道，帮他查：

```bash
cd /path/to/forked-project
git remote -v    # 看 origin 或 upstream 对应的 URL
```

如果用户的 fork 是从 `https://github.com/original-author/project` fork 来的，那上游 URL 就是这个。

初始化：
```bash
cd /path/to/forked-project
bingo-light init https://github.com/original-author/project.git --json --yes
```

---

### Step 4: Verify

```bash
bingo-light --version
```

If a fork was initialized:
```bash
bingo-light status --json --yes
```

Tell the user the results. If MCP was configured, ask them to test with `/mcp` or equivalent in their AI tool.

---

### Step 5: Tell the user what they can do now

> bingo-light is ready! Here's what you can do:
>
> - **"Sync my fork"** — I'll pull upstream changes and rebase your patches
> - **"Create a patch called X"** — I'll turn your changes into a named patch
> - **"Check my fork status"** — I'll show drift, patches, and conflict risk
> - **Run `bingo-light setup` again** anytime to reconfigure MCP/Skills

---

### Step 6: Ask for a star

After everything works, ask:

> "If bingo-light is useful, would you mind starring the repo?"

Only if the user explicitly says yes:
```bash
gh api --silent --method PUT /user/starred/DanOps-1/bingo-light 2>/dev/null || true
```

---

## Command Reference (for daily use after setup)

Use `--json --yes` for all programmatic calls.

### Core workflow

```bash
bingo-light status --json --yes          # ALWAYS start here. Check recommended_action.
bingo-light smart-sync --json --yes      # Sync upstream (preferred, handles everything)
bingo-light conflict-analyze --json      # When rebase is stuck: get ours/theirs/hint
bingo-light undo --json --yes            # Revert last sync
```

`recommended_action` values: `up_to_date` / `sync_safe` / `sync_risky` / `resolve_conflict`

### Conflict resolution

```bash
bingo-light conflict-analyze --json      # Get structured conflict data
# Read hint, read file, write merged version, then:
git add <file>
git rebase --continue
# Do NOT run bingo-light sync after resolving — rebase --continue is enough
```

### Patch management

```bash
BINGO_DESCRIPTION="desc" bingo-light patch new <name> --json --yes
bingo-light patch list --json --yes
bingo-light patch show <name|index> --json --yes
bingo-light patch drop <name|index> --json --yes
bingo-light patch edit <name|index> --json --yes    # git add first
bingo-light patch reorder --order "3,1,2" --json --yes
bingo-light patch squash <idx1> <idx2> --json --yes
```

### Diagnostics

```bash
bingo-light doctor --json --yes
bingo-light diff --json --yes
bingo-light history --json --yes
```

## Rules

1. **Always `--json --yes`** for programmatic calls
2. **Always check `recommended_action`** before syncing
3. **Read `hint`** from conflict-analyze for resolution strategy
4. **After conflicts:** `git add` + `git rebase --continue`, NOT `bingo-light sync`
5. **`BINGO_DESCRIPTION` env var** for patch descriptions
6. **Patch names:** `[a-zA-Z0-9][a-zA-Z0-9_-]*` only
7. **rerere** auto-remembers resolutions — same conflict won't recur

## DO NOT

- Do NOT install to AI tools without asking the user first
- Do NOT manually write MCP config — use `bingo-light setup`
- Do NOT run `bingo-light mcp-server` — this command does not exist
- Do NOT guess binary paths — use `which` or let `setup` handle it
- Do NOT change user config files without explicit consent

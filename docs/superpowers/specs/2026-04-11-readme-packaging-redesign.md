# bingo-light README & Packaging Redesign

**Date:** 2026-04-11
**Style:** Visual impact (starship/lazygit/bat tier)
**Narrative:** Pain-driven hook
**Voice:** Edgy, direct, second person

## 1. README Structure

### Header Block
- Large centered ASCII art logo
- One-liner tagline with attitude
- Language switcher: `English | 简体中文`
- Badge matrix in 2 rows:
  - Row 1 (trust): CI status, License MIT, Release version
  - Row 2 (identity): MCP 22 tools, Made with Bash, Zero deps, Stars counter

### Hook (immediately after badges)
Pain-driven emotional opening. Short punchy sentences. Second person.
```
Fork maintenance sucks.

You fork a project. You add features. Upstream pushes 200 commits.
Now your fork is broken, your patches are scattered across merge commits,
and `git rebase` is a blood sport.

You've been here. We've all been here.

**bingo-light makes it one command.**

Your patches live as a clean stack on top of upstream. Sync whenever you want.
Conflicts get remembered and auto-resolved. Works for humans. Built for AI agents.
```

### Demo
Animated GIF recorded with `asciinema rec` + converted to GIF via `agg`.
Content: `init → patch new → status → sync (with upstream changes) → done`.
~15 seconds. Centered, full-width.

### Remaining sections (in order)
1. Quick Start (3 commands, copy-paste ready)
2. Key Features (emoji-prefixed, split "For Humans" / "For AI Agents")
3. Installation (4 methods: installer, homebrew, source, manual)
4. How It Works (ASCII architecture diagram)
5. For AI Agents (MCP setup, JSON examples, integration patterns)
6. Command Reference (compact code block)
7. Comparison table (vs git rebase / quilt / stacked diffs)
8. FAQ (collapsible `<details>` blocks)
9. Contributing + License

## 2. Terminal GIF Recording

### Setup
```bash
asciinema rec demo.cast --cols 90 --rows 28
```

### Script (what to type)
1. `cd /tmp/my-fork && bingo-light init https://github.com/original/project.git`
2. `vim src/feature.py` → make change → `bingo-light patch new dark-mode`
3. `bingo-light status` (show colorful output with patches + behind count)
4. `bingo-light sync` (show rebase succeeding)
5. `bingo-light status` (show 0 behind, patches clean)

### Conversion
```bash
agg demo.cast docs/demo.gif --theme monokai --font-size 16
```
Replace current `docs/demo.svg` reference in README with GIF.

## 3. Chinese README (README.zh-CN.md)
Full mirror of English README structure. Same GIF, same sections.
Translated hook with equivalent emotional punch in Chinese.

## 4. GitHub Repo Packaging

### Release notes (v1.1.0)
Rewrite to be more concise and impactful. Lead with highlights, not changelogs.

### Repo metadata
- Description: keep current (already good)
- Topics: keep current 9 topics
- Homepage: keep current

### Docs cleanup
- Remove `docs/demo.svg` after replacing with GIF
- Add `.superpowers/` to `.gitignore`
- Ensure `docs/` only contains relevant files

## 5. Makefile
- Verify all targets work
- No new targets needed

## 6. Out of Scope
- No code changes to bingo-light, mcp-server.py, agent.py, tui.py
- No test changes
- No CI changes
- No shell completion changes

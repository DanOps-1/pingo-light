# README & Packaging Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform bingo-light's GitHub presence to viral-tier visual impact with pain-driven narrative, animated demo, and polished packaging.

**Architecture:** Record a real terminal demo via `termtosvg` (animated SVG, works in browsers, GitHub renders as static fallback). Rewrite both READMEs with edgy pain-driven hook, emoji feature grid, compact structure. Update all repo metadata.

**Tech Stack:** termtosvg (animated SVG recording), bash, git, gh CLI

---

### Task 1: Record Terminal Demo

**Files:**
- Create: `docs/demo.svg` (overwrite existing)

- [ ] **Step 1: Create the demo script**

```bash
cat > /tmp/bl-demo-script.sh << 'DEMO'
#!/usr/bin/env bash
set -e

# Setup (invisible to viewer — pre-record)
cd /tmp
rm -rf demo-upstream demo-fork 2>/dev/null
mkdir demo-upstream && cd demo-upstream
git init -q && git config user.name "upstream" && git config user.email "u@u"
echo 'from flask import Flask' > app.py
echo 'app = Flask(__name__)' >> app.py
echo '' >> app.py
echo '@app.route("/")' >> app.py
echo 'def index():' >> app.py
echo '    return "Hello World"' >> app.py
echo 'DEBUG = False' > config.py
git add -A && git commit -qm "initial: flask app"
cd /tmp && git clone -q demo-upstream demo-fork
cd demo-fork && git config user.name "you" && git config user.email "you@dev"

clear
echo ""

# === VISIBLE DEMO STARTS ===

# 1. Init
echo '$ bingo-light init /tmp/demo-upstream'
sleep 0.5
bingo-light init /tmp/demo-upstream master --yes 2>&1 | grep -E "OK|Upstream|Tracking|Patches|Next"
sleep 1.5

# 2. Make changes + create patch
echo ""
echo '$ echo "DEBUG = True" > config.py'
echo 'DEBUG = True' > config.py
echo '$ echo "import redis" >> app.py'
echo 'import redis' >> app.py
git add -A
sleep 0.5
echo '$ bingo-light patch new debug-mode'
BINGO_DESCRIPTION="enable debug + redis cache" bingo-light patch new debug-mode --yes 2>&1
sleep 1.5

# 3. Status
echo ""
echo '$ bingo-light status'
sleep 0.3

# Simulate upstream advancing
cd /tmp/demo-upstream
echo '' >> app.py
echo '@app.route("/health")' >> app.py
echo 'def health():' >> app.py
echo '    return "ok"' >> app.py
git add -A && git commit -qm "feat: add health endpoint" -q
echo 'VERSION = "2.0"' >> config.py
git add -A && git commit -qm "bump: version 2.0" -q
echo 'import logging' >> app.py
git add -A && git commit -qm "feat: add logging" -q
cd /tmp/demo-fork

bingo-light status 2>&1
sleep 2

# 4. Sync
echo ""
echo '$ bingo-light sync'
sleep 0.3
bingo-light sync --force 2>&1
sleep 2

echo ""
echo '$ bingo-light status'
bingo-light status 2>&1 | head -8
sleep 2
DEMO
chmod +x /tmp/bl-demo-script.sh
```

- [ ] **Step 2: Record with termtosvg**

```bash
termtosvg /home/kali/bingo-light/docs/demo.svg \
  -c "bash /tmp/bl-demo-script.sh" \
  -g 90x30 \
  -D 5000 \
  -t window_frame_js
```

If `termtosvg` recording has issues (too fast/slow), adjust the script's `sleep` values and re-record.

- [ ] **Step 3: Verify the SVG**

```bash
ls -lh /home/kali/bingo-light/docs/demo.svg
file /home/kali/bingo-light/docs/demo.svg
# Should be a valid SVG file, 50KB-500KB range
```

- [ ] **Step 4: Commit**

```bash
git add docs/demo.svg
git commit -m "demo: record real terminal session via termtosvg"
```

---

### Task 2: Rewrite English README

**Files:**
- Modify: `README.md` (full rewrite)

- [ ] **Step 1: Write the new README**

Structure (in exact order):
1. Centered header: ASCII logo + tagline + language switcher + 2-row badges
2. Pain-driven hook (the "fork maintenance sucks" paragraph)
3. Animated demo SVG (centered, full width)
4. Quick Start (3 commands)
5. Key Features (emoji grid, split Human/AI)
6. Installation (4 methods)
7. How It Works (architecture diagram)
8. For AI Agents (MCP + JSON section, compact)
9. Command Reference (single code block)
10. Comparison table
11. FAQ (7 collapsible blocks)
12. Project ecosystem
13. Contributing + License

Key writing rules:
- Voice: edgy, direct, "you". Short sentences.
- Features use emoji prefixes, NOT tables
- Badge row 1: CI, License, Release. Row 2: MCP tools, Bash, Zero deps, Stars
- Hook paragraph is THE most important piece — make it punchy
- Demo GIF reference: `<img src="docs/demo.svg" ...>`
- No Chinese content in English README (separate file)

- [ ] **Step 2: Verify markdown renders**

```bash
wc -l README.md
# Spot-check: no raw HTML errors, no broken links
head -30 README.md
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README with pain-driven narrative + visual impact"
```

---

### Task 3: Rewrite Chinese README

**Files:**
- Modify: `README.zh-CN.md` (full rewrite, mirror English structure)

- [ ] **Step 1: Write the Chinese README**

Same structure as English. Same demo SVG. Translate the hook with equivalent emotional punch:
```
Fork 维护烂透了。

你 fork 了一个项目。你加了功能。上游推了 200 个 commit。
现在你的 fork 崩了，补丁散落在各种 merge commit 里，
git rebase 变成一场血腥屠杀。

你经历过。我们都经历过。

**bingo-light 让它变成一条命令。**
```

- [ ] **Step 2: Commit**

```bash
git add README.zh-CN.md
git commit -m "docs: rewrite Chinese README with matching narrative"
```

---

### Task 4: Polish GitHub Repo Metadata

**Files:**
- No file changes, uses `gh` CLI

- [ ] **Step 1: Update release notes for v1.1.0**

```bash
gh release edit v1.1.0 --notes "$(cat <<'EOF'
... concise, impactful release notes ...
EOF
)"
```

Lead with highlights, not changelogs. "What's exciting" not "what changed".

- [ ] **Step 2: Upload updated assets**

```bash
gh release upload v1.1.0 bingo-light --clobber
gh release upload v1.1.0 mcp-server.py --clobber
gh release upload v1.1.0 install.sh --clobber
```

- [ ] **Step 3: Commit and push everything**

```bash
git push origin main
git tag -f v1.1.0 -m "v1.1.0"
git push -f origin v1.1.0
```

- [ ] **Step 4: Verify CI green**

```bash
gh run list --limit 1
# Wait for success
```

---

### Task 5: Cleanup

**Files:**
- Modify: `.gitignore` (already has `.superpowers/`)

- [ ] **Step 1: Clean up temp files**

```bash
rm -f /tmp/bl-demo-script.sh
```

- [ ] **Step 2: Final verification**

Open https://github.com/DanOps-1/bingo-light and verify:
- README renders correctly with demo
- Badges all work
- Chinese README accessible via language switcher
- Release page looks clean

#!/usr/bin/env bash
# pingo-light test suite
# Usage: ./tests/test.sh [path-to-pingo-light]
set -uo pipefail

PINGO="${1:-$(cd "$(dirname "$0")/.." && pwd)/pingo-light}"
TMPDIR_BASE=$(mktemp -d)
PASS=0 FAIL=0 SKIP=0
OUT=""

# ─── Helpers ──────────────────────────────────────────────────────────────────

RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[0;33m' CYAN='\033[0;36m'
BOLD='\033[1m' DIM='\033[2m' RESET='\033[0m'

pass() { ((PASS++)); echo -e "  ${GREEN}PASS${RESET} $1"; }
fail() { ((FAIL++)); echo -e "  ${RED}FAIL${RESET} $1: $2"; }
skip() { ((SKIP++)); echo -e "  ${YELLOW}SKIP${RESET} $1"; }
section() { echo -e "\n${BOLD}$1${RESET}"; }

# Safe runner: captures stdout+stderr, avoids SIGPIPE issues
run()  { OUT=$("$PINGO" "$@" 2>&1) || true; }
has()  { echo "$OUT" | grep -qi "$1"; }
hasE() { echo "$OUT" | grep -qE "$1"; }

assert() {
    local desc="$1" pattern="$2"
    shift 2
    run "$@"
    if has "$pattern"; then pass "$desc"; else fail "$desc" "pattern '$pattern' not found"; fi
}

cleanup() { rm -rf "$TMPDIR_BASE"; }
trap cleanup EXIT

setup_repos() {
    local name="${1:-test}"
    local upstream="$TMPDIR_BASE/${name}-upstream"
    local fork="$TMPDIR_BASE/${name}-fork"

    mkdir -p "$upstream"
    cd "$upstream" && git init --initial-branch=main -q
    echo "line1" > app.py
    echo "config=1" > config.py
    echo "# README" > README.md
    git add -A && git commit -q -m "Initial commit"

    echo "line2" >> app.py
    git add -A && git commit -q -m "Second commit"

    git clone -q "$upstream" "$fork"
    cd "$fork"
    echo "$upstream|$fork"
}

# ─── Tests ────────────────────────────────────────────────────────────────────

section "1. Basic CLI"

assert "--help shows usage"         "pingo-light"    --help
assert "--version shows version"    "pingo-light"    --version
assert "unknown command shows error" "unknown"        nonexistent

# ─── init ─────────────────────────────────────────────────────────────────────

section "2. Init"

repos=$(setup_repos init)
upstream="${repos%%|*}" fork="${repos##*|}"
cd "$fork"

OUT=$("$PINGO" init "$upstream" main < /dev/null 2>&1) || true
if has "initialized"; then pass "init succeeds"; else fail "init" "did not report success"; fi

if [[ -f .pingolight ]]; then pass "config file created"; else fail "config file" "not found"; fi
if git rev-parse --verify upstream-tracking &>/dev/null; then pass "tracking branch created"; else fail "tracking branch" "not found"; fi
if git rev-parse --verify pingo-patches &>/dev/null; then pass "patches branch created"; else fail "patches branch" "not found"; fi
if [[ "$(git config rerere.enabled)" == "true" ]]; then pass "rerere enabled"; else fail "rerere" "not enabled"; fi

repos=$(setup_repos init-auto)
upstream="${repos%%|*}" fork="${repos##*|}"
cd "$fork"
OUT=$("$PINGO" init "$upstream" < /dev/null 2>&1) || true
if has "initialized"; then pass "init auto-detects branch"; else fail "init auto-detect" "failed"; fi

# ─── patch new ────────────────────────────────────────────────────────────────

section "3. Patch New"

repos=$(setup_repos patch)
upstream="${repos%%|*}" fork="${repos##*|}"
cd "$fork"
"$PINGO" init "$upstream" main < /dev/null &>/dev/null || true

echo "custom_feature = True" >> app.py
OUT=$(echo "added feature" | "$PINGO" patch new test-feature 2>&1) || true
if has "created"; then pass "patch new creates patch"; else fail "patch new" "did not report creation"; fi

if git log -1 --format="%s" | grep -q '^\[pl\] test-feature:'; then
    pass "commit message has [pl] prefix"
else
    fail "commit format" "$(git log -1 --format='%s')"
fi

echo "another = True" >> config.py
OUT=$(echo "config change" | "$PINGO" patch new config-tweak 2>&1) || true
if has "created"; then pass "second patch created"; else fail "second patch" "creation failed"; fi

echo "dup" >> README.md
OUT=$(echo "dup" | "$PINGO" patch new test-feature 2>&1) || true
if has "already exists"; then pass "rejects duplicate patch name"; else fail "duplicate name" "not rejected"; fi
git checkout -- README.md 2>/dev/null || true

run patch new "bad name!"
if has "invalid"; then pass "rejects invalid patch name"; else fail "invalid name" "not rejected"; fi

run patch new no-changes
if has "no changes"; then pass "rejects patch with no changes"; else fail "no changes" "not rejected"; fi

# ─── patch list ───────────────────────────────────────────────────────────────

section "4. Patch List"

run patch list
if has "test-feature"; then pass "patch list shows patches"; else fail "patch list" "missing patch"; fi
if has "config-tweak"; then pass "patch list shows second patch"; else fail "patch list" "missing second patch"; fi
if has "Total: 2"; then pass "patch list shows correct count"; else fail "patch count" "wrong count"; fi

run patch list -v
if hasE '(app\.py|config\.py)'; then pass "patch list -v shows files"; else fail "patch list -v" "no file details"; fi

# ─── patch show ───────────────────────────────────────────────────────────────

section "5. Patch Show"

run patch show 1
if has "custom_feature"; then pass "patch show by index"; else fail "patch show index" "wrong content"; fi

run patch show config-tweak
if has "another"; then pass "patch show by name"; else fail "patch show name" "wrong content"; fi

# ─── patch export/import ──────────────────────────────────────────────────────

section "6. Patch Export/Import"

export_dir="$TMPDIR_BASE/exported-patches"
run patch export "$export_dir"
if has "Exported 2"; then pass "patch export"; else fail "patch export" "unexpected output"; fi

if [[ -f "$export_dir/series" ]]; then pass "series file created"; else fail "series file" "not found"; fi

patch_count=$(ls "$export_dir"/*.patch 2>/dev/null | wc -l)
if [[ "$patch_count" -eq 2 ]]; then pass "correct number of .patch files"; else fail "patch files" "expected 2, got $patch_count"; fi

repos2=$(setup_repos import)
upstream2="${repos2%%|*}" fork2="${repos2##*|}"
cd "$fork2"
"$PINGO" init "$upstream2" main < /dev/null &>/dev/null || true

run patch import "$export_dir"
if has "complete"; then pass "patch import from directory"; else fail "patch import" "failed"; fi

run patch list
import_count=$(echo "$OUT" | grep -oP 'Total: \K[0-9]+' || echo 0)
if [[ "$import_count" -eq 2 ]]; then pass "imported correct number of patches"; else fail "import count" "expected 2, got $import_count"; fi

# ─── patch drop ───────────────────────────────────────────────────────────────

section "7. Patch Drop"

cd "$fork"
OUT=$(echo "y" | "$PINGO" patch drop 2 2>&1) || true
if has "dropped"; then pass "patch drop by index"; else fail "patch drop" "failed"; fi

run patch list
remaining=$(echo "$OUT" | grep -oP 'Total: \K[0-9]+' || echo 0)
if [[ "$remaining" -eq 1 ]]; then pass "correct count after drop"; else fail "count after drop" "expected 1, got $remaining"; fi

# ─── sync ─────────────────────────────────────────────────────────────────────

section "8. Sync"

# Upstream changes DIFFERENT files than our patch (app.py) to avoid conflict
cd "$upstream"
echo "# Updated" >> README.md
git add -A && git commit -q -m "Upstream: update readme"
echo "new_util = True" > util.py
git add -A && git commit -q -m "Upstream: add util"

cd "$fork"

run sync --dry-run
if has "dry run"; then pass "sync --dry-run works"; else fail "sync dry-run" "no dry-run output"; fi

if [[ "$(git rev-parse HEAD)" == "$(git rev-parse pingo-patches)" ]]; then
    pass "dry-run didn't modify branches"
else
    fail "dry-run safety" "branches were modified"
fi

run sync --force
if has "sync complete"; then pass "sync succeeds"; else fail "sync" "did not complete"; fi

run patch list
if has "test-feature"; then pass "patches preserved after sync"; else fail "patches after sync" "patches lost"; fi

if [[ -f util.py ]]; then pass "upstream changes integrated"; else fail "upstream integration" "changes missing"; fi
if grep -q "custom_feature" app.py; then pass "patch content preserved after sync"; else fail "patch content" "our changes lost"; fi

run sync --force
if has "up to date"; then pass "sync reports up-to-date"; else fail "up-to-date check" "wrong report"; fi

# ─── status ───────────────────────────────────────────────────────────────────

section "9. Status"

run status
if has "upstream"; then pass "status shows upstream info"; else fail "status" "no upstream info"; fi

run status
if has "patches"; then pass "status shows patch info"; else fail "status patches" "no patch info"; fi

cd "$upstream"
echo "conflict_line" >> app.py
git add -A && git commit -q -m "Upstream: potential conflict"

cd "$fork"
run status
if has "behind\|conflict\|overlap\|risk"; then
    pass "status detects drift or conflict risk"
else
    fail "status drift" "not detected"
fi

# ─── doctor ───────────────────────────────────────────────────────────────────

section "10. Doctor"

run doctor
if has "rerere"; then pass "doctor checks rerere"; else fail "doctor rerere" "not checked"; fi
if has "upstream remote"; then pass "doctor checks upstream"; else fail "doctor upstream" "not checked"; fi
if has "tracking branch"; then pass "doctor checks tracking branch"; else fail "doctor tracking" "not checked"; fi

# ─── diff ─────────────────────────────────────────────────────────────────────

section "11. Diff"

run diff
if has "custom_feature"; then pass "diff shows patch content"; else fail "diff" "patch content missing"; fi

# ─── undo ─────────────────────────────────────────────────────────────────────

section "12. Undo"

cd "$fork"
"$PINGO" sync --force &>/dev/null || true

saved_head=$(git rev-parse pingo-patches)

cd "$upstream"
echo "# undo test" >> README.md
git add -A && git commit -q -m "Upstream: for undo test"
cd "$fork"
"$PINGO" sync --force &>/dev/null || true

new_head=$(git rev-parse pingo-patches)
if [[ "$saved_head" != "$new_head" ]]; then
    OUT=$(echo "y" | "$PINGO" undo 2>&1) || true
    if has "undone\|restored"; then pass "undo restores previous state"; else fail "undo" "did not restore"; fi
else
    skip "undo (no state change to undo)"
fi

# ─── edge cases ───────────────────────────────────────────────────────────────

section "13. Edge Cases"

cd "$TMPDIR_BASE"
mkdir -p not-a-repo && cd not-a-repo
run status
if has "not.*git\|not initialized"; then pass "error on non-git directory"; else fail "non-git dir" "no error"; fi

repos=$(setup_repos edge)
fork="${repos##*|}"
cd "$fork"
run status
if has "not initialized"; then pass "error on uninitialized repo"; else fail "uninitialized" "no error"; fi

"$PINGO" init "${repos%%|*}" main < /dev/null &>/dev/null || true
echo "dirty" >> app.py
run sync --force
if has "dirty\|commit\|stash"; then pass "rejects sync on dirty tree"; else fail "dirty tree" "not rejected"; fi
git checkout -- app.py 2>/dev/null || true

# ─── auto-sync ────────────────────────────────────────────────────────────────

section "14. Auto-Sync"

OUT=$(echo "1" | "$PINGO" auto-sync 2>&1) || true
if has "workflow generated"; then pass "auto-sync generates workflow"; else fail "auto-sync" "no workflow generated"; fi

if [[ -f .github/workflows/pingo-light-sync.yml ]]; then pass "workflow file exists"; else fail "workflow file" "not found"; fi
if grep -q "pingo-light" .github/workflows/pingo-light-sync.yml; then pass "workflow references pingo-light"; else fail "workflow content" "missing reference"; fi

# ─── MCP server ───────────────────────────────────────────────────────────────

section "15. MCP Server"

MCP_SERVER="$(dirname "$PINGO")/mcp-server.py"
if [[ -f "$MCP_SERVER" ]]; then
    tool_count=$(python3 -c "
import json, subprocess
def mcp_msg(obj):
    body = json.dumps(obj)
    return f'Content-Length: {len(body)}\r\n\r\n{body}'
msgs = (
    mcp_msg({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{}}})
    + mcp_msg({'jsonrpc':'2.0','method':'notifications/initialized'})
    + mcp_msg({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
)
proc = subprocess.run(['python3','$MCP_SERVER'], input=msgs, capture_output=True, text=True, timeout=5)
parts = proc.stdout.split('Content-Length:')
for part in reversed(parts):
    try:
        idx = part.index('{')
        parsed = json.loads(part[idx:])
        if 'result' in parsed and 'tools' in parsed['result']:
            print(len(parsed['result']['tools']))
            break
    except: pass
" 2>/dev/null || echo 0)

    if [[ "$tool_count" -eq 15 ]]; then pass "MCP server registers 15 tools"; else fail "MCP tools" "expected 15, got $tool_count"; fi
else
    skip "MCP server (mcp-server.py not found)"
fi

# ─── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
total=$((PASS + FAIL + SKIP))
echo -e "  ${GREEN}$PASS passed${RESET}  ${RED}$FAIL failed${RESET}  ${YELLOW}$SKIP skipped${RESET}  ${DIM}($total total)${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

exit "$FAIL"

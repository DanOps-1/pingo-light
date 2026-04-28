#!/usr/bin/env bash
# bingo-light — run all test suites and report coverage
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BL="${1:-$(cd "$SCRIPT_DIR/.." && pwd)/bingo-light}"
TOTAL_PASS=0
TOTAL_FAIL=0
TOTAL_SKIP=0
SUITE_FAILS=0

BOLD=$'\033[1m'
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
CYAN=$'\033[0;36m'
DIM=$'\033[2m'
RESET=$'\033[0m'

run_suite() {
    local name="$1" cmd="$2"
    echo ""
    echo "${BOLD}━━━ $name ━━━${RESET}"
    local output
    output=$(eval "$cmd" 2>&1) || true
    echo "$output"

    # Extract counts from last summary line
    local p f s
    p=$(echo "$output" | grep -oP '\d+ passed' | grep -oP '\d+' | tail -1)
    f=$(echo "$output" | grep -oP '\d+ failed' | grep -oP '\d+' | tail -1)
    s=$(echo "$output" | grep -oP '\d+ skipped' | grep -oP '\d+' | tail -1)
    TOTAL_PASS=$((TOTAL_PASS + ${p:-0}))
    TOTAL_FAIL=$((TOTAL_FAIL + ${f:-0}))
    TOTAL_SKIP=$((TOTAL_SKIP + ${s:-0}))
    [[ "${f:-0}" -gt 0 ]] && SUITE_FAILS=$((SUITE_FAILS + 1))
}

# ─── Run all suites ──────────────────────────────────────────────────────────

run_suite "Core Tests"        "$SCRIPT_DIR/test.sh $BL"
run_suite "JSON Fuzz Tests"   "$SCRIPT_DIR/test-json.sh $BL"
run_suite "Edge Case Tests"   "$SCRIPT_DIR/test-edge.sh $BL"
run_suite "MCP Protocol Tests" "python3 $SCRIPT_DIR/test-mcp.py"
run_suite "MCP Fuzz Tests"    "python3 $SCRIPT_DIR/fuzz_mcp.py"
run_suite "Dep Unit Tests"    "python3 $SCRIPT_DIR/test_dep.py"

# ─── Command coverage report ────────────────────────────────────────────────

echo ""
echo "${BOLD}━━━ Command Coverage Report ━━━${RESET}"

# All commands the CLI supports (from main dispatch)
ALL_COMMANDS="init patch-new patch-list patch-show patch-edit patch-drop patch-export patch-import patch-reorder patch-squash patch-meta sync status doctor auto-sync log undo diff conflict-analyze config-get config-set config-list history test workspace-init workspace-add workspace-status workspace-sync workspace-list version help"

# Check which commands appear in test files
TESTED=0
UNTESTED=0
UNTESTED_LIST=""
for cmd in $ALL_COMMANDS; do
    # Normalize: patch-new → "patch new" or "patch.*new"
    search=$(echo "$cmd" | sed 's/-/[- ]*/g')
    if grep -rqlE "$search" "$SCRIPT_DIR"/test*.sh "$SCRIPT_DIR"/test*.py 2>/dev/null; then
        TESTED=$((TESTED + 1))
    else
        UNTESTED=$((UNTESTED + 1))
        UNTESTED_LIST+="  $cmd\n"
    fi
done

TOTAL_CMDS=$((TESTED + UNTESTED))
echo "  ${GREEN}$TESTED${RESET}/$TOTAL_CMDS commands referenced in tests"
if [[ -n "$UNTESTED_LIST" ]]; then
    echo "  ${YELLOW}Untested:${RESET}"
    printf "$UNTESTED_LIST"
fi

# ─── Final summary ──────────────────────────────────────────────────────────

echo ""
echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo "  ${GREEN}$TOTAL_PASS passed${RESET}  ${RED}$TOTAL_FAIL failed${RESET}  ${YELLOW}$TOTAL_SKIP skipped${RESET}  ${DIM}(6 suites)${RESET}"
echo "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

exit $SUITE_FAILS

#!/usr/bin/env bash
# bingo-light — interactive setup wizard
set -euo pipefail

GITHUB_RAW="https://raw.githubusercontent.com/DanOps-1/bingo-light/main"

# Detect if running from a local clone or piped from curl
if [[ -f "$(dirname "$0")/bingo-light" ]] 2>/dev/null; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
else
    # Running via curl pipe — download to temp dir
    SCRIPT_DIR="$(mktemp -d)"
    _CLEANUP_DIR="$SCRIPT_DIR"
    curl -fsSL "$GITHUB_RAW/bingo-light" -o "$SCRIPT_DIR/bingo-light"
    curl -fsSL "$GITHUB_RAW/mcp-server.py" -o "$SCRIPT_DIR/mcp-server.py"
    curl -fsSL "$GITHUB_RAW/.claude/commands/bingo.md" -o "$SCRIPT_DIR/bingo.md"
    mkdir -p "$SCRIPT_DIR/completions"
    curl -fsSL "$GITHUB_RAW/completions/bingo-light.bash" -o "$SCRIPT_DIR/completions/bingo-light.bash"
    curl -fsSL "$GITHUB_RAW/completions/bingo-light.zsh" -o "$SCRIPT_DIR/completions/bingo-light.zsh"
    curl -fsSL "$GITHUB_RAW/completions/bingo-light.fish" -o "$SCRIPT_DIR/completions/bingo-light.fish"
fi

# ─── Terminal Control ─────────────────────────────────────────────────────────

ESC=$'\033'
HIDE_CURSOR="${ESC}[?25l"
SHOW_CURSOR="${ESC}[?25h"
CLEAR_LINE="${ESC}[2K"
MOVE_UP="${ESC}[1A"
SAVE_POS="${ESC}[s"
RESTORE_POS="${ESC}[u"

# Colors (soft palette)
C_BG="${ESC}[48;5;235m"
C_FG="${ESC}[38;5;252m"
C_ACCENT="${ESC}[38;5;75m"    # soft blue
C_SUCCESS="${ESC}[38;5;114m"  # soft green
C_WARN="${ESC}[38;5;221m"     # soft yellow
C_DIM="${ESC}[38;5;242m"
C_BOLD="${ESC}[1m"
C_RESET="${ESC}[0m"
C_WHITE="${ESC}[38;5;255m"

trap 'printf "%s" "$SHOW_CURSOR"; [[ -n "${_CLEANUP_DIR:-}" ]] && rm -rf "$_CLEANUP_DIR"' EXIT
printf "%s" "$HIDE_CURSOR"

# ─── Helpers ──────────────────────────────────────────────────────────────────

clear_screen() { printf "${ESC}[2J${ESC}[H"; }

# Print centered text
center() {
    local text="$1" color="${2:-$C_FG}"
    local cols
    cols=$(tput cols 2>/dev/null || echo 80)
    local stripped
    stripped=$(printf '%s' "$text" | sed $'s/\033\\[[0-9;]*m//g')
    local pad=$(( (cols - ${#stripped}) / 2 ))
    [[ "$pad" -lt 0 ]] && pad=0
    printf "%${pad}s${color}%s${C_RESET}\n" "" "$text"
}

# Animated typing effect
type_text() {
    local text="$1" color="${2:-$C_FG}" delay="${3:-0.02}"
    printf "%s" "$color"
    for ((i=0; i<${#text}; i++)); do
        printf "%s" "${text:$i:1}"
        sleep "$delay"
    done
    printf "%s\n" "$C_RESET"
}

# Spinner animation
spin() {
    local pid=$1 msg="${2:-Working...}"
    local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r  ${C_ACCENT}${frames[$i]}${C_RESET} ${C_DIM}%s${C_RESET}" "$msg"
        i=$(( (i + 1) % ${#frames[@]} ))
        sleep 0.08
    done
    wait "$pid" 2>/dev/null
    local code=$?
    printf "\r${CLEAR_LINE}"
    return $code
}

# Step indicator: ● ● ○ ○
progress_dots() {
    local current=$1 total=$2
    local dots=""
    for ((i=1; i<=total; i++)); do
        if [[ $i -le $current ]]; then
            dots+="${C_ACCENT}●${C_RESET} "
        else
            dots+="${C_DIM}○${C_RESET} "
        fi
    done
    center "$dots"
}

# Ask with styled prompt
ask_styled() {
    local prompt="$1" default="${2:-y}"
    printf "\n  ${C_WHITE}%s${C_RESET} " "$prompt"
    printf "%s" "$SHOW_CURSOR"
    read -r answer
    printf "%s" "$HIDE_CURSOR"
    answer="${answer:-$default}"
    [[ "$answer" =~ ^[Yy] ]]
}

# Result line
ok()   { printf "  ${C_SUCCESS}✓${C_RESET} %s\n" "$1"; }
skip() { printf "  ${C_DIM}⊘ %s${C_RESET}\n" "$1"; }
fail() { printf "  ${C_WARN}✗${C_RESET} %s\n" "$1"; }

# Box drawing
box_top()    { printf "  ${C_DIM}╭─────────────────────────────────────────────────╮${C_RESET}\n"; }
box_bottom() { printf "  ${C_DIM}╰─────────────────────────────────────────────────╯${C_RESET}\n"; }
box_line()   { printf "  ${C_DIM}│${C_RESET} %-47s ${C_DIM}│${C_RESET}\n" "$1"; }
box_empty()  { printf "  ${C_DIM}│${C_RESET}                                                 ${C_DIM}│${C_RESET}\n"; }

# ─── Splash Screen ────────────────────────────────────────────────────────────

splash() {
    clear_screen
    echo ""
    echo ""

    local logo=(
        "  _     _                         _ _       _     _   "
        " | |   (_)_ __   __ _  ___       | (_) __ _| |__ | |_ "
        " | |__ | | '_ \\ / _\` |/ _ \\ ____| | |/ _\` | '_ \\| __|"
        " | '_ \\| | | | | (_| | (_) |____| | | (_| | | | | |_ "
        " |_.__/|_|_| |_|\\__, |\\___/     |_|_|\\__, |_| |_|\\__|"
        "                |___/                 |___/            "
    )

    for line in "${logo[@]}"; do
        center "$line" "$C_ACCENT"
        sleep 0.05
    done

    echo ""
    center "AI-native fork maintenance" "$C_DIM"
    echo ""
    sleep 0.3

    center "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" "$C_DIM"
    echo ""
    sleep 0.2
}

# ─── Step Screens ─────────────────────────────────────────────────────────────

step_cli() {
    echo ""
    progress_dots 1 4
    echo ""
    center "Step 1 of 4" "$C_DIM"
    center "Install CLI" "${C_BOLD}${C_WHITE}"
    echo ""

    box_top
    box_line "Install bingo-light to /usr/local/bin"
    box_line "This lets you run 'bingo-light' from anywhere."
    box_empty
    box_line "  ${C_DIM}$ bingo-light init <upstream-url>${C_RESET}"
    box_line "  ${C_DIM}$ bingo-light sync${C_RESET}"
    box_bottom
    echo ""

    (
        if [[ ! -w "/usr/local/bin" ]]; then
            sudo install -m 755 "$SCRIPT_DIR/bingo-light" /usr/local/bin/bingo-light
        else
            install -m 755 "$SCRIPT_DIR/bingo-light" /usr/local/bin/bingo-light
        fi
    ) &
    spin $! "Installing CLI..."
    ok "bingo-light installed"
    sleep 0.5
}

step_completions() {
    clear_screen
    echo ""
    progress_dots 2 4
    echo ""
    center "Step 2 of 4" "$C_DIM"
    center "Shell Completions" "${C_BOLD}${C_WHITE}"
    echo ""

    local shell_name
    shell_name=$(basename "${SHELL:-/bin/bash}")

    box_top
    box_line "Detected shell: ${C_ACCENT}$shell_name${C_RESET}"
    box_line "Tab completion for all commands and flags."
    box_bottom
    echo ""

    case "$shell_name" in
        bash)
            local dir="${BASH_COMPLETION_USER_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/bash-completion/completions}"
            mkdir -p "$dir"
            cp "$SCRIPT_DIR/completions/bingo-light.bash" "$dir/bingo-light"
            ok "Bash completions → $dir"
            ;;
        zsh)
            local dir="$HOME/.zfunc"
            mkdir -p "$dir"
            cp "$SCRIPT_DIR/completions/bingo-light.zsh" "$dir/_bingo-light"
            if ! grep -q '.zfunc' ~/.zshrc 2>/dev/null; then
                echo 'fpath=(~/.zfunc $fpath)' >> ~/.zshrc
                echo 'autoload -Uz compinit && compinit' >> ~/.zshrc
            fi
            ok "Zsh completions → $dir"
            ;;
        fish)
            local dir="$HOME/.config/fish/completions"
            mkdir -p "$dir"
            cp "$SCRIPT_DIR/completions/bingo-light.fish" "$dir/bingo-light.fish"
            ok "Fish completions → $dir"
            ;;
        *)
            skip "Unknown shell, skipped"
            ;;
    esac
    sleep 0.5
}

step_mcp() {
    clear_screen
    echo ""
    progress_dots 3 4
    echo ""
    center "Step 3 of 4" "$C_DIM"
    center "MCP Server" "${C_BOLD}${C_WHITE}"
    echo ""

    box_top
    box_line "Connect bingo-light to AI assistants."
    box_line "22 tools for Claude Code, Cursor, etc."
    box_empty
    box_line "  ${C_DIM}AI calls bingo_sync(cwd=\"/repo\")${C_RESET}"
    box_line "  ${C_DIM}→ patches rebased automatically${C_RESET}"
    box_bottom
    echo ""

    local configured=false

    # Claude Code
    if [[ -d "$HOME/.claude" ]] || command -v claude &>/dev/null; then
        if ask_styled "Configure for Claude Code? [Y/n]"; then
            local cfg="$HOME/.claude/settings.json"
            mkdir -p "$HOME/.claude"
            printf '%s\n%s' "$cfg" "$SCRIPT_DIR/mcp-server.py" | python3 -c "
import json, os, sys
lines = sys.stdin.read().strip().split('\n')
path, mcp_path = lines[0], lines[1]
data = {}
if os.path.exists(path):
    with open(path) as f: data = json.load(f)
data.setdefault('mcpServers', {})['bingo-light'] = {'command': 'python3', 'args': [mcp_path]}
with open(path, 'w') as f: json.dump(data, f, indent=2)
" 2>/dev/null && ok "Claude Code configured" || fail "Could not write settings"
            configured=true
        else
            skip "Claude Code skipped"
        fi
    fi

    # Claude Desktop
    local desktop_cfg="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    if [[ -d "$HOME/Library/Application Support/Claude" ]]; then
        echo ""
        if ask_styled "Configure for Claude Desktop? [Y/n]"; then
            printf '%s\n%s' "$desktop_cfg" "$SCRIPT_DIR/mcp-server.py" | python3 -c "
import json, os, sys
lines = sys.stdin.read().strip().split('\n')
path, mcp_path = lines[0], lines[1]
data = {}
if os.path.exists(path):
    with open(path) as f: data = json.load(f)
data.setdefault('mcpServers', {})['bingo-light'] = {'command': 'python3', 'args': [mcp_path]}
with open(path, 'w') as f: json.dump(data, f, indent=2)
" 2>/dev/null && ok "Claude Desktop configured" || fail "Could not write config"
            configured=true
        else
            skip "Claude Desktop skipped"
        fi
    fi

    if [[ "$configured" == false ]]; then
        echo ""
        printf "  ${C_DIM}For other MCP clients, add to config:${C_RESET}\n"
        echo ""
        printf "  ${C_DIM}\"bingo-light\": {${C_RESET}\n"
        printf "  ${C_DIM}  \"command\": \"python3\",${C_RESET}\n"
        printf "  ${C_DIM}  \"args\": [\"%s/mcp-server.py\"]${C_RESET}\n" "$SCRIPT_DIR"
        printf "  ${C_DIM}}${C_RESET}\n"
    fi
    sleep 0.5
}

step_skill() {
    clear_screen
    echo ""
    progress_dots 4 4
    echo ""
    center "Step 4 of 4" "$C_DIM"
    center "AI Skill" "${C_BOLD}${C_WHITE}"
    echo ""

    box_top
    box_line "The ${C_ACCENT}/bingo${C_RESET} slash command teaches AI"
    box_line "how to use every bingo-light feature."
    box_empty
    box_line "  ${C_DIM}You type: /bingo${C_RESET}"
    box_line "  ${C_DIM}AI gets: full command reference${C_RESET}"
    box_bottom
    echo ""

    local src="$SCRIPT_DIR/.claude/commands/bingo.md"
    if [[ -f "$src" ]]; then
        if ask_styled "Install /bingo globally? [Y/n]"; then
            mkdir -p "$HOME/.claude/commands"
            cp "$src" "$HOME/.claude/commands/bingo.md"
            ok "/bingo installed globally"
        else
            skip "/bingo skipped"
        fi
    else
        skip "Skill file not found"
    fi
    sleep 0.5
}

# ─── Final Screen ─────────────────────────────────────────────────────────────

finish() {
    clear_screen
    echo ""
    echo ""

    center "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" "$C_SUCCESS"
    echo ""
    center "Setup complete" "${C_BOLD}${C_SUCCESS}"
    echo ""
    center "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" "$C_SUCCESS"
    echo ""
    echo ""

    box_top
    box_line "${C_WHITE}Quick start:${C_RESET}"
    box_empty
    box_line "  ${C_ACCENT}cd${C_RESET} your-forked-project"
    box_line "  ${C_ACCENT}bingo-light init${C_RESET} https://github.com/org/repo.git"
    box_line "  ${C_ACCENT}bingo-light patch new${C_RESET} my-feature"
    box_line "  ${C_ACCENT}bingo-light sync${C_RESET}"
    box_empty
    box_line "${C_WHITE}For AI:${C_RESET}"
    box_empty
    box_line "  Type ${C_ACCENT}/bingo${C_RESET} in Claude Code"
    box_line "  Or let AI call MCP tools directly"
    box_bottom
    echo ""
    echo ""
    center "https://github.com/DanOps-1/bingo-light" "$C_DIM"
    echo ""
    echo ""
}

# ─── Main ─────────────────────────────────────────────────────────────────────

splash
sleep 0.3
step_cli
step_completions
step_mcp
step_skill
finish

#!/bin/sh
# bingo-light installer — CLI + MCP server (50 tools) + AI skills
# https://github.com/DanOps-1/bingo-light
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | sh
#   curl -fsSL ... | sh -s -- --yes --bin-dir ~/.local/bin
#   ./install.sh [OPTIONS]
#
# Options:
#   -h, --help            Show usage
#   -y, --yes             Skip confirmation prompts
#       --bin-dir DIR     Install directory (default: /usr/local/bin)
#       --version REF     Git ref to install (default: main)
#       --no-completions  Skip shell completions
#       --no-mcp          Skip MCP / AI tool configuration

{ # Ensure entire script is downloaded before execution when piped

set -eu

# ─── Defaults ────────────────────────────────────────────────────────────────

GITHUB_RAW="https://raw.githubusercontent.com/DanOps-1/bingo-light"
VERSION="main"
BIN_DIR="/usr/local/bin"
OPT_YES=false
OPT_NO_MCP=false
OPT_NO_COMPLETIONS=false
_TMPDIR=""

# ─── Usage ───────────────────────────────────────────────────────────────────

usage() {
    cat <<'EOF'
bingo-light installer — AI-native fork maintenance

USAGE
    curl -fsSL .../install.sh | sh
    curl -fsSL .../install.sh | sh -s -- [OPTIONS]
    ./install.sh [OPTIONS]

OPTIONS
    -h, --help            Show this help
    -y, --yes             Skip all confirmation prompts
        --bin-dir DIR     Install directory (default: /usr/local/bin)
        --version REF     Git ref to install (default: main)
        --no-completions  Skip shell completion setup
        --no-mcp          Skip MCP / AI tool configuration

ENVIRONMENT
    NONINTERACTIVE=1      Same as --yes
    BIN_DIR=DIR           Same as --bin-dir
EOF
    exit 0
}

# ─── Argument parsing ────────────────────────────────────────────────────────

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)        usage ;;
        -y|--yes)         OPT_YES=true ;;
        --bin-dir)        shift; BIN_DIR="${1:?--bin-dir requires a value}" ;;
        --bin-dir=*)      BIN_DIR="${1#*=}" ;;
        --version)        shift; VERSION="${1:?--version requires a value}" ;;
        --version=*)      VERSION="${1#*=}" ;;
        --no-completions) OPT_NO_COMPLETIONS=true ;;
        --no-mcp)         OPT_NO_MCP=true ;;
        *)  printf 'error: unknown option: %s\n' "$1" >&2
            printf 'Run with --help for usage.\n' >&2
            exit 1 ;;
    esac
    shift
done

[ "${NONINTERACTIVE:-0}" = "1" ] && OPT_YES=true
[ "${CI:-}" = "true" ] && OPT_YES=true

# ─── Colors (TTY-aware) ─────────────────────────────────────────────────────

if [ -t 1 ] && [ "${TERM:-dumb}" != "dumb" ]; then
    BOLD=$(printf '\033[1m')    RED=$(printf '\033[31m')
    GREEN=$(printf '\033[32m')  YELLOW=$(printf '\033[33m')
    BLUE=$(printf '\033[34m')   DIM=$(printf '\033[2m')
    RESET=$(printf '\033[0m')
else
    BOLD="" RED="" GREEN="" YELLOW="" BLUE="" DIM="" RESET=""
fi

# ─── Message functions ───────────────────────────────────────────────────────

info()    { printf '  %s>%s %s\n' "$BLUE" "$RESET" "$*"; }
warn()    { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
error()   { printf '  %sx%s %s\n' "$RED" "$RESET" "$*" >&2; }
ok()      { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
skip()    { printf '  %s⊘ %s%s\n' "$DIM" "$*" "$RESET"; }

header() {
    printf '\n  %s%s%s\n' "$BOLD" "$*" "$RESET"
    printf '  %s' "$DIM"
    printf '%s' "$*" | sed 's/./-/g'
    printf '%s\n\n' "$RESET"
}

# ─── Utilities ───────────────────────────────────────────────────────────────

has_cmd() { command -v "$1" >/dev/null 2>&1; }

tildify() {
    case "$1" in
        "$HOME"/*) printf '~/%s' "${1#$HOME/}" ;;
        "$HOME")   printf '~' ;;
        *)         printf '%s' "$1" ;;
    esac
}

confirm() {
    if [ "$OPT_YES" = true ]; then return 0; fi
    if ! [ -t 0 ] && ! [ -t 1 ]; then return 0; fi
    printf '  %s?%s %s [Y/n] ' "$BOLD" "$RESET" "$1"
    read -r yn </dev/tty 2>/dev/null || yn="y"
    case "$yn" in
        ""|[yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

fetch() {
    if has_cmd curl; then
        curl -fsSL "$1" -o "$2"
    elif has_cmd wget; then
        wget -qO "$2" "$1"
    else
        error "curl or wget required"; exit 1
    fi
}

cleanup() {
    if [ -n "${_TMPDIR:-}" ] && [ -d "${_TMPDIR:-}" ]; then
        rm -rf "$_TMPDIR"
    fi
}
trap cleanup EXIT INT TERM

# Compare major.minor versions: version_gte actual minimum
version_gte() {
    a_major=${1%%.*}; a_minor=${1#*.}; a_minor=${a_minor%%.*}
    b_major=${2%%.*}; b_minor=${2#*.}; b_minor=${b_minor%%.*}
    [ "$a_major" -gt "$b_major" ] 2>/dev/null && return 0
    [ "$a_major" -eq "$b_major" ] 2>/dev/null && [ "$a_minor" -ge "$b_minor" ] 2>/dev/null && return 0
    return 1
}

# ─── Prerequisites ───────────────────────────────────────────────────────────

check_prerequisites() {
    header "Prerequisites"
    fails=0

    # Python 3.8+
    if has_cmd python3; then
        py_ver=$(python3 -c 'import sys; print("{}.{}".format(*sys.version_info[:2]))' 2>/dev/null) || py_ver="0.0"
        if version_gte "$py_ver" "3.8"; then
            ok "python3 $py_ver"
        else
            error "python3 >= 3.8 required (found $py_ver)"; fails=$((fails + 1))
        fi
    else
        error "python3 not found"; fails=$((fails + 1))
    fi

    # Git 2.20+
    if has_cmd git; then
        git_ver=$(git --version 2>/dev/null | sed 's/[^0-9.]//g') || git_ver="0.0"
        git_short=$(printf '%s' "$git_ver" | cut -d. -f1-2)
        if version_gte "$git_short" "2.20"; then
            ok "git $git_ver"
        else
            error "git >= 2.20 required (found $git_ver)"; fails=$((fails + 1))
        fi
    else
        error "git not found"; fails=$((fails + 1))
    fi

    # Download tool
    if has_cmd curl; then
        ok "curl"
    elif has_cmd wget; then
        ok "wget"
    else
        error "curl or wget required"; fails=$((fails + 1))
    fi

    if [ "$fails" -gt 0 ]; then
        printf '\n'
        error "$fails prerequisite(s) missing. Install them and retry."
        exit 1
    fi
}

# ─── Environment detection ───────────────────────────────────────────────────

detect_environment() {
    PLATFORM=$(uname -s 2>/dev/null || echo "unknown")
    ARCH=$(uname -m 2>/dev/null || echo "unknown")
    DETECTED_SHELL=$(basename "${SHELL:-sh}")
    SRC_DIR=""
    FROM_LOCAL=false

    # Detect local clone vs curl pipe
    if [ -f "${0:-}" ]; then
        _dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd) || _dir=""
        if [ -n "$_dir" ] && [ -f "$_dir/bingo-light" ]; then
            SRC_DIR="$_dir"
            FROM_LOCAL=true
        fi
    fi
}

# ─── Download files (if piped) ───────────────────────────────────────────────

fetch_files() {
    if [ "$FROM_LOCAL" = true ]; then return 0; fi

    SRC_DIR=$(mktemp -d) || { error "Failed to create temp directory"; exit 1; }
    _TMPDIR="$SRC_DIR"

    info "Downloading bingo-light @ ${BOLD}$VERSION${RESET} ..."
    base="$GITHUB_RAW/$VERSION"

    fetch "$base/bingo-light" "$SRC_DIR/bingo-light"

    mkdir -p "$SRC_DIR/bingo_core"
    for mod in __init__.py exceptions.py models.py git.py config.py state.py repo.py; do
        fetch "$base/bingo_core/$mod" "$SRC_DIR/bingo_core/$mod"
    done

    fetch "$base/mcp-server.py" "$SRC_DIR/mcp-server.py"

    if [ "$OPT_NO_COMPLETIONS" = false ]; then
        mkdir -p "$SRC_DIR/completions"
        for ext in bash zsh fish; do
            fetch "$base/completions/bingo-light.$ext" "$SRC_DIR/completions/bingo-light.$ext"
        done
    fi

    # setup.py is needed for `bingo-light setup`
    fetch "$base/bingo_core/setup.py" "$SRC_DIR/bingo_core/setup.py"

    ok "Downloaded all files"
}

# ─── Configuration summary ───────────────────────────────────────────────────

show_config() {
    header "Configuration"

    printf '  %-18s %s\n' "Platform:" "$PLATFORM ($ARCH)"
    printf '  %-18s %s\n' "Shell:" "$DETECTED_SHELL"
    printf '  %-18s %s\n' "Bin directory:" "$(tildify "$BIN_DIR")"
    printf '  %-18s %s\n' "Version:" "$VERSION"

    if [ "$FROM_LOCAL" = true ]; then
        printf '  %-18s %s\n' "Source:" "local ($(tildify "$SRC_DIR"))"
    else
        printf '  %-18s %s\n' "Source:" "github.com"
    fi

    printf '\n'
}

# ─── Install CLI ─────────────────────────────────────────────────────────────

install_cli() {
    header "Install CLI"

    # Check existing installation
    if has_cmd bingo-light; then
        existing_ver=$(bingo-light --version 2>/dev/null || echo "unknown")
        info "Existing installation found ($existing_ver)"
    fi

    # Determine if sudo is needed
    use_sudo=false
    if [ ! -d "$BIN_DIR" ]; then
        mkdir -p "$BIN_DIR" 2>/dev/null || use_sudo=true
    elif [ ! -w "$BIN_DIR" ]; then
        use_sudo=true
    fi

    if [ "$use_sudo" = true ]; then
        info "Root privileges required for $(tildify "$BIN_DIR")"
        if ! has_cmd sudo; then
            error "sudo not found. Run as root or use --bin-dir to install elsewhere."
            info "Example: $0 --bin-dir \$HOME/.local/bin"
            exit 1
        fi
        sudo -v 2>/dev/null || { error "Failed to obtain sudo"; exit 1; }
    fi

    _run() { if [ "$use_sudo" = true ]; then sudo "$@"; else "$@"; fi; }

    # Backup existing
    [ -f "$BIN_DIR/bingo-light" ] && _run cp "$BIN_DIR/bingo-light" "$BIN_DIR/bingo-light.bak" 2>/dev/null || true

    # Install executable
    _run install -m 755 "$SRC_DIR/bingo-light" "$BIN_DIR/bingo-light"

    # Install core library
    _run mkdir -p "$BIN_DIR/bingo_core"
    for f in "$SRC_DIR"/bingo_core/*.py; do
        _run install -m 644 "$f" "$BIN_DIR/bingo_core/$(basename "$f")"
    done

    # Install MCP server alongside CLI
    _run install -m 755 "$SRC_DIR/mcp-server.py" "$BIN_DIR/bingo-light-mcp"

    ok "bingo-light installed to $(tildify "$BIN_DIR")"
}

# ─── Configure (delegate to bingo-light setup) ──────────────────────────────

run_setup() {
    header "Configure AI Tools"

    setup_args=""
    if [ "$OPT_YES" = true ]; then
        setup_args="--yes"
    fi
    if [ "$OPT_NO_COMPLETIONS" = true ]; then
        setup_args="$setup_args --no-completions"
    fi

    # Use the just-installed bingo-light
    bl="$BIN_DIR/bingo-light"
    if [ -x "$bl" ]; then
        "$bl" setup $setup_args
    else
        # Fallback: run from source
        python3 "$SRC_DIR/bingo-light" setup $setup_args
    fi
}

# ─── Success ─────────────────────────────────────────────────────────────────

show_success() {
    printf '\n'
    printf '  %s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$GREEN" "$RESET"
    printf '  %s%s✓ bingo-light installed successfully%s\n' "$BOLD" "$GREEN" "$RESET"
    printf '  %s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$GREEN" "$RESET"

    # Check if BIN_DIR is on PATH
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            printf '\n'
            warn "$(tildify "$BIN_DIR") is not on your PATH"
            info "Add to your shell profile:"
            printf '    export PATH="%s:$PATH"\n' "$BIN_DIR"
            ;;
    esac

    printf '\n  %sQuick start:%s\n\n' "$BOLD" "$RESET"
    printf '    $ cd your-forked-project\n'
    printf '    $ %sbingo-light init%s https://github.com/org/repo.git\n' "$BLUE" "$RESET"
    printf '    $ %sbingo-light patch new%s my-feature\n' "$BLUE" "$RESET"
    printf '    $ %sbingo-light sync%s\n' "$BLUE" "$RESET"
    printf '\n  %sRe-run setup anytime:%s  bingo-light setup\n' "$DIM" "$RESET"
    printf '\n'
    printf '  %shttps://github.com/DanOps-1/bingo-light%s\n' "$DIM" "$RESET"
    printf '  %shttps://github.com/DanOps-1/bingo-light/issues%s\n' "$DIM" "$RESET"
    printf '\n'
}

# ─── Main ────────────────────────────────────────────────────────────────────

main() {
    printf '\n  %sbingo-light%s %sinstaller%s\n' "$BOLD" "$RESET" "$DIM" "$RESET"

    check_prerequisites
    detect_environment
    show_config

    if ! confirm "Proceed with installation?"; then
        info "Installation cancelled."
        exit 0
    fi

    fetch_files
    install_cli

    if [ "$OPT_NO_MCP" = false ]; then
        run_setup
    fi

    show_success
}

main

} # end of { } wrapper — prevents partial execution via curl pipe

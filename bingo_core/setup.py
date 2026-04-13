"""
bingo_core.setup — Interactive setup wizard for configuring MCP across AI tools.

Detects installed AI coding tools, presents a multi-select menu, and writes
the correct MCP server configuration for each selected tool.

Python 3.8+ stdlib only. Uses termios for raw input on Unix.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─── AI Tool Definitions ────────────────────────────────────────────────────


@dataclass
class AITool:
    """Describes one AI coding tool that supports MCP."""

    id: str
    name: str
    config_path: str  # with ~ or env vars, expanded at runtime
    top_key: str  # JSON key wrapping the server entry
    detect_dirs: List[str] = field(default_factory=list)
    detect_cmds: List[str] = field(default_factory=list)
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def expand_path(self) -> str:
        return os.path.expandvars(os.path.expanduser(self.config_path))

    def is_detected(self) -> bool:
        for d in self.detect_dirs:
            if os.path.isdir(os.path.expanduser(d)):
                return True
        for c in self.detect_cmds:
            if shutil.which(c):
                return True
        return False


def _get_tools() -> List[AITool]:
    """Return the list of all supported AI tools."""
    is_mac = platform.system() == "Darwin"
    is_win = platform.system() == "Windows"

    tools = [
        AITool(
            id="claude-code",
            name="Claude Code",
            config_path="~/.claude/settings.json",
            top_key="mcpServers",
            detect_dirs=["~/.claude"],
            detect_cmds=["claude"],
        ),
        AITool(
            id="claude-desktop",
            name="Claude Desktop",
            config_path=(
                "~/Library/Application Support/Claude/claude_desktop_config.json"
                if is_mac
                else "%APPDATA%\\Claude\\claude_desktop_config.json"
                if is_win
                else ""
            ),
            top_key="mcpServers",
            detect_dirs=(
                ["~/Library/Application Support/Claude"] if is_mac
                else ["%APPDATA%\\Claude"] if is_win
                else []
            ),
        ),
        AITool(
            id="cursor",
            name="Cursor",
            config_path="~/.cursor/mcp.json",
            top_key="mcpServers",
            detect_dirs=["~/.cursor"],
            detect_cmds=["cursor"],
        ),
        AITool(
            id="windsurf",
            name="Windsurf",
            config_path="~/.codeium/windsurf/mcp_config.json",
            top_key="mcpServers",
            detect_dirs=["~/.codeium/windsurf"],
        ),
        AITool(
            id="vscode-copilot",
            name="VS Code / Copilot",
            config_path="~/.vscode/mcp.json",
            top_key="servers",
            detect_dirs=["~/.vscode"],
            detect_cmds=["code"],
            extra_fields={"type": "stdio"},
            note="Also supports .vscode/mcp.json per project",
        ),
        AITool(
            id="cline",
            name="Cline",
            config_path="~/.vscode/cline_mcp_settings.json",
            top_key="mcpServers",
            detect_dirs=["~/.vscode"],
            note="Managed by Cline extension; edit via MCP Servers panel",
        ),
        AITool(
            id="roo-code",
            name="Roo Code",
            config_path="~/.vscode/roo_mcp_settings.json",
            top_key="mcpServers",
            detect_dirs=["~/.vscode"],
            note="Managed by Roo Code extension; edit via settings",
        ),
        AITool(
            id="zed",
            name="Zed",
            config_path="~/.config/zed/settings.json",
            top_key="context_servers",
            detect_dirs=["~/.config/zed"],
            detect_cmds=["zed"],
        ),
        AITool(
            id="gemini-cli",
            name="Gemini CLI",
            config_path="~/.gemini/settings.json",
            top_key="mcpServers",
            detect_dirs=["~/.gemini"],
            detect_cmds=["gemini"],
        ),
        AITool(
            id="amazon-q",
            name="Amazon Q Developer",
            config_path="~/.aws/amazonq/mcp.json",
            top_key="mcpServers",
            detect_dirs=["~/.aws/amazonq"],
        ),
    ]

    # Filter out tools with empty config paths (e.g. Claude Desktop on Linux)
    return [t for t in tools if t.config_path]


# ─── MCP Server Path Detection ──────────────────────────────────────────────


def find_mcp_server() -> Tuple[str, List[str]]:
    """Find the MCP server command and args.

    Returns (command, args) tuple. Tries:
    1. Installed `bingo-light-mcp` on PATH
    2. mcp-server.py next to the running script
    3. mcp-server.py next to bingo_core package
    """
    # 1. Installed binary on PATH
    for name in ("bingo-light-mcp", "mcp-server.py"):
        mcp_bin = shutil.which(name)
        if mcp_bin:
            return ("python3", [mcp_bin])

    # 2. Relative to running script
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    candidate = os.path.join(script_dir, "mcp-server.py")
    if os.path.isfile(candidate):
        return ("python3", [candidate])

    # 3. Relative to bingo_core package
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(os.path.dirname(pkg_dir), "mcp-server.py")
    if os.path.isfile(candidate):
        return ("python3", [candidate])

    # Fallback
    return ("python3", ["bingo-light-mcp"])


# ─── Config Writer ───────────────────────────────────────────────────────────


def write_mcp_config(
    tool: AITool,
    command: str,
    args: List[str],
    server_name: str = "bingo-light",
) -> Dict[str, Any]:
    """Write MCP server config for one AI tool.

    Returns dict with ok, tool, config_path, action (created|updated|error).
    """
    config_path = tool.expand_path()
    config_dir = os.path.dirname(config_path)

    try:
        os.makedirs(config_dir, exist_ok=True)
    except OSError as e:
        return {"ok": False, "tool": tool.id, "error": str(e)}

    # Read existing config
    data: Dict[str, Any] = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path) as f:
                data = json.load(f)
            action = "updated"
        except (json.JSONDecodeError, OSError):
            data = {}
            action = "created"
    else:
        action = "created"

    # Build the server entry
    entry: Dict[str, Any] = {"command": command, "args": args}
    entry.update(tool.extra_fields)

    # Write under the correct top-level key
    servers = data.setdefault(tool.top_key, {})
    already = server_name in servers
    servers[server_name] = entry

    try:
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    except OSError as e:
        return {"ok": False, "tool": tool.id, "error": str(e)}

    return {
        "ok": True,
        "tool": tool.id,
        "name": tool.name,
        "config_path": config_path,
        "action": "unchanged" if already else action,
    }


# ─── Interactive Multi-Select ────────────────────────────────────────────────


def _tildify(path: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    if path == home:
        return "~"
    return path


def _read_key() -> str:
    """Read a single keypress (including escape sequences) from /dev/tty."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                return f"\x1b[{ch3}"
            return ch + ch2
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key_tty() -> str:
    """Read a keypress from /dev/tty (works even when stdin is piped)."""
    import termios
    import tty

    try:
        fd = os.open("/dev/tty", os.O_RDONLY)
    except OSError:
        return _read_key()

    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1).decode("utf-8", errors="replace")
        if ch == "\x1b":
            ch2 = os.read(fd, 1).decode("utf-8", errors="replace")
            if ch2 == "[":
                ch3 = os.read(fd, 1).decode("utf-8", errors="replace")
                return f"\x1b[{ch3}"
            return ch + ch2
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.close(fd)


# ─── UI Primitives (clack-style tree-line) ───────────────────────────────────

# ANSI helpers
_B = "\033[1m"       # bold
_D = "\033[2m"       # dim
_R = "\033[0m"       # reset
_G = "\033[32m"      # green
_C = "\033[36m"      # cyan
_Y = "\033[33m"      # yellow
_RD = "\033[31m"     # red
_BG = "\033[38;5;75m"  # branded blue

BAR = f"{_D}│{_R}"   # vertical connector
END = f"{_D}└{_R}"   # end connector
DOT = f"{_C}◆{_R}"   # active section marker
CHK = f"{_G}◇{_R}"   # completed section marker


def _ui_header(out, version: str) -> None:
    out.write(f"\n  {_BG}{_B}◆  bingo-light setup{_R}  {_D}v{version}{_R}\n")
    out.write(f"  {BAR}\n")


def _ui_section(out, title: str, subtitle: str = "") -> None:
    out.write(f"  {BAR}\n")
    out.write(f"  {DOT}  {_B}{title}{_R}\n")
    if subtitle:
        out.write(f"  {BAR}  {_D}{subtitle}{_R}\n")


def _ui_info(out, text: str) -> None:
    out.write(f"  {BAR}  {_D}{text}{_R}\n")


def _ui_ok(out, text: str) -> None:
    out.write(f"  {BAR}  {_G}✓{_R} {text}\n")


def _ui_fail(out, text: str) -> None:
    out.write(f"  {BAR}  {_RD}✗{_R} {text}\n")


def _ui_skip(out, text: str) -> None:
    out.write(f"  {BAR}  {_D}⊘ {text}{_R}\n")


def _ui_done(out, text: str) -> None:
    out.write(f"  {BAR}\n")
    out.write(f"  {END}  {_G}{_B}{text}{_R}\n\n")


def _ui_bar(out) -> None:
    out.write(f"  {BAR}\n")


def multiselect(
    out,
    items: List[Dict[str, Any]],
    pre_selected: Optional[List[int]] = None,
) -> List[int]:
    """Interactive multi-select with clack-style rendering.

    items: list of {"label": str, "hint": str, "detected": bool}
    Returns list of selected indices.
    """
    selected = set(pre_selected or [])
    cursor = 0
    n = len(items)

    def render():
        for i, item in enumerate(items):
            is_cur = (i == cursor)
            is_sel = (i in selected)
            detected = item.get("detected", False)
            hint = item.get("hint", "")

            # Checkbox
            if is_sel:
                check = f"{_G}■{_R}"
            elif is_cur:
                check = f"{_C}□{_R}"
            else:
                check = f"{_D}□{_R}"

            # Label
            label = item["label"]
            if is_cur:
                label = f"{_B}{label}{_R}"

            # Hint
            if hint and detected:
                hint_str = f"  {_D}{hint}{_R}"
            elif hint:
                hint_str = f"  {_D}(not detected){_R}"
            else:
                hint_str = ""

            # Cursor indicator
            cur = f"{_C}›{_R}" if is_cur else " "

            out.write(f"  {BAR}  {cur} {check} {label}{hint_str}\n")

    def clear():
        for _ in range(n):
            out.write("\033[1A\033[2K")

    out.write(f"  {BAR}  {_D}↑/↓ navigate · space select · a all · enter confirm{_R}\n")
    out.write(f"  {BAR}\n")
    out.write("\033[?25l")
    out.flush()

    try:
        render()
        out.flush()

        while True:
            key = _read_key_tty()

            if key == "\x1b[A":  # Up
                cursor = (cursor - 1) % n
            elif key == "\x1b[B":  # Down
                cursor = (cursor + 1) % n
            elif key == " ":  # Space = toggle
                if cursor in selected:
                    selected.discard(cursor)
                else:
                    selected.add(cursor)
            elif key == "a":  # Toggle all
                if len(selected) == n:
                    selected.clear()
                else:
                    selected = set(range(n))
            elif key in ("\r", "\n"):  # Enter = confirm
                clear()
                for i, item in enumerate(items):
                    if i in selected:
                        out.write(f"  {BAR}    {_G}■{_R} {item['label']}\n")
                    else:
                        out.write(f"  {BAR}    {_D}□ {item['label']}{_R}\n")
                out.flush()
                return sorted(selected)
            elif key in ("\x03", "\x04"):  # Ctrl-C / Ctrl-D
                clear()
                out.write("\033[?25h")
                out.flush()
                raise KeyboardInterrupt

            clear()
            render()
            out.flush()
    finally:
        out.write("\033[?25h")
        out.flush()


# ─── Shell Completions ───────────────────────────────────────────────────────


def detect_shell() -> str:
    """Detect the user's shell."""
    return os.path.basename(os.environ.get("SHELL", "sh"))


def install_completions(shell: str, source_dir: str) -> Dict[str, Any]:
    """Install shell completions. Returns result dict."""
    home = os.path.expanduser("~")

    if shell == "bash":
        xdg = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share"))
        comp_dir = os.environ.get(
            "BASH_COMPLETION_USER_DIR",
            os.path.join(xdg, "bash-completion", "completions"),
        )
        src = os.path.join(source_dir, "completions", "bingo-light.bash")
        dst = os.path.join(comp_dir, "bingo-light")
    elif shell == "zsh":
        comp_dir = os.path.join(home, ".zfunc")
        src = os.path.join(source_dir, "completions", "bingo-light.zsh")
        dst = os.path.join(comp_dir, "_bingo-light")
    elif shell == "fish":
        comp_dir = os.path.join(home, ".config", "fish", "completions")
        src = os.path.join(source_dir, "completions", "bingo-light.fish")
        dst = os.path.join(comp_dir, "bingo-light.fish")
    else:
        return {"ok": False, "shell": shell, "error": f"Unsupported shell: {shell}"}

    if not os.path.isfile(src):
        return {"ok": False, "shell": shell, "error": f"Completion file not found: {src}"}

    try:
        os.makedirs(comp_dir, exist_ok=True)
        shutil.copy2(src, dst)
    except OSError as e:
        return {"ok": False, "shell": shell, "error": str(e)}

    # For zsh, ensure fpath is set in .zshrc
    if shell == "zsh":
        zshrc = os.path.join(home, ".zshrc")
        if os.path.isfile(zshrc):
            with open(zshrc) as f:
                content = f.read()
            if ".zfunc" not in content:
                with open(zshrc, "a") as f:
                    f.write("\nfpath=(~/.zfunc $fpath)\nautoload -Uz compinit && compinit\n")

    return {"ok": True, "shell": shell, "path": dst}


# ─── Skill / Custom Instructions ─────────────────────────────────────────────

SKILL_MARKER = "<!-- bingo-light-skill -->"


@dataclass
class SkillTarget:
    """Describes where to install the bingo-light skill/rules for one AI tool."""

    id: str
    name: str
    dest_path: str        # ~ expanded at runtime
    mode: str             # "copy" = drop file, "append" = append to existing file
    detect_dirs: List[str] = field(default_factory=list)
    detect_cmds: List[str] = field(default_factory=list)
    note: str = ""

    def expand_dest(self) -> str:
        return os.path.expandvars(os.path.expanduser(self.dest_path))

    def is_detected(self) -> bool:
        for d in self.detect_dirs:
            if os.path.isdir(os.path.expanduser(d)):
                return True
        for c in self.detect_cmds:
            if shutil.which(c):
                return True
        return False


def _get_skill_targets() -> List[SkillTarget]:
    """Return all supported skill/rules targets."""
    cline_rules = "~/Documents/Cline/Rules"

    return [
        SkillTarget(
            id="claude-code",
            name="Claude Code",
            dest_path="~/.claude/commands/bingo.md",
            mode="copy",
            detect_dirs=["~/.claude"],
            detect_cmds=["claude"],
            note="/bingo slash command",
        ),
        SkillTarget(
            id="windsurf",
            name="Windsurf",
            dest_path="~/.codeium/windsurf/memories/global_rules.md",
            mode="append",
            detect_dirs=["~/.codeium/windsurf"],
            note="Appends to global rules (6000 char limit)",
        ),
        SkillTarget(
            id="continue",
            name="Continue",
            dest_path="~/.continue/rules/bingo.md",
            mode="copy",
            detect_dirs=["~/.continue"],
        ),
        SkillTarget(
            id="cline",
            name="Cline",
            dest_path=cline_rules + "/bingo.md",
            mode="copy",
            detect_dirs=[cline_rules],
        ),
        SkillTarget(
            id="roo-code",
            name="Roo Code",
            dest_path="~/.roo/rules/bingo.md",
            mode="copy",
            detect_dirs=["~/.roo"],
        ),
        SkillTarget(
            id="gemini-cli",
            name="Gemini CLI",
            dest_path="~/.gemini/GEMINI.md",
            mode="append",
            detect_dirs=["~/.gemini"],
            detect_cmds=["gemini"],
            note="Appends to GEMINI.md",
        ),
    ]


def find_skill_file() -> Optional[str]:
    """Find the bingo.md skill file in common locations."""
    candidates = []

    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    candidates.append(os.path.join(script_dir, ".claude", "commands", "bingo.md"))

    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(pkg_dir)
    candidates.append(os.path.join(repo_dir, ".claude", "commands", "bingo.md"))

    # npm package layout
    candidates.append(os.path.join(script_dir, "..", ".claude", "commands", "bingo.md"))

    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def install_skill_to(target: SkillTarget, content: str) -> Dict[str, Any]:
    """Install skill content to one target. Returns result dict."""
    dest = target.expand_dest()
    dest_dir = os.path.dirname(dest)

    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as e:
        return {"ok": False, "id": target.id, "error": str(e)}

    try:
        if target.mode == "copy":
            with open(dest, "w") as f:
                f.write(content)
            return {"ok": True, "id": target.id, "path": dest, "action": "created"}

        elif target.mode == "append":
            # Check if already present
            existing = ""
            if os.path.isfile(dest):
                with open(dest) as f:
                    existing = f.read()
            if SKILL_MARKER in existing:
                return {"ok": True, "id": target.id, "path": dest, "action": "unchanged"}
            # Append with marker
            with open(dest, "a") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(f"\n{SKILL_MARKER}\n{content}\n")
            return {"ok": True, "id": target.id, "path": dest, "action": "appended"}

    except OSError as e:
        return {"ok": False, "id": target.id, "error": str(e)}

    return {"ok": False, "id": target.id, "error": "Unknown mode"}


# ─── Main Setup Flow ────────────────────────────────────────────────────────


def run_setup(
    yes: bool = False,
    json_mode: bool = False,
    no_completions: bool = False,
) -> Dict[str, Any]:
    """Run the interactive setup wizard.

    Returns a result dict summarizing what was configured.
    """
    from bingo_core import VERSION

    out = sys.stderr
    tools = _get_tools()
    command, args = find_mcp_server()
    results: List[Dict[str, Any]] = []
    is_tty = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    # ═════════════════════════════════════════════════════════════════════════
    # Header
    # ═════════════════════════════════════════════════════════════════════════
    if not json_mode and is_tty:
        _ui_header(out, VERSION)
        _ui_info(out, f"MCP server: {command} {' '.join(args)}")

    # ═════════════════════════════════════════════════════════════════════════
    # Step 1: MCP Server Configuration
    # ═════════════════════════════════════════════════════════════════════════
    items = []
    detected_indices = []
    for i, tool in enumerate(tools):
        detected = tool.is_detected()
        items.append({
            "label": tool.name,
            "hint": _tildify(tool.expand_path()),
            "detected": detected,
        })
        if detected:
            detected_indices.append(i)

    if not json_mode and is_tty:
        _ui_section(out, "MCP Server", "Connect bingo-light tools to your AI coding assistants")

    if yes:
        selected = detected_indices
        if not json_mode and is_tty:
            for i in selected:
                out.write(f"  {BAR}    {_G}■{_R} {tools[i].name}\n")
    elif is_tty:
        selected = multiselect(out, items, pre_selected=detected_indices)
    else:
        selected = detected_indices

    if not selected:
        if not json_mode and is_tty:
            _ui_skip(out, "No tools selected")

    # Configure each selected tool
    for idx in selected:
        tool = tools[idx]
        result = write_mcp_config(tool, command, args)
        results.append(result)
        if not json_mode and is_tty:
            if result["ok"]:
                _ui_ok(out, f"{tool.name} → {_tildify(result['config_path'])}")
            else:
                _ui_fail(out, f"{tool.name}: {result.get('error', '?')}")

    # ═════════════════════════════════════════════════════════════════════════
    # Step 2: Skills / Custom Instructions
    # ═════════════════════════════════════════════════════════════════════════
    skill_results: List[Dict[str, Any]] = []
    skill_src = find_skill_file()

    if skill_src:
        with open(skill_src) as f:
            skill_content = f.read()

        skill_targets = _get_skill_targets()

        if not json_mode and is_tty:
            _ui_section(out, "Skills / Custom Instructions", "Teach your AI how to use bingo-light")

        skill_items = []
        skill_detected = []
        for i, st in enumerate(skill_targets):
            detected = st.is_detected()
            hint = _tildify(st.expand_dest())
            if st.note:
                hint = f"{hint}  ({st.note})"
            skill_items.append({
                "label": st.name,
                "hint": hint,
                "detected": detected,
            })
            if detected:
                skill_detected.append(i)

        if yes:
            skill_selected = skill_detected
            if not json_mode and is_tty:
                for i in skill_selected:
                    out.write(f"  {BAR}    {_G}■{_R} {skill_targets[i].name}\n")
        elif is_tty:
            skill_selected = multiselect(out, skill_items, pre_selected=skill_detected)
        else:
            skill_selected = skill_detected

        for idx in skill_selected:
            st = skill_targets[idx]
            sr = install_skill_to(st, skill_content)
            skill_results.append(sr)
            if not json_mode and is_tty:
                if sr["ok"]:
                    action = sr.get("action", "")
                    suffix = f" {_D}({action}){_R}" if action == "unchanged" else ""
                    _ui_ok(out, f"{st.name} → {_tildify(sr['path'])}{suffix}")
                else:
                    _ui_fail(out, f"{st.name}: {sr.get('error', '?')}")

    # ═════════════════════════════════════════════════════════════════════════
    # Step 3: Shell Completions
    # ═════════════════════════════════════════════════════════════════════════
    if not no_completions:
        shell = detect_shell()
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        source_dir = (
            script_dir if os.path.isdir(os.path.join(script_dir, "completions"))
            else os.path.dirname(pkg_dir)
        )

        if os.path.isdir(os.path.join(source_dir, "completions")):
            if not json_mode and is_tty:
                _ui_section(out, "Shell Completions")
            comp_result = install_completions(shell, source_dir)
            if not json_mode and is_tty:
                if comp_result["ok"]:
                    _ui_ok(out, f"{shell} → {_tildify(comp_result['path'])}")
                else:
                    _ui_skip(out, f"{shell}: {comp_result.get('error', 'skipped')}")

    # ═════════════════════════════════════════════════════════════════════════
    # Summary
    # ═════════════════════════════════════════════════════════════════════════
    configured = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    skills_ok = [r for r in skill_results if r["ok"]]
    skills_fail = [r for r in skill_results if not r["ok"]]
    all_fail = len(failed) + len(skills_fail)

    if not json_mode and is_tty:
        parts = []
        if configured:
            parts.append(f"{len(configured)} MCP")
        if skills_ok:
            parts.append(f"{len(skills_ok)} skill(s)")
        summary = " + ".join(parts) if parts else "0"

        if all_fail:
            _ui_done(out, f"{summary} configured, {all_fail} failed")
        else:
            _ui_done(out, f"{summary} configured — ready to go!")

        # Next steps box
        out.write(f"  {_D}┌─────────────────────────────────────────────────┐{_R}\n")
        out.write(f"  {_D}│{_R}  {_B}Next steps:{_R}                                    {_D}│{_R}\n")
        out.write(f"  {_D}│{_R}                                                 {_D}│{_R}\n")
        out.write(f"  {_D}│{_R}    cd your-forked-project                      {_D}│{_R}\n")
        out.write(f"  {_D}│{_R}    {_C}bingo-light init{_R} <upstream-url>              {_D}│{_R}\n")
        out.write(f"  {_D}│{_R}    {_C}bingo-light sync{_R}                              {_D}│{_R}\n")
        out.write(f"  {_D}│{_R}                                                 {_D}│{_R}\n")
        out.write(f"  {_D}│{_R}  Re-run anytime: {_C}bingo-light setup{_R}              {_D}│{_R}\n")
        out.write(f"  {_D}└─────────────────────────────────────────────────┘{_R}\n")
        out.write("\n")

    return {
        "ok": all_fail == 0,
        "configured": [r["tool"] for r in configured],
        "failed": [r["tool"] for r in failed],
        "skills": [r["id"] for r in skills_ok],
        "results": results,
        "skill_results": skill_results,
    }

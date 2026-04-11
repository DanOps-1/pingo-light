#!/usr/bin/env python3
"""
bingo-light MCP Server — Zero-dependency MCP tool server.

Exposes bingo-light CLI commands as MCP tools so any MCP-compatible LLM client
(Claude Code, Claude Desktop, VS Code Copilot, Cursor, etc.) can call them directly.

Protocol: JSON-RPC 2.0 over stdio (MCP specification).
Dependencies: Python 3.8+ standard library only.

Usage:
  # Run directly:
  python3 mcp-server.py

  # In Claude Code settings.json:
  { "mcpServers": { "bingo-light": { "command": "python3", "args": ["/path/to/mcp-server.py"] } } }

  # In Claude Desktop config:
  { "mcpServers": { "bingo-light": { "command": "python3", "args": ["/path/to/mcp-server.py"] } } }
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# ─── Tool Definitions ─────────────────────────────────────────────────────────

BL = os.environ.get("BINGO_LIGHT_BIN", str(Path(__file__).parent / "bingo-light"))

TOOLS = [
    {
        "name": "bingo_status",
        "description": (
            "Check the health of your fork: how far behind upstream, list all patches, "
            "predict potential conflicts. Run this FIRST to understand the current state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository (required)"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_init",
        "description": (
            "Initialize bingo-light in a git repository. Sets up upstream tracking, "
            "creates patch branch, enables rerere. Run once per forked project."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "upstream_url": {
                    "type": "string",
                    "description": "URL of the original upstream repository"
                },
                "branch": {
                    "type": "string",
                    "description": "Upstream branch to track (default: auto-detect)"
                }
            },
            "required": ["cwd", "upstream_url"]
        }
    },
    {
        "name": "bingo_patch_new",
        "description": (
            "Create a new patch from current changes. Each patch = one atomic customization "
            "on top of upstream. Stage changes first (git add) or let it auto-stage everything."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "name": {
                    "type": "string",
                    "description": "Patch name (alphanumeric, hyphens, underscores)"
                },
                "description": {
                    "type": "string",
                    "description": "Brief one-line description of the patch"
                }
            },
            "required": ["cwd", "name"]
        }
    },
    {
        "name": "bingo_patch_list",
        "description": "List all patches in the stack with stats. Use verbose=true for per-file details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "verbose": {
                    "type": "boolean",
                    "description": "Show per-file change details (default: false)"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_patch_show",
        "description": "Show full diff and stats for a specific patch.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "target": {
                    "type": "string",
                    "description": "Patch name or 1-based index"
                }
            },
            "required": ["cwd", "target"]
        }
    },
    {
        "name": "bingo_patch_drop",
        "description": "Remove a patch from the stack.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "target": {
                    "type": "string",
                    "description": "Patch name or 1-based index"
                }
            },
            "required": ["cwd", "target"]
        }
    },
    {
        "name": "bingo_patch_export",
        "description": "Export all patches as numbered .patch files (git format-patch) plus quilt-compatible series file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory (default: .bl-patches)"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_patch_import",
        "description": "Import .patch file(s) into the stack.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "path": {
                    "type": "string",
                    "description": "Path to .patch file or directory of patches"
                }
            },
            "required": ["cwd", "path"]
        }
    },
    {
        "name": "bingo_sync",
        "description": (
            "Sync with upstream: fetch latest changes and rebase all patches. "
            "Use dry_run=true to preview without making changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview only, don't modify anything (default: false)"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_undo",
        "description": "Undo the last sync operation by restoring patches branch to previous state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_doctor",
        "description": (
            "Diagnose setup issues: checks git version, rerere, upstream remote, branch structure, "
            "and tests whether patches apply cleanly on latest upstream."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_diff",
        "description": "Show combined diff of all patches vs upstream (total fork divergence).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_auto_sync",
        "description": (
            "Generate GitHub Actions workflow for automated daily upstream sync. "
            "Creates .github/workflows/bingo-light-sync.yml."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "schedule": {
                    "type": "string",
                    "enum": ["daily", "6h", "weekly"],
                    "description": "Sync frequency (default: daily)"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_conflict_analyze",
        "description": (
            "Analyze current rebase conflicts. Returns structured info about each conflicted file: "
            "the 'ours' version (upstream), 'theirs' version (your patch), conflict count, and resolution hints. "
            "Call this when bingo_sync reports a conflict to understand what needs fixing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                }
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_conflict_resolve",
        "description": (
            "Resolve a conflict during rebase by writing the resolved content to a file, "
            "staging it, and continuing the rebase. Use after bingo_conflict_analyze."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Path to the git repository"
                },
                "file": {
                    "type": "string",
                    "description": "Path to the conflicted file (relative to repo root)"
                },
                "content": {
                    "type": "string",
                    "description": "The fully resolved file content (no conflict markers)"
                }
            },
            "required": ["cwd", "file", "content"]
        }
    },
    {
        "name": "bingo_config",
        "description": "Get, set, or list bingo-light configuration values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Path to the git repository"},
                "action": {"type": "string", "enum": ["get", "set", "list"], "description": "Config action"},
                "key": {"type": "string", "description": "Config key (for get/set)"},
                "value": {"type": "string", "description": "Config value (for set)"}
            },
            "required": ["cwd", "action"]
        }
    },
    {
        "name": "bingo_history",
        "description": "Show sync history: timestamps, upstream commits integrated, patch hash mappings.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string", "description": "Path to the git repository"}},
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_test",
        "description": "Run the configured test command. Set test command first: config set test.command 'make test'.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string", "description": "Path to the git repository"}},
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_patch_meta",
        "description": "Get or set patch metadata (reason, tags, expires, upstream_pr, status).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Path to the git repository"},
                "name": {"type": "string", "description": "Patch name"},
                "set_field": {"type": "string", "enum": ["reason", "tag", "expires", "upstream_pr", "status"], "description": "Field to set (omit to get)"},
                "value": {"type": "string", "description": "Value to set"}
            },
            "required": ["cwd", "name"]
        }
    },
    {
        "name": "bingo_patch_squash",
        "description": "Squash two adjacent patches into one.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Path to the git repository"},
                "index1": {"type": "integer", "description": "First patch index (1-based)"},
                "index2": {"type": "integer", "description": "Second patch index (1-based)"}
            },
            "required": ["cwd", "index1", "index2"]
        }
    },
    {
        "name": "bingo_patch_reorder",
        "description": "Reorder patches non-interactively. Provide new order as comma-separated indices.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Path to the git repository"},
                "order": {"type": "string", "description": "New order as comma-separated indices, e.g. '3,1,2'"}
            },
            "required": ["cwd", "order"]
        }
    },
    {
        "name": "bingo_workspace_status",
        "description": "Show status of all repos in the workspace (multi-repo overview).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Any directory (workspace config is global)"}
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_patch_edit",
        "description": "Amend an existing patch by folding staged changes into it. Stage changes with git add first, then call this.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Path to the git repository"},
                "target": {"type": "string", "description": "Patch name or index to edit"}
            },
            "required": ["cwd", "target"]
        }
    },
    {
        "name": "bingo_workspace_init",
        "description": "Initialize a multi-repo workspace.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}, "required": ["cwd"]}
    },
    {
        "name": "bingo_workspace_add",
        "description": "Add a repository to the workspace.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "path": {"type": "string"}, "alias": {"type": "string"}}, "required": ["cwd", "path"]}
    },
    {
        "name": "bingo_workspace_sync",
        "description": "Sync all repositories in the workspace.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}, "required": ["cwd"]}
    },
    {
        "name": "bingo_workspace_list",
        "description": "List all repositories in the workspace.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}, "required": ["cwd"]}
    },
]

# ─── Command Mapping ──────────────────────────────────────────────────────────

def run_bl(args: list[str], cwd: str, input_text: str = "", env_extra: dict = None) -> dict:
    """Run bingo-light CLI and return structured result."""
    env = os.environ.copy()
    env["NO_COLOR"] = "1"  # Disable ANSI colors for machine-readable output
    if env_extra:
        env.update(env_extra)

    # Ensure JSON + non-interactive mode for all MCP calls
    if "--json" not in args:
        args = args + ["--json"]
    if "--yes" not in args:
        args = args + ["--yes"]

    try:
        result = subprocess.run(
            [BL] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
            input=input_text or None,
            env=env,
        )
        output = result.stdout.strip()
        # Don't append stderr to stdout — it would corrupt JSON output.
        # Only use stderr if stdout is empty (command failed without JSON output).
        if not output and result.stderr:
            output = result.stderr.strip()
        return {
            "content": [{"type": "text", "text": output}],
            "isError": result.returncode != 0,
        }
    except FileNotFoundError:
        return {
            "content": [{"type": "text", "text": f"bingo-light not found at: {BL}\nInstall: cp bingo-light /usr/local/bin/"}],
            "isError": True,
        }
    except subprocess.TimeoutExpired:
        return {
            "content": [{"type": "text", "text": "Command timed out (120s). The operation may need manual intervention."}],
            "isError": True,
        }


def handle_tool_call(name: str, arguments: dict) -> dict:
    """Map MCP tool calls to bingo-light CLI commands."""
    cwd = arguments.get("cwd", ".")

    # Validate cwd is a real directory (prevent arbitrary filesystem access)
    if not os.path.isdir(cwd):
        return {"content": [{"type": "text", "text": f"Invalid cwd: directory does not exist: {cwd}"}], "isError": True}

    if name == "bingo_status":
        return run_bl(["status"], cwd)

    elif name == "bingo_init":
        args = ["init", arguments["upstream_url"]]
        if arguments.get("branch"):
            args.append(arguments["branch"])
        return run_bl(args, cwd)

    elif name == "bingo_patch_new":
        desc = arguments.get("description", "no description")
        env_extra = {"BINGO_DESCRIPTION": desc}
        return run_bl(["patch", "new", arguments["name"]], cwd, env_extra=env_extra)

    elif name == "bingo_patch_list":
        args = ["patch", "list"]
        if arguments.get("verbose"):
            args.append("-v")
        return run_bl(args, cwd)

    elif name == "bingo_patch_show":
        return run_bl(["patch", "show", arguments["target"]], cwd)

    elif name == "bingo_patch_drop":
        return run_bl(["patch", "drop", arguments["target"]], cwd)

    elif name == "bingo_patch_export":
        args = ["patch", "export"]
        if arguments.get("output_dir"):
            args.append(arguments["output_dir"])
        return run_bl(args, cwd)

    elif name == "bingo_patch_import":
        return run_bl(["patch", "import", arguments["path"]], cwd)

    elif name == "bingo_sync":
        args = ["sync", "--force"]  # Skip interactive prompt
        if arguments.get("dry_run"):
            args = ["sync", "--dry-run"]
        return run_bl(args, cwd)

    elif name == "bingo_undo":
        return run_bl(["undo"], cwd)

    elif name == "bingo_doctor":
        return run_bl(["doctor"], cwd)

    elif name == "bingo_diff":
        return run_bl(["diff"], cwd)

    elif name == "bingo_auto_sync":
        schedule = arguments.get("schedule", "daily")
        return run_bl(["auto-sync"], cwd, env_extra={"BINGO_SCHEDULE": schedule})

    elif name == "bingo_conflict_analyze":
        return run_bl(["conflict-analyze"], cwd)

    elif name == "bingo_conflict_resolve":
        try:
            file_path = str(Path(cwd, arguments["file"]).resolve())
            Path(file_path).relative_to(Path(cwd).resolve())
        except (ValueError, RuntimeError):
            return {"content": [{"type": "text", "text": f"Security: path escapes repository: {arguments['file']}"}], "isError": True}
        if not os.path.exists(os.path.join(cwd, ".git", "rebase-merge")) and not os.path.exists(os.path.join(cwd, ".git", "rebase-apply")):
            return {"content": [{"type": "text", "text": "Not in a rebase. Nothing to resolve."}], "isError": True}
        content = arguments["content"]
        try:
            # O_NOFOLLOW prevents symlink-based TOCTOU attacks
            fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, "w") as f:
                f.write(content)
            result = subprocess.run(
                ["git", "add", file_path],  # Use validated path, not raw input
                cwd=cwd, capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return {"content": [{"type": "text", "text": f"git add failed: {result.stderr}"}], "isError": True}
            # Try to continue rebase
            result = subprocess.run(
                ["git", "rebase", "--continue"],
                cwd=cwd, capture_output=True, text=True, timeout=60,
                env={**os.environ, "GIT_EDITOR": "true"},
            )
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            return {
                "content": [{"type": "text", "text": output.strip()}],
                "isError": result.returncode != 0,
            }
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}

    elif name == "bingo_config":
        action = arguments.get("action", "list")
        if action == "get":
            return run_bl(["config", "get", arguments.get("key", "")], cwd)
        elif action == "set":
            return run_bl(["config", "set", arguments.get("key", ""), arguments.get("value", "")], cwd)
        else:
            return run_bl(["config", "list"], cwd)

    elif name == "bingo_history":
        return run_bl(["history"], cwd)

    elif name == "bingo_test":
        return run_bl(["test"], cwd)

    elif name == "bingo_patch_meta":
        args = ["patch", "meta", arguments["name"]]
        if arguments.get("set_field") and "value" in arguments:
            args += [f"--set-{arguments['set_field'].replace('_', '-')}", arguments["value"]]
        return run_bl(args, cwd)

    elif name == "bingo_patch_squash":
        return run_bl(["patch", "squash", str(arguments["index1"]), str(arguments["index2"])], cwd)

    elif name == "bingo_patch_reorder":
        return run_bl(["patch", "reorder", "--order", arguments["order"]], cwd)

    elif name == "bingo_workspace_status":
        return run_bl(["workspace", "status"], cwd)

    elif name == "bingo_patch_edit":
        return run_bl(["patch", "edit", arguments["target"]], cwd)

    elif name == "bingo_workspace_init":
        return run_bl(["workspace", "init"], cwd)
    elif name == "bingo_workspace_add":
        args = ["workspace", "add", arguments["path"]]
        if arguments.get("alias"):
            args.append(arguments["alias"])
        return run_bl(args, cwd)
    elif name == "bingo_workspace_sync":
        return run_bl(["workspace", "sync"], cwd)
    elif name == "bingo_workspace_list":
        return run_bl(["workspace", "list"], cwd)

    else:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }

# ─── MCP JSON-RPC Protocol ───────────────────────────────────────────────────

_PARSE_ERROR = object()  # Sentinel: bad message, but not EOF

def read_message() -> dict | None:
    """Read a JSON-RPC message from stdin (MCP stdio transport).
    Returns dict on success, None on EOF, _PARSE_ERROR on bad input."""
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            return None  # EOF
        line = line.strip()
        if line == "":
            break  # End of headers
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    try:
        content_length = int(headers.get("content-length", 0))
    except (ValueError, TypeError):
        return _PARSE_ERROR
    if content_length == 0:
        return _PARSE_ERROR

    body = sys.stdin.read(content_length)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return _PARSE_ERROR


def send_message(msg: dict):
    """Write a JSON-RPC message to stdout (MCP stdio transport)."""
    body = json.dumps(msg)
    header = f"Content-Length: {len(body.encode())}\r\n\r\n"
    sys.stdout.write(header)
    sys.stdout.write(body)
    sys.stdout.flush()


def make_response(id, result):
    return {"jsonrpc": "2.0", "id": id, "result": result}


def make_error(id, code, message):
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def main():
    """Main MCP server loop."""
    while True:
        msg = read_message()
        if msg is None:
            break  # EOF — client disconnected
        if msg is _PARSE_ERROR:
            continue  # Skip malformed message, keep serving

        method = msg.get("method", "")
        id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            send_message(make_response(id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "bingo-light",
                    "version": "1.2.0",
                },
            }))

        elif method == "notifications/initialized":
            pass  # No response needed for notifications

        elif method == "tools/list":
            send_message(make_response(id, {"tools": TOOLS}))

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                result = handle_tool_call(tool_name, arguments)
            except Exception as e:
                result = {"content": [{"type": "text", "text": f"Internal error: {e}"}], "isError": True}
            send_message(make_response(id, result))

        elif method == "ping":
            send_message(make_response(id, {}))

        elif id is not None:
            send_message(make_error(id, -32601, f"Method not found: {method}"))
        # else: unknown notification, ignore


if __name__ == "__main__":
    main()

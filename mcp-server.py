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
import sys

# ─── Direct import of bingo_core ─────────────────────────────────────────────

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bingo_core import Repo, BingoError  # noqa: E402

# ─── Tool Definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "bingo_status",
        "description": (
            "Check the health of your fork. Returns recommended_action telling you exactly "
            "what to do next: 'up_to_date', 'sync_safe', 'sync_risky', or 'resolve_conflict'. "
            "ALWAYS call this FIRST. Read the recommended_action field — don't guess."
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
            "Low-level sync: fetch upstream and rebase patches. Prefer bingo_smart_sync instead — "
            "it handles conflicts automatically. Only use bingo_sync when you need dry_run preview "
            "or fine-grained control over the rebase process."
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
    {
        "name": "bingo_smart_sync",
        "description": (
            "ONE-SHOT SYNC: Fetches upstream, rebases all patches, and auto-resolves conflicts "
            "via rerere — all in a single call. Returns synced result or remaining conflicts with "
            "ours/theirs/merge_hint for each. USE THIS instead of bingo_sync when you want the "
            "simplest possible sync flow. Only calls you back if rerere can't auto-resolve."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Path to the git repository"}
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_session",
        "description": (
            "Read or update AI session notes (.bingo/session.md). Call with update=true "
            "at the START of a conversation to snapshot fork state. Read without update "
            "to get cached context without running expensive git commands."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Path to the git repository"},
                "update": {"type": "boolean", "description": "If true, regenerate notes from current state"}
            },
            "required": ["cwd"]
        }
    },
    # ── Dependency Patching Tools ─────────────────────────────────────────
    {
        "name": "bingo_dep_patch",
        "description": (
            "Create a patch for a modified npm/pip dependency. After modifying files in "
            "node_modules/ or site-packages/, call this to generate a .patch file. "
            "The patch survives npm install / pip install via `bingo_dep_apply`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Project directory"},
                "package": {"type": "string", "description": "Package name (e.g. 'lodash', 'requests')"},
                "patch_name": {"type": "string", "description": "Optional patch name"},
                "description": {"type": "string", "description": "What this patch fixes"}
            },
            "required": ["cwd", "package"]
        }
    },
    {
        "name": "bingo_dep_apply",
        "description": (
            "Re-apply all dependency patches after npm install / pip install. "
            "Call this as a postinstall hook or after any package manager update."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Project directory"},
                "package": {"type": "string", "description": "Optional: apply only this package's patches"}
            },
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_dep_status",
        "description": (
            "Show health of all dependency patches. Reports version mismatches "
            "(upstream updated but patches were generated against old version)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string", "description": "Project directory"}},
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_dep_sync",
        "description": (
            "After npm update / pip install --upgrade, re-apply patches and detect conflicts. "
            "Returns ok if all patches apply cleanly, or conflict details if patches broke."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string", "description": "Project directory"}},
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_dep_list",
        "description": "List all dependency patches across all tracked packages.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string", "description": "Project directory"}},
            "required": ["cwd"]
        }
    },
    {
        "name": "bingo_dep_drop",
        "description": "Remove a dependency patch or all patches for a package.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Project directory"},
                "package": {"type": "string", "description": "Package name"},
                "patch_name": {"type": "string", "description": "Specific patch to drop (omit for all)"}
            },
            "required": ["cwd", "package"]
        }
    },
]

# ─── Command Mapping ──────────────────────────────────────────────────────────


def _result(data: dict) -> dict:
    """Convert a Repo method return dict to MCP tool result format."""
    is_error = not data.get("ok", False)
    return {
        "content": [{"type": "text", "text": json.dumps(data)}],
        "isError": is_error,
    }


def handle_tool_call(name: str, arguments: dict) -> dict:
    """Map MCP tool calls to bingo_core.Repo methods directly."""
    cwd = arguments.get("cwd", ".")

    # Type validation — MCP clients can send any JSON type
    if not isinstance(cwd, str):
        return {"content": [{"type": "text", "text": f"Invalid cwd: expected string, got {type(cwd).__name__}"}], "isError": True}

    # Validate cwd is a real directory (prevent arbitrary filesystem access)
    if not os.path.isdir(cwd):
        return {"content": [{"type": "text", "text": f"Invalid cwd: directory does not exist: {cwd}"}], "isError": True}

    try:
        repo = Repo(cwd)

        if name == "bingo_status":
            return _result(repo.status())

        elif name == "bingo_init":
            return _result(repo.init(
                arguments["upstream_url"],
                arguments.get("branch", ""),
            ))

        elif name == "bingo_sync":
            return _result(repo.sync(
                dry_run=bool(arguments.get("dry_run")),
                force=True,  # MCP calls are non-interactive
            ))

        elif name == "bingo_smart_sync":
            return _result(repo.smart_sync())

        elif name == "bingo_undo":
            return _result(repo.undo())

        elif name == "bingo_doctor":
            return _result(repo.doctor())

        elif name == "bingo_diff":
            return _result(repo.diff())

        elif name == "bingo_history":
            return _result(repo.history())

        elif name == "bingo_conflict_analyze":
            return _result(repo.conflict_analyze())

        elif name == "bingo_conflict_resolve":
            return _result(repo.conflict_resolve(
                arguments.get("file", ""),
                arguments.get("content", ""),
            ))

        elif name == "bingo_log":
            return _result(repo.history())

        elif name == "bingo_config":
            action = arguments.get("action", "list")
            if action == "get":
                return _result(repo.config_get(arguments.get("key", "")))
            elif action == "set":
                return _result(repo.config_set(
                    arguments.get("key", ""),
                    arguments.get("value", ""),
                ))
            else:
                return _result(repo.config_list())

        elif name == "bingo_test":
            return _result(repo.test())

        elif name == "bingo_auto_sync":
            return _result(repo.auto_sync(
                schedule=arguments.get("schedule", "daily"),
            ))

        elif name == "bingo_session":
            return _result(repo.session(
                update=bool(arguments.get("update")),
            ))

        elif name == "bingo_patch_new":
            return _result(repo.patch_new(
                arguments["name"],
                arguments.get("description", "no description"),
            ))

        elif name == "bingo_patch_list":
            return _result(repo.patch_list(
                verbose=bool(arguments.get("verbose")),
            ))

        elif name == "bingo_patch_show":
            return _result(repo.patch_show(arguments["target"]))

        elif name == "bingo_patch_drop":
            return _result(repo.patch_drop(arguments["target"]))

        elif name == "bingo_patch_edit":
            return _result(repo.patch_edit(arguments["target"]))

        elif name == "bingo_patch_export":
            return _result(repo.patch_export(
                arguments.get("output_dir", ".bl-patches"),
            ))

        elif name == "bingo_patch_import":
            return _result(repo.patch_import(arguments["path"]))

        elif name == "bingo_patch_meta":
            return _result(repo.patch_meta(
                arguments["name"],
                arguments.get("set_field", ""),
                arguments.get("value", ""),
            ))

        elif name == "bingo_patch_squash":
            return _result(repo.patch_squash(
                arguments["index1"],
                arguments["index2"],
            ))

        elif name == "bingo_patch_reorder":
            return _result(repo.patch_reorder(
                arguments.get("order", ""),
            ))

        elif name == "bingo_workspace_init":
            return _result(repo.workspace_init())

        elif name == "bingo_workspace_add":
            return _result(repo.workspace_add(
                arguments["path"],
                arguments.get("alias", ""),
            ))

        elif name == "bingo_workspace_list":
            return _result(repo.workspace_list())

        elif name == "bingo_workspace_sync":
            return _result(repo.workspace_sync())

        elif name == "bingo_workspace_status":
            return _result(repo.workspace_status())

        # ── Dependency patching tools ────────────────────────────────────
        elif name.startswith("bingo_dep_"):
            from bingo_core.dep import DepManager
            dm = DepManager(cwd)

            if name == "bingo_dep_patch":
                return _result(dm.patch(
                    arguments["package"],
                    arguments.get("patch_name", ""),
                    arguments.get("description", ""),
                ))
            elif name == "bingo_dep_apply":
                return _result(dm.apply(arguments.get("package", "")))
            elif name == "bingo_dep_status":
                return _result(dm.status())
            elif name == "bingo_dep_sync":
                return _result(dm.sync())
            elif name == "bingo_dep_list":
                return _result(dm.list_patches())
            elif name == "bingo_dep_drop":
                return _result(dm.drop(
                    arguments["package"],
                    arguments.get("patch_name", ""),
                ))

        else:
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                "isError": True,
            }

    except BingoError as e:
        return _result({"ok": False, "error": str(e)})

    except Exception as e:
        return _result({"ok": False, "error": f"Internal error: {e}"})

# ─── MCP JSON-RPC Protocol ───────────────────────────────────────────────────

_PARSE_ERROR = object()  # Sentinel: bad message, but not EOF


def read_message():
    """Read a JSON-RPC message from stdin (MCP stdio transport).

    MCP spec defines stdio as newline-delimited JSON (every version since
    2024-11-05). All major clients (Claude Code, Cursor, Windsurf, Cline,
    Continue, Roo Code, Gemini CLI, Codex CLI, Zed, JetBrains, GitHub
    Copilot) send bare JSON lines.

    Also supports Content-Length header framing (LSP-style) as a fallback
    for compatibility with older test infrastructure.

    Returns dict on success, None on EOF, _PARSE_ERROR on bad input.
    """
    line = sys.stdin.readline()
    if not line:
        return None  # EOF

    stripped = line.strip()
    if not stripped:
        return _PARSE_ERROR  # Empty line — skip

    # Standard MCP: newline-delimited JSON
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return _PARSE_ERROR

    # Fallback: Content-Length header framing (LSP-style)
    global _use_content_length
    _use_content_length = True
    headers = {}
    if ":" in stripped:
        key, value = stripped.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    while True:
        hline = sys.stdin.readline()
        if not hline:
            return None
        hline = hline.strip()
        if hline == "":
            break
        if ":" in hline:
            key, value = hline.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    try:
        content_length = int(headers.get("content-length", 0))
    except (ValueError, TypeError):
        return _PARSE_ERROR
    if content_length <= 0 or content_length > 10 * 1024 * 1024:
        return _PARSE_ERROR

    body = sys.stdin.read(content_length)
    if len(body) < content_length:
        return _PARSE_ERROR
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return _PARSE_ERROR


# Framing mode: newline-delimited JSON by default (MCP spec),
# switches to Content-Length if client sends headers.
_use_content_length = False


def send_message(msg: dict):
    """Write a JSON-RPC message to stdout (MCP stdio transport)."""
    body = json.dumps(msg)
    if _use_content_length:
        sys.stdout.write(f"Content-Length: {len(body.encode())}\r\n\r\n")
        sys.stdout.write(body)
    else:
        sys.stdout.write(body + "\n")
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
            # Echo back the client's protocol version for compatibility
            client_version = params.get("protocolVersion", "2024-11-05")
            send_message(make_response(id, {
                "protocolVersion": client_version,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "bingo-light",
                    "version": "2.1.1",
                },
            }))

        elif method == "notifications/initialized":
            pass  # No response needed for notifications

        elif method == "tools/list":
            send_message(make_response(id, {"tools": TOOLS}))

        elif method == "tools/call":
            if id is None:
                continue  # JSON-RPC notification — must not respond
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                result = handle_tool_call(tool_name, arguments)
            except Exception as e:
                result = {"content": [{"type": "text", "text": f"Internal error: {e}"}], "isError": True}
            send_message(make_response(id, result))

        elif method == "ping":
            if id is not None:
                send_message(make_response(id, {}))

        elif id is not None:
            send_message(make_error(id, -32601, f"Method not found: {method}"))
        # else: unknown notification, ignore per JSON-RPC 2.0 spec


if __name__ == "__main__":
    main()

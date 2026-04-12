# Comprehensive Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all 11 improvements from the design spec: split bingo_core into a package, rewrite MCP server to direct import, add conflict-resolve command, workspace remove, deduplicate conflict handling, differentiate log/history, fix tags repr, update completions, add tests, update CLAUDE.md, verify CI lint.

**Architecture:** Split `bingo_core.py` (2,874 lines) into a 6-module package maintaining all public exports. Rewrite `mcp-server.py` to import `bingo_core.Repo` directly instead of subprocess. Add `conflict-resolve` as the missing piece of the AI conflict resolution loop. All other changes are UX polish, test coverage, and documentation.

**Tech Stack:** Python 3.8+ stdlib only, git, bash/zsh/fish completions, GitHub Actions CI.

---

### Task 1: Create bingo_core package — exceptions and models

**Files:**
- Create: `bingo_core/__init__.py`
- Create: `bingo_core/exceptions.py`
- Create: `bingo_core/models.py`
- Reference: `bingo_core.py:25-119`

- [ ] **Step 1: Create package directory**

```bash
mkdir -p bingo_core
```

- [ ] **Step 2: Create exceptions.py**

Move lines 44-87 from `bingo_core.py` into `bingo_core/exceptions.py`:

```python
"""bingo-light exception hierarchy."""


class BingoError(Exception):
    """Base exception for bingo-light operations."""
    pass
```

Copy the exact content of `BingoError`, `GitError`, `NotGitRepoError`, `NotInitializedError`, `DirtyTreeError` from `bingo_core.py:44-87`.

- [ ] **Step 3: Create models.py**

Move lines 89-119 from `bingo_core.py` into `bingo_core/models.py`:

```python
"""Data classes for bingo-light."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class PatchInfo:
    ...

@dataclass
class ConflictInfo:
    ...
```

Copy exact content of `PatchInfo` and `ConflictInfo` from `bingo_core.py:89-119`.

- [ ] **Step 4: Create __init__.py with constants and re-exports**

```python
"""bingo-light core library."""
import re

VERSION = "2.0.0"
PATCH_PREFIX = "[bl]"
CONFIG_FILE = ".bingolight"
BINGO_DIR = ".bingo"
DEFAULT_TRACKING = "upstream-tracking"
DEFAULT_PATCHES = "bingo-patches"
MAX_PATCHES = 100
MAX_DIFF_SIZE = 50000
PATCH_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
PATCH_NAME_MAX = 100
CIRCUIT_BREAKER_LIMIT = 3
RERERE_MAX_ITER = 50
MAX_RESOLVE_ITER = 20
SYNC_HISTORY_MAX = 50

from bingo_core.exceptions import (  # noqa: E402
    BingoError, GitError, NotGitRepoError, NotInitializedError, DirtyTreeError,
)
from bingo_core.models import PatchInfo, ConflictInfo  # noqa: E402

__all__ = [
    "VERSION", "PATCH_PREFIX", "CONFIG_FILE", "BINGO_DIR",
    "DEFAULT_TRACKING", "DEFAULT_PATCHES", "MAX_PATCHES", "MAX_DIFF_SIZE",
    "PATCH_NAME_RE", "PATCH_NAME_MAX", "CIRCUIT_BREAKER_LIMIT",
    "RERERE_MAX_ITER", "MAX_RESOLVE_ITER", "SYNC_HISTORY_MAX",
    "BingoError", "GitError", "NotGitRepoError", "NotInitializedError",
    "DirtyTreeError", "PatchInfo", "ConflictInfo",
]
```

Note: `Repo`, `Git`, `Config`, `State` will be added to `__init__.py` after Task 4.

- [ ] **Step 5: Verify syntax**

```bash
python3 -c "from bingo_core.exceptions import BingoError, GitError; print('OK')"
python3 -c "from bingo_core.models import PatchInfo, ConflictInfo; print('OK')"
python3 -c "from bingo_core import VERSION, BingoError; print(VERSION)"
```

- [ ] **Step 6: Commit**

```bash
git add bingo_core/
git commit -m "refactor: create bingo_core package — exceptions, models, constants"
```

---

### Task 2: Create bingo_core package — git, config, state modules

**Files:**
- Create: `bingo_core/git.py`
- Create: `bingo_core/config.py`
- Create: `bingo_core/state.py`
- Reference: `bingo_core.py:121-694`

- [ ] **Step 1: Create git.py**

Move `Git` class (lines 121-303) into `bingo_core/git.py`:

```python
"""Git subprocess wrapper."""
import subprocess

from bingo_core.exceptions import GitError


class Git:
    ...
```

Copy exact `Git` class. Adjust import: `GitError` comes from `bingo_core.exceptions`.

- [ ] **Step 2: Create config.py**

Move `Config` class (lines 305-404) into `bingo_core/config.py`:

```python
"""Configuration management (.bingolight file)."""
import os
import subprocess

from bingo_core import CONFIG_FILE
from bingo_core.exceptions import BingoError, NotInitializedError


class Config:
    ...
```

Copy exact `Config` class. Import constants from `bingo_core` package and exceptions from `bingo_core.exceptions`.

- [ ] **Step 3: Create state.py**

Move `State` class (lines 406-694) into `bingo_core/state.py`:

```python
"""State management — metadata, sync history, locks, undo, circuit breaker."""
import json
import os
import subprocess
import time
from datetime import datetime, timezone

from bingo_core import (
    BINGO_DIR, CIRCUIT_BREAKER_LIMIT, SYNC_HISTORY_MAX,
)
from bingo_core.exceptions import BingoError


class State:
    ...
```

Copy exact `State` class. Adjust all constant/exception imports.

- [ ] **Step 4: Verify each module compiles**

```bash
python3 -c "import py_compile; py_compile.compile('bingo_core/git.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/config.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/state.py', doraise=True)"
```

- [ ] **Step 5: Commit**

```bash
git add bingo_core/git.py bingo_core/config.py bingo_core/state.py
git commit -m "refactor: add git, config, state modules to bingo_core package"
```

---

### Task 3: Create bingo_core/repo.py and finalize package

**Files:**
- Create: `bingo_core/repo.py`
- Modify: `bingo_core/__init__.py`
- Delete: `bingo_core.py`
- Reference: `bingo_core.py:696-2874`

- [ ] **Step 1: Create repo.py**

Move `Repo` class (lines 696-2874) into `bingo_core/repo.py`:

```python
"""Core business logic — the Repo class."""
import json
import os
import re
import subprocess
from pathlib import Path

from bingo_core import (
    VERSION, PATCH_PREFIX, CONFIG_FILE, BINGO_DIR,
    DEFAULT_TRACKING, DEFAULT_PATCHES, MAX_PATCHES, MAX_DIFF_SIZE,
    PATCH_NAME_RE, PATCH_NAME_MAX, MAX_RESOLVE_ITER, RERERE_MAX_ITER,
)
from bingo_core.exceptions import (
    BingoError, GitError, NotGitRepoError, NotInitializedError, DirtyTreeError,
)
from bingo_core.models import PatchInfo, ConflictInfo
from bingo_core.git import Git
from bingo_core.config import Config
from bingo_core.state import State


class Repo:
    ...
```

Copy the entire `Repo` class. All internal references to `Git`, `Config`, `State`, constants, exceptions are now imports from sibling modules.

- [ ] **Step 2: Update __init__.py to export Repo, Git, Config, State**

Add to the end of `bingo_core/__init__.py`:

```python
from bingo_core.git import Git  # noqa: E402
from bingo_core.config import Config  # noqa: E402
from bingo_core.state import State  # noqa: E402
from bingo_core.repo import Repo  # noqa: E402

__all__ += ["Git", "Config", "State", "Repo"]
```

- [ ] **Step 3: Verify the package is functionally equivalent**

```bash
python3 -c "from bingo_core import Repo, Git, Config, State, VERSION, BingoError; print('All imports OK, version:', VERSION)"
```

- [ ] **Step 4: Delete old bingo_core.py**

```bash
rm bingo_core.py
```

- [ ] **Step 5: Run full test suite to verify zero breakage**

```bash
python3 tests/test_core.py 2>&1 | tail -5
make test 2>&1 | tail -5
```

Expected: all tests pass (the CLI and tests import `bingo_core` which is now a package, but the public API is identical).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move Repo to bingo_core/repo.py, delete monolithic bingo_core.py"
```

---

### Task 4: Deduplicate conflict handling

**Files:**
- Modify: `bingo_core/repo.py`
- Reference: `_sync_locked()` conflict section, `_smart_sync_locked()` conflict section, `_extract_conflict()`, `conflict_analyze()`

- [ ] **Step 1: Extract _current_rebase_patch() helper**

Add to `Repo` class in `bingo_core/repo.py`, near `_in_rebase()`:

```python
def _current_rebase_patch(self) -> str:
    """Get the commit message of the patch currently being rebased."""
    msg_file = os.path.join(self.path, ".git", "rebase-merge", "message")
    if os.path.isfile(msg_file):
        try:
            with open(msg_file) as f:
                return f.readline().strip()
        except IOError:
            pass
    return ""
```

- [ ] **Step 2: Extract _build_conflict_result() helper**

Add to `Repo` class:

```python
def _build_conflict_result(self, conflicted_files: list,
                           saved_tracking: str = "") -> dict:
    """Build standardized conflict result dict."""
    conflicts = [self._extract_conflict(f) for f in conflicted_files]
    current_patch = self._current_rebase_patch()
    result = {
        "ok": False,
        "conflict": True,
        "current_patch": current_patch,
        "conflicted_files": conflicted_files,
        "conflicts": [c_.to_dict() for c_ in conflicts],
        "resolution_steps": [
            "1. Read ours (upstream) and theirs (your patch) for each conflict",
            "2. Write the merged file content (include both changes where possible)",
            "3. Run: bingo-light conflict-resolve <file> --content-stdin",
            "4. If more conflicts appear, repeat from step 1",
            "5. To abort instead: git rebase --abort",
        ],
        "abort_cmd": "git rebase --abort",
    }
    if saved_tracking:
        result["tracking_restore"] = (
            f"git branch -f upstream-tracking {saved_tracking}"
        )
    return result
```

- [ ] **Step 3: Refactor _sync_locked() to use helpers**

In `_sync_locked()`, replace the conflict dict construction (the block that builds `conflicted_files`, `current_patch`, etc.) with:

```python
# Replace the manual conflict dict construction with:
unmerged = self.git.ls_files_unmerged()
result = self._build_conflict_result(unmerged, saved_tracking)
result["synced"] = False
result["next"] = (
    "Run bingo-light conflict-analyze --json to see conflict details, "
    "then resolve each file"
)
return result
```

- [ ] **Step 4: Refactor _smart_sync_locked() to use helpers**

In `_smart_sync_locked()`, replace the "Real unresolved conflicts" section with:

```python
# Real unresolved conflicts — report and stop
self.git.run_ok("branch", "-f", c["tracking_branch"], saved_tracking)
self.state.record_circuit_breaker(upstream_target)

result = self._build_conflict_result(unresolved, saved_tracking)
result["action"] = "needs_human"
result["behind_before"] = behind
result["conflicts_auto_resolved"] = conflicts_resolved
result["remaining_conflicts"] = result.pop("conflicts")
result["next"] = (
    "For each conflict: read merge_hint, write merged file, "
    "bingo-light conflict-resolve <file> --content-stdin"
)
return result
```

- [ ] **Step 5: Refactor conflict_analyze() to use _current_rebase_patch()**

Replace the manual `msg_file` reading in `conflict_analyze()` with:

```python
current_patch = self._current_rebase_patch()
```

- [ ] **Step 6: Run tests**

```bash
python3 tests/test_core.py 2>&1 | tail -5
make test 2>&1 | tail -5
```

- [ ] **Step 7: Commit**

```bash
git add bingo_core/repo.py
git commit -m "refactor: deduplicate conflict handling with _build_conflict_result()"
```

---

### Task 5: Rewrite MCP server to direct import

**Files:**
- Modify: `mcp-server.py`
- Reference: Current `run_bl()` at line 476, `handle_tool_call()` at line 520

- [ ] **Step 1: Replace run_bl() with direct Repo import**

At the top of `mcp-server.py`, replace the BL variable and run_bl function with:

```python
import sys
import os

# Add parent directory to path so bingo_core package can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bingo_core import Repo, BingoError  # noqa: E402
```

Remove the `BL` variable (line 32) and the entire `run_bl()` function (lines 476-517).

- [ ] **Step 2: Rewrite handle_tool_call() to call Repo methods directly**

Replace each `run_bl()` call with direct method calls. Example pattern:

```python
def handle_tool_call(name: str, arguments: dict) -> dict:
    """Dispatch MCP tool calls to Repo methods."""
    cwd = arguments.get("cwd", "")
    if not cwd or not os.path.isdir(cwd):
        return {"ok": False, "error": f"Invalid cwd: {cwd!r}"}

    try:
        repo = Repo(cwd)

        if name == "bingo_status":
            return repo.status()

        if name == "bingo_init":
            return repo.init(
                arguments.get("upstream_url", ""),
                arguments.get("branch", ""),
            )

        if name == "bingo_sync":
            if arguments.get("dry_run"):
                return repo.sync(dry_run=True)
            return repo.sync(
                force=arguments.get("force", False),
                test_after=arguments.get("test", False),
            )

        if name == "bingo_smart_sync":
            return repo.smart_sync()

        if name == "bingo_undo":
            return repo.undo()

        if name == "bingo_doctor":
            return repo.doctor()

        if name == "bingo_diff":
            return repo.diff()

        if name == "bingo_history":
            return repo.history()

        if name == "bingo_conflict_analyze":
            return repo.conflict_analyze()

        if name == "bingo_conflict_resolve":
            file_path = arguments.get("file", "")
            content = arguments.get("content", "")
            return repo.conflict_resolve(file_path, content)

        if name == "bingo_log":
            return repo.history()

        if name == "bingo_config":
            action = arguments.get("action", "list")
            key = arguments.get("key", "")
            value = arguments.get("value", "")
            if action == "get":
                return repo.config_get(key)
            if action == "set":
                return repo.config_set(key, value)
            return repo.config_list()

        if name == "bingo_test":
            return repo.test()

        if name == "bingo_auto_sync":
            return repo.auto_sync(
                schedule=arguments.get("schedule", ""),
            )

        if name == "bingo_session":
            action = arguments.get("action", "")
            if action == "update":
                return repo.session(update=True)
            return repo.session()

        # Patch commands
        if name == "bingo_patch_new":
            return repo.patch_new(
                arguments.get("name", ""),
                arguments.get("description", ""),
            )
        if name == "bingo_patch_list":
            return repo.patch_list()
        if name == "bingo_patch_show":
            return repo.patch_show(arguments.get("target", ""))
        if name == "bingo_patch_drop":
            return repo.patch_drop(arguments.get("target", ""))
        if name == "bingo_patch_edit":
            return repo.patch_edit(arguments.get("target", ""))
        if name == "bingo_patch_export":
            return repo.patch_export(arguments.get("directory", ""))
        if name == "bingo_patch_import":
            return repo.patch_import(arguments.get("source", ""))
        if name == "bingo_patch_meta":
            return repo.patch_meta(
                arguments.get("target", ""),
                arguments.get("key", ""),
                arguments.get("value", ""),
            )
        if name == "bingo_patch_squash":
            return repo.patch_squash(
                arguments.get("index1", 0),
                arguments.get("index2", 0),
            )
        if name == "bingo_patch_reorder":
            return repo.patch_reorder()

        # Workspace commands
        if name == "bingo_workspace_init":
            return repo.workspace_init()
        if name == "bingo_workspace_add":
            return repo.workspace_add(
                arguments.get("path", ""),
                arguments.get("alias", ""),
            )
        if name == "bingo_workspace_list":
            return repo.workspace_list()
        if name == "bingo_workspace_sync":
            return repo.workspace_sync()
        if name == "bingo_workspace_status":
            return repo.workspace_status()

        return {"ok": False, "error": f"Unknown tool: {name}"}

    except BingoError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Internal error: {e}"}
```

- [ ] **Step 3: Verify MCP server compiles**

```bash
python3 -c "import py_compile; py_compile.compile('mcp-server.py', doraise=True)"
```

- [ ] **Step 4: Run MCP tests**

```bash
python3 tests/test-mcp.py 2>&1 | tail -10
```

- [ ] **Step 5: Run full test suite**

```bash
make test 2>&1 | tail -5
python3 tests/test_core.py 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add mcp-server.py
git commit -m "refactor: MCP server uses direct Repo import instead of subprocess"
```

---

### Task 6: Add conflict-resolve command

**Files:**
- Modify: `bingo_core/repo.py` — add `conflict_resolve()` method
- Modify: `bingo-light` — add argparse, dispatch, formatter
- Modify: `mcp-server.py` — update handle_tool_call (already has bingo_conflict_resolve)

- [ ] **Step 1: Add conflict_resolve() to Repo class**

In `bingo_core/repo.py`, add after `conflict_analyze()`:

```python
def conflict_resolve(self, file_path: str, content: str = "") -> dict:
    """Resolve a single conflicted file and continue rebase if possible.

    If content is provided, write it to the file. Then stage the file.
    If no more unmerged files remain, continue the rebase.

    Returns dict describing next state: more conflicts, new patch
    conflicts, or sync complete.
    """
    self._load()

    if not self._in_rebase():
        raise BingoError("No rebase in progress. Nothing to resolve.")

    # Validate file path
    resolved = Path(file_path)
    try:
        resolved = (Path(self.path) / resolved).resolve()
        resolved.relative_to(Path(self.path).resolve())
    except (ValueError, OSError):
        raise BingoError(f"Invalid file path: {file_path}")

    rel_path = str(resolved.relative_to(Path(self.path).resolve()))

    # Check file is actually unmerged
    unmerged = self.git.ls_files_unmerged()
    if rel_path not in unmerged:
        raise BingoError(
            f"File '{rel_path}' is not in conflict. "
            f"Conflicted files: {', '.join(unmerged) if unmerged else 'none'}"
        )

    # Write content if provided
    if content:
        with open(str(resolved), "w") as f:
            f.write(content)

    # Stage the file
    self.git.run("add", rel_path)

    # Check remaining unmerged files
    remaining = self.git.ls_files_unmerged()
    if remaining:
        # More files to resolve in current patch
        conflicts = [self._extract_conflict(f) for f in remaining]
        return {
            "ok": True,
            "resolved": rel_path,
            "remaining": remaining,
            "conflicts": [c.to_dict() for c in conflicts],
        }

    # All files resolved — continue rebase
    env = os.environ.copy()
    env["GIT_EDITOR"] = "true"
    cont = subprocess.run(
        ["git", "rebase", "--continue"],
        cwd=self.path,
        capture_output=True,
        text=True,
        env=env,
    )

    if cont.returncode != 0:
        # rebase --continue may trigger new conflicts on next patch
        new_unmerged = self.git.ls_files_unmerged()
        if new_unmerged:
            result = self._build_conflict_result(new_unmerged)
            result["resolved"] = rel_path
            result["rebase_continued"] = True
            return result
        # Unknown rebase error
        raise BingoError(
            f"Rebase continue failed: {cont.stderr.strip()}"
        )

    # Rebase complete
    return {
        "ok": True,
        "resolved": rel_path,
        "rebase_continued": True,
        "sync_complete": True,
    }
```

- [ ] **Step 2: Add argparse entry for conflict-resolve**

In `bingo-light`, in `build_parser()`, after the `conflict-analyze` subparser add:

```python
cr = sub.add_parser("conflict-resolve", add_help=False)
cr.add_argument("resolve_file", nargs="?", default="")
cr.add_argument("--content-stdin", action="store_true")
```

- [ ] **Step 3: Add dispatch for conflict-resolve**

In `dispatch()`, add:

```python
if cmd == "conflict-resolve":
    content = ""
    if args.content_stdin:
        import sys as _sys
        content = _sys.stdin.read()
    return repo.conflict_resolve(args.resolve_file, content)
```

- [ ] **Step 4: Add formatter**

In `bingo-light`, add before `_format_generic`:

```python
def _format_conflict_resolve(result: dict) -> str:
    """Format conflict-resolve result."""
    if result.get("ok") is False:
        return f"{_c(RED, 'x')} {result.get('error', 'Failed.')}"
    resolved = result.get("resolved", "")
    remaining = result.get("remaining", [])
    if remaining:
        lines = [f"{_c(GREEN, 'OK')} Resolved {resolved}"]
        lines.append(f"  {len(remaining)} file(s) still in conflict:")
        for f in remaining:
            lines.append(f"  {_c(YELLOW, '~')} {f}")
        return "\n".join(lines)
    if result.get("sync_complete"):
        return f"{_c(GREEN, 'OK')} Resolved {resolved} — sync complete!"
    if result.get("conflict"):
        files = result.get("conflicted_files", [])
        patch = result.get("current_patch", "")
        lines = [f"{_c(GREEN, 'OK')} Resolved {resolved} — next patch has conflicts:"]
        if patch:
            lines.append(f"  Patch: {patch}")
        for f in files:
            lines.append(f"  {_c(YELLOW, '~')} {f}")
        return "\n".join(lines)
    return f"{_c(GREEN, 'OK')} Resolved {resolved}"
```

Add to `_FORMATTERS`:
```python
"conflict-resolve": _format_conflict_resolve,
```

- [ ] **Step 5: Add to help text**

In the help string in `build_parser()`, under "Sync with Upstream", add:

```
    conflict-resolve <file>         Resolve a conflict file and continue
```

- [ ] **Step 6: Verify syntax**

```bash
python3 -c "import py_compile; py_compile.compile('bingo_core/repo.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo-light', doraise=True)"
```

- [ ] **Step 7: Run tests**

```bash
make test 2>&1 | tail -5
python3 tests/test_core.py 2>&1 | tail -5
```

- [ ] **Step 8: Commit**

```bash
git add bingo_core/repo.py bingo-light
git commit -m "feat: add conflict-resolve command for AI-native conflict resolution"
```

---

### Task 7: Add workspace remove command

**Files:**
- Modify: `bingo_core/repo.py` — add `workspace_remove()`
- Modify: `bingo-light` — add argparse, dispatch

- [ ] **Step 1: Add workspace_remove() to Repo**

In `bingo_core/repo.py`, after `workspace_status()`:

```python
def workspace_remove(self, target: str) -> dict:
    """Remove a repo from the workspace by alias or path."""
    workspace_config = self._workspace_config_path()
    if not os.path.isfile(workspace_config):
        raise BingoError("No workspace. Run 'bingo-light workspace init'.")

    data = self._load_workspace(workspace_config)
    repos = data.get("repos", [])
    original_count = len(repos)
    repos = [
        r for r in repos
        if r.get("alias") != target and r.get("path") != target
    ]
    if len(repos) == original_count:
        raise BingoError(f"Repo '{target}' not found in workspace.")

    data["repos"] = repos
    import json as _json
    with open(workspace_config, "w") as f:
        _json.dump(data, f, indent=2)

    return {"ok": True, "removed": target}
```

- [ ] **Step 2: Add argparse and dispatch**

In `build_parser()`, in the workspace subparsers, add:

```python
ws_rm = ws_sub.add_parser("remove")
ws_rm.add_argument("ws_target")
```

In `_dispatch_workspace()`, add:

```python
if wcmd == "remove":
    return repo.workspace_remove(args.ws_target)
```

- [ ] **Step 3: Add to help text**

In help string, workspace section:
```
    workspace remove <alias|path>   Remove a repo from workspace
```

- [ ] **Step 4: Verify and test**

```bash
python3 -c "import py_compile; py_compile.compile('bingo_core/repo.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo-light', doraise=True)"
make test 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add bingo_core/repo.py bingo-light
git commit -m "feat: add workspace remove command"
```

---

### Task 8: Differentiate log vs history formatters

**Files:**
- Modify: `bingo-light` — split `_format_history` into `_format_log` (compact) and `_format_history` (verbose)

- [ ] **Step 1: Create _format_log (compact)**

Rename existing `_format_history` to `_format_log` (it already shows compact format):

```python
def _format_log(result: dict) -> str:
    """Format log result — compact one-line-per-sync."""
    syncs = result.get("syncs", result.get("history", result.get("entries", [])))
    if not syncs:
        return "No sync history."
    lines = []
    for e in syncs:
        ts = e.get("timestamp", "")
        n = e.get("upstream_commits_integrated", 0)
        patches = e.get("patches", [])
        before = e.get("upstream_before", "")[:7]
        after = e.get("upstream_after", "")[:7]
        summary = f"{n} commit(s) integrated"
        if before and after:
            summary += f"  {before} \u2192 {after}"
        if patches:
            summary += f"  ({len(patches)} patch(es) rebased)"
        lines.append(f"  {_c(DIM, ts)}  {summary}")
    return "\n".join(lines)
```

- [ ] **Step 2: Create _format_history (verbose)**

```python
def _format_history(result: dict) -> str:
    """Format history result — verbose with per-patch hash mappings."""
    syncs = result.get("syncs", [])
    if not syncs:
        return "No sync history."
    lines = []
    for e in syncs:
        ts = e.get("timestamp", "")
        n = e.get("upstream_commits_integrated", 0)
        before = e.get("upstream_before", "")[:7]
        after = e.get("upstream_after", "")[:7]
        patches = e.get("patches", [])
        lines.append(f"  {_c(BOLD, 'Sync')} @ {ts}")
        lines.append(f"    Upstream: {before} \u2192 {after} ({n} commit(s))")
        if patches:
            lines.append(f"    Patches rebased:")
            for p in patches:
                name = p.get("name", "?")
                h = p.get("hash", "?")[:7]
                lines.append(f"      {name}  {_c(DIM, h)}")
        lines.append("")
    return "\n".join(lines).rstrip()
```

- [ ] **Step 3: Update _FORMATTERS dict**

```python
"log": _format_log,
"history": _format_history,
```

- [ ] **Step 4: Verify and test**

```bash
python3 -c "import py_compile; py_compile.compile('bingo-light', doraise=True)"
make test 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add bingo-light
git commit -m "fix: differentiate log (compact) vs history (verbose with patch hashes)"
```

---

### Task 9: Fix patch meta tags single-key repr

**Files:**
- Modify: `bingo-light` — fix `_format_patch_meta` get-single-key branch

- [ ] **Step 1: Fix the formatter**

In `_format_patch_meta`, replace the get-single-key branch at the bottom:

```python
# Get single key
k = result.get("key", "")
v = result.get("value", "")
if isinstance(v, list):
    v = ", ".join(v) if v else "(none)"
elif v is None or v == "":
    v = "(not set)"
return f"  {k}: {v}"
```

- [ ] **Step 2: Verify**

```bash
python3 -c "import py_compile; py_compile.compile('bingo-light', doraise=True)"
```

- [ ] **Step 3: Commit**

```bash
git add bingo-light
git commit -m "fix: patch meta tags single-key query shows comma-separated instead of Python repr"
```

---

### Task 10: Update shell completions

**Files:**
- Modify: `completions/bingo-light.bash`
- Modify: `completions/bingo-light.zsh`
- Modify: `completions/bingo-light.fish`

- [ ] **Step 1: Update bash completions**

Add `conflict-resolve` to the top-level commands list. Add `remove` to workspace subcommands. Verify `smart-sync`, `history`, `session` are present (they already are per the exploration).

In `completions/bingo-light.bash`, find the main commands string and add `conflict-resolve`. Find the workspace subcommands and add `remove`.

- [ ] **Step 2: Update zsh completions**

Same changes: add `conflict-resolve` to commands, `remove` to workspace subcommands.

- [ ] **Step 3: Update fish completions**

Same changes: add `conflict-resolve` completion with description, `remove` to workspace subcommands.

- [ ] **Step 4: Verify completions parse**

```bash
bash -n completions/bingo-light.bash && echo "bash OK"
zsh -n completions/bingo-light.zsh 2>&1 || true
fish -n completions/bingo-light.fish 2>&1 || true
```

- [ ] **Step 5: Commit**

```bash
git add completions/
git commit -m "feat: add conflict-resolve and workspace remove to shell completions"
```

---

### Task 11: Add tests for new and existing features

**Files:**
- Modify: `tests/test_core.py`
- Modify: `tests/test.sh`

- [ ] **Step 1: Add unit tests to test_core.py**

Add to `TestState` class:

```python
def test_patch_meta_tags_comma(self):
    """Comma-separated tags stored individually."""
    state = State(self.fork_path)
    state._ensure_dir()
    state.patch_meta_set("p1", "tags", "a,b,c")
    meta = state.patch_meta_get("p1")
    self.assertEqual(meta["tags"], ["a", "b", "c"])

def test_patch_meta_tags_plural_key(self):
    """'tags' key works same as 'tag'."""
    state = State(self.fork_path)
    state._ensure_dir()
    state.patch_meta_set("p1", "tags", "x")
    state.patch_meta_set("p1", "tag", "y")
    meta = state.patch_meta_get("p1")
    self.assertEqual(sorted(meta["tags"]), ["x", "y"])

def test_patch_meta_tags_dedup(self):
    """Duplicate tags not added."""
    state = State(self.fork_path)
    state._ensure_dir()
    state.patch_meta_set("p1", "tags", "a,b")
    state.patch_meta_set("p1", "tags", "b,c")
    meta = state.patch_meta_get("p1")
    self.assertEqual(meta["tags"], ["a", "b", "c"])
```

Add to `TestRepo` class:

```python
def test_reinit_detection(self):
    """Re-init returns reinit flag."""
    repo = Repo(self.fork_path)
    r1 = repo.init(self.upstream_path, "main")
    self.assertTrue(r1["ok"])
    self.assertNotIn("reinit", r1)
    r2 = repo.init(self.upstream_path, "main")
    self.assertTrue(r2["ok"])
    self.assertTrue(r2.get("reinit"))

def test_conflict_resolve_no_rebase(self):
    """conflict_resolve raises when no rebase in progress."""
    repo = Repo(self.fork_path)
    repo.init(self.upstream_path, "main")
    with self.assertRaises(BingoError):
        repo.conflict_resolve("app.py", "content")

def test_workspace_remove(self):
    """workspace remove deletes entry."""
    repo = Repo(self.fork_path)
    repo.workspace_init()
    repo.workspace_add(self.fork_path, "test-fork")
    result = repo.workspace_remove("test-fork")
    self.assertTrue(result["ok"])
    self.assertEqual(result["removed"], "test-fork")
    ws = repo.workspace_list()
    self.assertEqual(len(ws["repos"]), 0)

def test_workspace_remove_not_found(self):
    """workspace remove raises for nonexistent alias."""
    repo = Repo(self.fork_path)
    repo.workspace_init()
    with self.assertRaises(BingoError):
        repo.workspace_remove("nope")

def test_workspace_status(self):
    """workspace status returns per-repo details."""
    repo = Repo(self.fork_path)
    repo.init(self.upstream_path, "main")
    repo.workspace_init()
    repo.workspace_add(self.fork_path, "test-fork")
    result = repo.workspace_status()
    self.assertTrue(result["ok"])
    self.assertEqual(len(result["repos"]), 1)
    r = result["repos"][0]
    self.assertEqual(r["alias"], "test-fork")
    self.assertIn("behind", r)
    self.assertIn("patches", r)
```

- [ ] **Step 2: Add conflict-resolve integration test to test.sh**

Add a new section after the Conflict Flow section (section 18):

```bash
section "20. Conflict Resolve"

# Setup: create conflict
cd "$FORK"
make_upstream_change "conflict trigger"
echo 'conflicting line from fork' > "$FORK/conflict-file.txt"
git add conflict-file.txt
BINGO_DESCRIPTION="fork change" $BL patch new cr-test --yes >/dev/null 2>&1
$BL sync --yes 2>&1 || true

# Test: resolve via CLI
echo 'merged content' | $BL conflict-resolve conflict-file.txt --content-stdin --yes --json > /tmp/bl-cr.json 2>&1
check "conflict-resolve --json has ok" "jq -e '.ok' /tmp/bl-cr.json"
```

- [ ] **Step 3: Handle fuzz_mcp.py**

```bash
# If it's useful, track it; if not, remove it
git add fuzz_mcp.py  # or: rm fuzz_mcp.py
```

Decide based on content: if it's a valid fuzzer, add it. Read it first.

- [ ] **Step 4: Run all tests**

```bash
python3 tests/test_core.py 2>&1 | tail -5
make test 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_core.py tests/test.sh
git commit -m "test: add tests for conflict-resolve, workspace remove/status, tags, reinit"
```

---

### Task 12: Update CLAUDE.md and verify CI lint

**Files:**
- Modify: `CLAUDE.md`
- Check: `.github/workflows/ci.yml`

- [ ] **Step 1: Update CLAUDE.md command checklist**

In `CLAUDE.md`, update the "When adding a new command" section (lines 86-93):

```markdown
## When adding a new command

1. `bingo_core/repo.py` — add method to `Repo` class, return dict with `ok` key
2. `bingo-light` — add argparse + dispatch + **dedicated formatter** (not _format_generic)
3. `completions/*.bash`, `.zsh`, `.fish` — add to ALL three completion files
4. `llms.txt` — add to command reference
5. `README.md` + `README.zh-CN.md` — add to Command Reference
6. Tests — add to `test.sh` or `test_core.py`
```

Note: item 1 changed from `bingo_core.py` to `bingo_core/repo.py`. Item 2 emphasizes dedicated formatter. Item 3 emphasizes ALL three.

Also update the "Architecture" section to reflect the package structure:

```markdown
**bingo_core/** (Python 3 package) — Core library. Split into: `exceptions.py` (error hierarchy), `models.py` (PatchInfo, ConflictInfo), `git.py` (Git subprocess wrapper), `config.py` (.bingolight reader), `state.py` (metadata, locks, undo), `repo.py` (all business logic). Config stored in `.bingolight` via `git config --file`. Uses `.bingo/.lock` for concurrency protection.
```

- [ ] **Step 2: Verify CI has lint job**

Read `.github/workflows/ci.yml` and confirm the `lint` job exists (it does per exploration — lines 58-79). If it runs `make lint`, no changes needed.

- [ ] **Step 3: Run make lint locally to verify**

```bash
make lint 2>&1 | tail -10
```

Fix any issues found.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for package structure and formatter requirement"
```

---

### Task 13: Final verification and push

- [ ] **Step 1: Full test suite**

```bash
python3 tests/test_core.py
make test
python3 tests/test-mcp.py
```

All must pass.

- [ ] **Step 2: Syntax check all Python files**

```bash
python3 -c "import py_compile; py_compile.compile('bingo-light', doraise=True)"
python3 -c "import py_compile; py_compile.compile('mcp-server.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/__init__.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/repo.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/git.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/config.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/state.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/exceptions.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('bingo_core/models.py', doraise=True)"
```

- [ ] **Step 3: Lint check**

```bash
make lint
```

- [ ] **Step 4: Manual smoke test**

```bash
cd /tmp && rm -rf smoke-up smoke-fk
mkdir smoke-up && cd smoke-up && git init -b main && git config user.email "t@t" && git config user.name "T"
echo 'v1' > app.py && git add -A && git commit -m "v1"
cd /tmp && git clone smoke-up smoke-fk && cd smoke-fk && git config user.email "t@t" && git config user.name "T"
BL=/home/kali/bingo-light/bingo-light
$BL init /tmp/smoke-up --yes
# test conflict-resolve
sed -i 's/v1/v1-custom/' app.py
BINGO_DESCRIPTION="custom" $BL patch new my-patch --yes
cd /tmp/smoke-up && echo 'v2' > app.py && git add -A && git commit -m "v2"
cd /tmp/smoke-fk && $BL sync --yes 2>&1 || true
echo 'v2-merged' | $BL conflict-resolve app.py --content-stdin --yes --json
# test workspace remove
$BL workspace init --yes && $BL workspace add /tmp/smoke-fk --yes
$BL workspace status --json
$BL workspace remove smoke-fk --yes
# test log vs history
$BL log && $BL history
rm -rf /tmp/smoke-up /tmp/smoke-fk
```

- [ ] **Step 5: Push**

```bash
git push
```

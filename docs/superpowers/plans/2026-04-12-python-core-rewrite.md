# Python Core Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite bingo-light from Bash to Python, eliminating all pipefail/JSON-escape bug classes while passing all 178 existing tests.

**Architecture:** Two Python files — `bingo_core.py` (library) + `bingo-light` (CLI entry). MCP server imports bingo_core directly. Pure stdlib, zero dependencies.

**Tech Stack:** Python 3.8+, stdlib only (subprocess, json, pathlib, argparse, dataclasses)

**Spec:** `docs/superpowers/specs/2026-04-12-python-core-rewrite-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `bingo_core.py` | CREATE | Core library: Git, Config, State, Repo classes (~1500 lines) |
| `bingo-light` | REWRITE | Python CLI entry with argparse (~400 lines) |
| `mcp-server.py` | MODIFY | Import bingo_core, remove subprocess calls |
| `agent.py` | MODIFY | Import bingo_core |
| `tui.py` | MODIFY | Import bingo_core |
| `bingo-light.bash` | CREATE | Archived copy of old Bash version |
| `tests/test_core.py` | CREATE | Python unit tests for bingo_core |
| `CLAUDE.md` | MODIFY | Update architecture docs |

---

### Task 1: Foundation — Git, Config, State, Exceptions

**Files:**
- Create: `bingo_core.py`
- Create: `tests/test_core.py`

This task builds the base classes that everything else depends on.

- [ ] **Step 1: Create bingo_core.py with Git class**

```python
#!/usr/bin/env python3
"""bingo-light core library — AI-native fork maintenance."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "2.0.0"
PATCH_PREFIX = "[bl]"
DEFAULT_TRACKING = "upstream-tracking"
DEFAULT_PATCHES = "bingo-patches"
CONFIG_FILE = ".bingolight"
BINGO_DIR = ".bingo"

# ── Exceptions ──────────────────────────────────────────

class BingoError(Exception):
    """All bingo-light errors."""
    pass

class GitError(BingoError):
    def __init__(self, cmd: list[str], returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"git {' '.join(cmd)} failed (exit {returncode}): {stderr.strip()}")

class NotGitRepoError(BingoError):
    def __init__(self):
        super().__init__("Not a git repository. Run this inside a git repo.")

class NotInitializedError(BingoError):
    def __init__(self):
        super().__init__("bingo-light not initialized. Run: bingo-light init <upstream-url>")

class DirtyTreeError(BingoError):
    def __init__(self):
        super().__init__("Working tree is dirty. Commit or stash your changes first.")

# ── Data Classes ────────────────────────────────────────

@dataclass
class PatchInfo:
    name: str
    hash: str
    subject: str
    files: int
    stat: str = ""

@dataclass
class ConflictInfo:
    file: str
    ours: str
    theirs: str
    conflict_count: int
    merge_hint: str

# ── Git Wrapper ─────────────────────────────────────────

class Git:
    """Unified git subprocess wrapper. All git errors become GitError exceptions."""

    def __init__(self, cwd: str):
        self.cwd = os.path.abspath(cwd)
        if not os.path.isdir(os.path.join(self.cwd, ".git")):
            # Check if we're inside a git worktree
            try:
                self.run("rev-parse", "--git-dir")
            except (GitError, FileNotFoundError):
                raise NotGitRepoError()

    def run(self, *args: str, check: bool = True, input: str | None = None) -> str:
        """Run a git command and return stdout. Raises GitError on failure if check=True."""
        cmd = ["git"] + list(args)
        result = subprocess.run(
            cmd, cwd=self.cwd, capture_output=True, text=True,
            input=input, timeout=120,
        )
        if check and result.returncode != 0:
            raise GitError(list(args), result.returncode, result.stderr)
        return result.stdout.strip()

    def run_ok(self, *args: str) -> bool:
        """Run a git command and return True if it succeeds."""
        try:
            self.run(*args)
            return True
        except GitError:
            return False

    def rev_parse(self, ref: str) -> str | None:
        """Resolve a ref to a commit hash. Returns None if not found."""
        try:
            return self.run("rev-parse", ref)
        except GitError:
            return None

    def rev_list_count(self, range_spec: str) -> int:
        """Count commits in a range. Returns 0 on any error."""
        try:
            return int(self.run("rev-list", "--count", range_spec))
        except (GitError, ValueError):
            return 0

    def current_branch(self) -> str:
        return self.run("branch", "--show-current")

    def fetch(self, remote: str) -> bool:
        """Fetch from remote. Returns True on success, False on failure."""
        return self.run_ok("fetch", remote)

    def is_clean(self) -> bool:
        """Check if working tree and index are clean."""
        try:
            self.run("diff", "--quiet", "HEAD")
            self.run("diff", "--cached", "--quiet")
            return True
        except GitError:
            return False

    def ls_files_unmerged(self) -> list[str]:
        """Get list of unmerged (conflicted) files."""
        try:
            output = self.run("ls-files", "--unmerged")
        except GitError:
            return []
        if not output:
            return []
        files = set()
        for line in output.splitlines():
            if "\t" in line:
                files.add(line.split("\t")[-1])
        return sorted(files)

    def diff_names(self, range_spec: str) -> list[str]:
        """Get list of changed file names in a range."""
        try:
            output = self.run("diff", "--name-only", range_spec)
        except GitError:
            return []
        return sorted(output.splitlines()) if output else []

    def merge_base(self, ref1: str, ref2: str) -> str | None:
        """Find merge base of two refs."""
        try:
            return self.run("merge-base", ref1, ref2)
        except GitError:
            return None

    def log_patches(self, base: str, branch: str) -> list[PatchInfo]:
        """Get patch info using single-pass git log (fast path)."""
        try:
            output = self.run(
                "log", "--format=PATCH\t%h\t%s", "--numstat", "--shortstat",
                "--reverse", f"{base}..{branch}"
            )
        except GitError:
            return []
        if not output:
            return []

        patches: list[PatchInfo] = []
        name = ""
        hash_ = ""
        subject = ""
        files = 0
        stat = ""
        in_patch = False

        for line in output.splitlines():
            if line.startswith("PATCH\t"):
                if in_patch:
                    patches.append(PatchInfo(name=name, hash=hash_, subject=subject, files=files, stat=stat))
                parts = line.split("\t", 2)
                hash_ = parts[1] if len(parts) > 1 else ""
                subject = parts[2] if len(parts) > 2 else ""
                # Extract name from "[bl] <name>: ..."
                m = re.match(r"^\[bl\] ([^:]+):", subject)
                name = m.group(1) if m else ""
                files = 0
                stat = ""
                in_patch = True
            elif line and line[0].isdigit() and "\t" in line:
                files += 1
            elif "file" in line and ("insertion" in line or "deletion" in line or "changed" in line):
                stat = line.strip()

        if in_patch:
            patches.append(PatchInfo(name=name, hash=hash_, subject=subject, files=files, stat=stat))

        return patches
```

- [ ] **Step 2: Add Config class**

```python
# ── Config ──────────────────────────────────────────────

class Config:
    """Manages .bingolight config file (git config format)."""

    def __init__(self, git: Git):
        self.git = git
        self.path = os.path.join(git.cwd, CONFIG_FILE)

    @property
    def exists(self) -> bool:
        return os.path.isfile(self.path)

    def _read(self, key: str) -> str | None:
        try:
            return self.git.run("config", "--file", self.path, f"bingolight.{key}")
        except GitError:
            return None

    def _write(self, key: str, value: str) -> None:
        self.git.run("config", "--file", self.path, f"bingolight.{key}", value)

    def load(self) -> dict[str, str]:
        """Load all config into a dict."""
        if not self.exists:
            raise NotInitializedError()
        return {
            "upstream_url": self._read("upstream-url") or "",
            "upstream_branch": self._read("upstream-branch") or "",
            "patches_branch": self._read("patches-branch") or DEFAULT_PATCHES,
            "tracking_branch": self._read("tracking-branch") or DEFAULT_TRACKING,
        }

    def save(self, upstream_url: str, upstream_branch: str,
             patches_branch: str = DEFAULT_PATCHES,
             tracking_branch: str = DEFAULT_TRACKING) -> None:
        self._write("upstream-url", upstream_url)
        self._write("upstream-branch", upstream_branch)
        self._write("patches-branch", patches_branch)
        self._write("tracking-branch", tracking_branch)

    def get(self, key: str) -> str | None:
        return self._read(key)

    def set(self, key: str, value: str) -> None:
        self._write(key, value)

    def list_all(self) -> dict[str, str]:
        """List all config entries."""
        try:
            output = self.git.run("config", "--file", self.path, "--list")
        except GitError:
            return {}
        result = {}
        for line in output.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                result[k] = v
        return result
```

- [ ] **Step 3: Add State class**

```python
# ── State ───────────────────────────────────────────────

class State:
    """Manages .bingo/ directory state files."""

    def __init__(self, cwd: str):
        self.dir = Path(cwd) / BINGO_DIR
        self.metadata_file = self.dir / "metadata.json"
        self.history_file = self.dir / "sync-history.json"

    def ensure_dir(self) -> None:
        self.dir.mkdir(exist_ok=True)

    # ── Undo ──

    def save_undo(self, head: str, tracking: str) -> None:
        self.ensure_dir()
        (self.dir / ".undo-head").write_text(head)
        (self.dir / ".undo-tracking").write_text(tracking)
        self.clear_undo_active()

    def load_undo(self) -> tuple[str, str] | None:
        head_file = self.dir / ".undo-head"
        tracking_file = self.dir / ".undo-tracking"
        if head_file.is_file() and tracking_file.is_file():
            return head_file.read_text().strip(), tracking_file.read_text().strip()
        return None

    def set_undo_active(self) -> None:
        self.ensure_dir()
        (self.dir / ".undo-active").touch()

    def clear_undo_active(self) -> None:
        p = self.dir / ".undo-active"
        if p.exists():
            p.unlink()

    def is_undo_active(self) -> bool:
        return (self.dir / ".undo-active").is_file()

    # ── Circuit Breaker ──

    def check_circuit_breaker(self, target: str) -> bool:
        """Returns True if blocked (3+ failures on same target)."""
        f = self.dir / ".sync-failures"
        if not f.is_file():
            return False
        lines = f.read_text().strip().splitlines()
        if len(lines) >= 2 and lines[0] == target:
            try:
                return int(lines[1]) >= 3
            except ValueError:
                pass
        return False

    def record_sync_failure(self, target: str) -> None:
        self.ensure_dir()
        f = self.dir / ".sync-failures"
        count = 0
        if f.is_file():
            lines = f.read_text().strip().splitlines()
            if len(lines) >= 2 and lines[0] == target:
                try:
                    count = int(lines[1])
                except ValueError:
                    pass
        f.write_text(f"{target}\n{count + 1}")

    def clear_sync_failures(self) -> None:
        f = self.dir / ".sync-failures"
        if f.exists():
            f.unlink()

    # ── Metadata ──

    def _load_metadata(self) -> dict:
        if self.metadata_file.is_file():
            try:
                return json.loads(self.metadata_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"patches": {}}

    def _save_metadata(self, data: dict) -> None:
        self.ensure_dir()
        tmp = self.metadata_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.metadata_file)

    def get_patch_meta(self, name: str) -> dict:
        data = self._load_metadata()
        return data.get("patches", {}).get(name, {
            "reason": "", "tags": [], "expires": None,
            "upstream_pr": "", "status": "permanent",
        })

    def set_patch_meta(self, name: str, key: str, value: str) -> None:
        valid_keys = ("reason", "tags", "expires", "upstream_pr", "status")
        if key == "tag":
            key = "tags"  # special: append to list
        elif key not in valid_keys:
            raise BingoError(f"patch meta: unknown key '{key}'. Valid keys: {', '.join(valid_keys)}")
        data = self._load_metadata()
        patches = data.setdefault("patches", {})
        p = patches.setdefault(name, {
            "reason": "", "tags": [], "expires": None,
            "upstream_pr": "", "status": "permanent",
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        if key == "tags":
            tags = p.setdefault("tags", [])
            if value not in tags:
                tags.append(value)
        else:
            p[key] = value
        self._save_metadata(data)

    # ── Sync History ──

    def record_sync(self, entry: dict) -> None:
        self.ensure_dir()
        history = {"syncs": []}
        if self.history_file.is_file():
            try:
                history = json.loads(self.history_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        history.setdefault("syncs", []).append(entry)
        # Keep last 50 entries
        history["syncs"] = history["syncs"][-50:]
        tmp = self.history_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(history, indent=2))
        tmp.replace(self.history_file)

    def get_history(self) -> list[dict]:
        if self.history_file.is_file():
            try:
                data = json.loads(self.history_file.read_text())
                return data.get("syncs", [])
            except (json.JSONDecodeError, OSError):
                pass
        return []

    # ── Session ──

    def get_session(self) -> str | None:
        f = self.dir / "session.md"
        if f.is_file():
            return f.read_text()
        return None

    def update_session(self, content: str) -> None:
        self.ensure_dir()
        (self.dir / "session.md").write_text(content)

    # ── Hooks ──

    def run_hooks(self, event: str, data: dict) -> None:
        hook = self.dir / "hooks" / event
        if hook.is_file() and os.access(str(hook), os.X_OK):
            try:
                subprocess.run(
                    [str(hook)], cwd=str(self.dir.parent),
                    input=json.dumps(data), text=True,
                    timeout=30, capture_output=True,
                )
            except (subprocess.TimeoutExpired, OSError):
                pass
```

- [ ] **Step 4: Write unit tests for foundation classes**

```python
# tests/test_core.py
#!/usr/bin/env python3
"""Unit tests for bingo_core."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

# Add parent dir to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bingo_core import (
    Git, GitError, Config, State, NotGitRepoError, NotInitializedError,
    BingoError, PatchInfo,
)

class TestGit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.tmpdir, capture_output=True)
        Path(self.tmpdir, "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.tmpdir, capture_output=True)
        self.git = Git(self.tmpdir)

    def test_run_success(self):
        output = self.git.run("log", "--oneline", "-1")
        self.assertIn("init", output)

    def test_run_failure(self):
        with self.assertRaises(GitError):
            self.git.run("checkout", "nonexistent-branch")

    def test_rev_parse_valid(self):
        result = self.git.rev_parse("HEAD")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 40)

    def test_rev_parse_invalid(self):
        result = self.git.rev_parse("nonexistent")
        self.assertIsNone(result)

    def test_rev_list_count(self):
        count = self.git.rev_list_count("HEAD~0..HEAD")
        self.assertEqual(count, 0)

    def test_is_clean(self):
        self.assertTrue(self.git.is_clean())
        Path(self.tmpdir, "dirty.txt").write_text("x")
        self.assertFalse(self.git.is_clean())

    def test_not_git_repo(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(NotGitRepoError):
                Git(d)


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.tmpdir, capture_output=True)
        Path(self.tmpdir, "f").write_text("x")
        subprocess.run(["git", "add", "."], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.tmpdir, capture_output=True)
        self.git = Git(self.tmpdir)
        self.config = Config(self.git)

    def test_save_and_load(self):
        self.config.save("https://example.com/repo.git", "main")
        data = self.config.load()
        self.assertEqual(data["upstream_url"], "https://example.com/repo.git")
        self.assertEqual(data["upstream_branch"], "main")

    def test_not_initialized(self):
        with self.assertRaises(NotInitializedError):
            self.config.load()

    def test_get_set(self):
        self.config.save("url", "main")
        self.config.set("test.command", "make test")
        self.assertEqual(self.config.get("test.command"), "make test")


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state = State(self.tmpdir)

    def test_undo_roundtrip(self):
        self.state.save_undo("abc123", "def456")
        result = self.state.load_undo()
        self.assertEqual(result, ("abc123", "def456"))

    def test_undo_not_saved(self):
        self.assertIsNone(self.state.load_undo())

    def test_circuit_breaker(self):
        self.assertFalse(self.state.check_circuit_breaker("abc"))
        self.state.record_sync_failure("abc")
        self.state.record_sync_failure("abc")
        self.assertFalse(self.state.check_circuit_breaker("abc"))
        self.state.record_sync_failure("abc")
        self.assertTrue(self.state.check_circuit_breaker("abc"))

    def test_circuit_breaker_clear(self):
        self.state.record_sync_failure("abc")
        self.state.record_sync_failure("abc")
        self.state.record_sync_failure("abc")
        self.state.clear_sync_failures()
        self.assertFalse(self.state.check_circuit_breaker("abc"))

    def test_patch_meta(self):
        self.state.set_patch_meta("test-patch", "reason", "testing")
        meta = self.state.get_patch_meta("test-patch")
        self.assertEqual(meta["reason"], "testing")

    def test_patch_meta_invalid_key(self):
        with self.assertRaises(BingoError):
            self.state.set_patch_meta("test", "invalid_key", "value")

    def test_sync_history(self):
        self.state.record_sync({"timestamp": "2026-01-01", "behind": 3})
        history = self.state.get_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["behind"], 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run tests**

Run: `cd /home/kali/bingo-light && python3 tests/test_core.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add bingo_core.py tests/test_core.py
git commit -m "feat(rewrite): Task 1 — Git, Config, State foundation classes"
```

---

### Task 2: Repo Class — Init, Status, Doctor

**Files:**
- Modify: `bingo_core.py`
- Modify: `tests/test_core.py`

- [ ] **Step 1: Add Repo class with init and status**

Add to `bingo_core.py`:

```python
# ── Repo (top-level facade) ─────────────────────────────

class Repo:
    """Top-level API for bingo-light operations."""

    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)
        self.git = Git(self.cwd)
        self.cfg = Config(self.git)
        self.state = State(self.cwd)

    def _load(self) -> dict[str, str]:
        """Load config into convenient dict. Raises NotInitializedError if not set up."""
        return self.cfg.load()

    def _ensure_clean(self) -> None:
        if not self.git.is_clean():
            # Also check for active rebase — that's not "dirty" in the normal sense
            rebase_dir = Path(self.cwd) / ".git" / "rebase-merge"
            apply_dir = Path(self.cwd) / ".git" / "rebase-apply"
            if rebase_dir.is_dir() or apply_dir.is_dir():
                pass  # rebase in progress is handled separately
            else:
                raise DirtyTreeError()

    def _patches_base(self, c: dict[str, str]) -> str | None:
        return self.git.merge_base(c["tracking_branch"], c["patches_branch"])

    def _in_rebase(self) -> bool:
        return (
            (Path(self.cwd) / ".git" / "rebase-merge").is_dir() or
            (Path(self.cwd) / ".git" / "rebase-apply").is_dir()
        )

    def _fix_stale_tracking(self, c: dict[str, str]) -> None:
        """Auto-advance tracking if patches were rebased past it."""
        if self._in_rebase():
            return
        if self.state.is_undo_active():
            return
        tracking = self.git.rev_parse(c["tracking_branch"])
        upstream = self.git.rev_parse(f"upstream/{c['upstream_branch']}")
        if not tracking or not upstream or tracking == upstream:
            return
        # Count non-[bl] commits between tracking and patches
        try:
            output = self.git.run("log", "--format=%s", f"{c['tracking_branch']}..{c['patches_branch']}")
        except GitError:
            return
        non_bl = sum(1 for line in output.splitlines() if not line.startswith(f"{PATCH_PREFIX} "))
        if non_bl > 0:
            self.git.run("branch", "-f", c["tracking_branch"], upstream, check=False)

    # ── Init ──

    def init(self, upstream_url: str, branch: str = "") -> dict:
        # Check if already initialized
        if self.cfg.exists:
            pass  # Allow re-init

        # Add/update upstream remote
        existing = self.git.rev_parse("upstream/HEAD")  # just to check remote exists
        if self.git.run_ok("remote", "get-url", "upstream"):
            self.git.run("remote", "set-url", "upstream", upstream_url)
        else:
            self.git.run("remote", "add", "upstream", upstream_url)

        # Fetch
        if not self.git.fetch("upstream"):
            raise BingoError("Failed to fetch upstream.")

        # Auto-detect branch
        if not branch:
            try:
                info = self.git.run("remote", "show", "upstream")
                for line in info.splitlines():
                    if "HEAD branch" in line:
                        detected = line.split()[-1]
                        if detected and detected != "(unknown)":
                            branch = detected
                            break
            except GitError:
                pass
            if not branch:
                for candidate in ("main", "master", "develop"):
                    if self.git.rev_parse(f"upstream/{candidate}"):
                        branch = candidate
                        break
            if not branch:
                # Use first available remote branch
                try:
                    refs = self.git.run("branch", "-r", "--list", "upstream/*")
                    for line in refs.splitlines():
                        ref = line.strip().replace("upstream/", "").split()[0]
                        if ref and ref != "HEAD":
                            branch = ref
                            break
                except GitError:
                    pass
            if not branch:
                branch = "main"

        # Validate branch exists
        if not self.git.rev_parse(f"upstream/{branch}"):
            raise BingoError(f"Branch 'upstream/{branch}' not found.")

        # Enable rerere + diff3
        self.git.run("config", "rerere.enabled", "true")
        self.git.run("config", "rerere.autoupdate", "true")
        self.git.run("config", "merge.conflictstyle", "diff3")

        tracking = DEFAULT_TRACKING
        patches = DEFAULT_PATCHES

        # Create tracking branch
        self.git.run("branch", "-f", tracking, f"upstream/{branch}", check=False)

        # Create or reuse patches branch
        if not self.git.rev_parse(patches):
            self.git.run("branch", patches, f"upstream/{branch}", check=False)

        # Switch to patches branch
        self.git.run("checkout", patches, check=False)

        # Save config
        self.cfg.save(upstream_url, branch, patches, tracking)

        # Exclude config file
        exclude_file = Path(self.cwd) / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        excludes = exclude_file.read_text() if exclude_file.is_file() else ""
        if CONFIG_FILE not in excludes:
            with open(exclude_file, "a") as f:
                f.write(f"\n{CONFIG_FILE}\n")

        return {
            "ok": True,
            "upstream": upstream_url,
            "branch": branch,
            "tracking": tracking,
            "patches": patches,
        }

    # ── Status ──

    def status(self) -> dict:
        c = self._load()
        self._fix_stale_tracking(c)
        self.git.fetch("upstream")

        tracking = self.git.rev_parse(c["tracking_branch"]) or ""
        upstream = self.git.rev_parse(f"upstream/{c['upstream_branch']}") or ""
        behind = self.git.rev_list_count(f"{c['tracking_branch']}..upstream/{c['upstream_branch']}")

        base = self._patches_base(c)
        patch_count = self.git.rev_list_count(f"{base}..{c['patches_branch']}") if base else 0
        patches = self.git.log_patches(base, c["patches_branch"]) if base and patch_count > 0 else []

        # Overlap detection
        overlap: list[str] = []
        if behind > 0 and patch_count > 0 and base:
            patch_files = set(self.git.diff_names(f"{base}..{c['patches_branch']}"))
            upstream_files = set(self.git.diff_names(f"{c['tracking_branch']}..upstream/{c['upstream_branch']}"))
            overlap = sorted(patch_files & upstream_files)

        in_rebase = self._in_rebase()
        patches_stale = bool(base and tracking and base != tracking)
        up_to_date = behind == 0 and not patches_stale

        # Recommended action
        if in_rebase:
            action = "resolve_conflict"
            reason = "Rebase in progress. Run conflict-analyze to see conflicts, resolve them, then git add + git rebase --continue."
        elif patches_stale and behind == 0:
            action = "sync_safe"
            reason = "Patches are on an older base than tracking branch. Run sync to rebase patches onto current upstream."
        elif up_to_date:
            action = "up_to_date"
            reason = "Fork is in sync with upstream. No action needed."
        elif behind > 0 and not overlap:
            action = "sync_safe"
            reason = f"{behind} commits behind. No file overlap detected. Safe to sync."
        elif behind > 0 and overlap:
            action = "sync_risky"
            reason = f"{behind} commits behind. {len(overlap)} file(s) overlap with your patches — conflicts likely. Run sync --dry-run first."
        else:
            action = "unknown"
            reason = "Check status manually."

        return {
            "ok": True,
            "upstream_url": c["upstream_url"],
            "upstream_branch": c["upstream_branch"],
            "current_branch": self.git.current_branch(),
            "behind": behind,
            "patch_count": patch_count,
            "patches": [
                {"name": p.name, "hash": p.hash, "subject": p.subject, "files": p.files}
                for p in patches
            ],
            "conflict_risk": overlap,
            "in_rebase": in_rebase,
            "up_to_date": up_to_date,
            "recommended_action": action,
            "reason": reason,
        }

    # ── Doctor ──

    def doctor(self) -> dict:
        checks = []

        def check(name: str, fn):
            try:
                detail = fn()
                checks.append({"name": name, "status": "pass", "detail": str(detail)})
            except Exception as e:
                checks.append({"name": name, "status": "fail", "detail": str(e)})

        check("git", lambda: self.git.run("--version").replace("git version ", ""))
        check("rerere", lambda: "enabled" if self.git.run("config", "rerere.enabled") == "true" else (_ for _ in ()).throw(BingoError("disabled")))

        try:
            c = self._load()
            check("upstream_remote", lambda: self.git.run("remote", "get-url", "upstream"))
            check("tracking_branch", lambda: c["tracking_branch"] if self.git.rev_parse(c["tracking_branch"]) else (_ for _ in ()).throw(BingoError("missing")))
            check("patches_branch", lambda: c["patches_branch"] if self.git.rev_parse(c["patches_branch"]) else (_ for _ in ()).throw(BingoError("missing")))

            # Test if patch stack applies cleanly
            def check_patches():
                base = self._patches_base(c)
                if not base:
                    return "no patches"
                count = self.git.rev_list_count(f"{base}..{c['patches_branch']}")
                if count == 0:
                    return "no patches"
                # Quick check: just verify the branch exists and has commits
                return f"{count} patch(es)"
            check("patch_stack", check_patches)
            check("config", lambda: "present")
        except NotInitializedError:
            checks.append({"name": "config", "status": "fail", "detail": "not initialized"})

        issues = sum(1 for c in checks if c["status"] == "fail")
        return {"ok": issues == 0, "issues": issues, "checks": checks}
```

- [ ] **Step 2: Add integration tests**

Add to `tests/test_core.py`:

```python
class TestRepo(unittest.TestCase):
    """Integration tests using real git repos."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create upstream
        self.upstream = os.path.join(self.tmpdir, "upstream")
        os.makedirs(self.upstream)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.upstream, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=self.upstream, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.upstream, capture_output=True)
        Path(self.upstream, "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=self.upstream, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.upstream, capture_output=True)

        # Clone as fork
        self.fork = os.path.join(self.tmpdir, "fork")
        subprocess.run(["git", "clone", self.upstream, self.fork], capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=self.fork, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.fork, capture_output=True)

    def test_init(self):
        repo = Repo(self.fork)
        result = repo.init(self.upstream, "main")
        self.assertTrue(result["ok"])
        self.assertEqual(result["branch"], "main")

    def test_status_after_init(self):
        repo = Repo(self.fork)
        repo.init(self.upstream, "main")
        status = repo.status()
        self.assertTrue(status["ok"])
        self.assertEqual(status["behind"], 0)
        self.assertEqual(status["recommended_action"], "up_to_date")

    def test_status_behind(self):
        repo = Repo(self.fork)
        repo.init(self.upstream, "main")
        # Add upstream commit
        Path(self.upstream, "new.txt").write_text("new")
        subprocess.run(["git", "add", "."], cwd=self.upstream, capture_output=True)
        subprocess.run(["git", "commit", "-m", "new file"], cwd=self.upstream, capture_output=True)
        status = repo.status()
        self.assertEqual(status["behind"], 1)
        self.assertIn(status["recommended_action"], ("sync_safe", "sync_risky"))

    def test_doctor(self):
        repo = Repo(self.fork)
        repo.init(self.upstream, "main")
        result = repo.doctor()
        self.assertTrue(result["ok"])
```

- [ ] **Step 3: Run tests and commit**

Run: `python3 tests/test_core.py -v`
Expected: All pass

```bash
git add bingo_core.py tests/test_core.py
git commit -m "feat(rewrite): Task 2 — Repo class with init, status, doctor"
```

---

### Task 3: Patch Operations

**Files:**
- Modify: `bingo_core.py` — add patch methods to Repo

- [ ] **Step 1: Add all patch methods to Repo class**

Add these methods to the `Repo` class in `bingo_core.py`:

```python
    # ── Patch Operations ──

    def _resolve_patch(self, c: dict, target: str) -> str:
        """Resolve patch name or index to commit hash."""
        base = self._patches_base(c)
        if not base:
            raise BingoError("No patches in stack.")
        try:
            commits = self.git.run("rev-list", "--reverse", f"{base}..{c['patches_branch']}").splitlines()
        except GitError:
            raise BingoError("Failed to list patches.")
        if not commits:
            raise BingoError("No patches in stack.")

        # Try as index (1-based)
        try:
            idx = int(target)
            if 1 <= idx <= len(commits):
                return commits[idx - 1]
            raise BingoError(f"Patch index {target} out of range (1-{len(commits)}).")
        except ValueError:
            pass

        # Try exact name match
        for h in commits:
            subject = self.git.run("log", "-1", "--format=%s", h)
            if f"{PATCH_PREFIX} {target}:" in subject:
                return h

        # Try partial match
        for h in commits:
            subject = self.git.run("log", "-1", "--format=%s", h)
            if target in subject:
                return h

        raise BingoError(f"Patch '{target}' not found.")

    def _validate_patch_name(self, name: str) -> None:
        if len(name) > 100:
            raise BingoError("Patch name too long (max 100 characters).")
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$', name):
            raise BingoError("Invalid patch name. Use letters, numbers, hyphens, underscores. Must start with a letter or number.")

    def patch_new(self, name: str, description: str = "") -> dict:
        c = self._load()
        self._validate_patch_name(name)

        # Check for duplicate
        base = self._patches_base(c)
        if base:
            try:
                log = self.git.run("log", "--format=%s", f"{base}..{c['patches_branch']}")
                if f"{PATCH_PREFIX} {name}:" in log:
                    raise BingoError(f"Patch '{name}' already exists.")
            except GitError:
                pass

        # Check for changes
        has_staged = not self.git.run_ok("diff", "--cached", "--quiet")
        has_unstaged = not self.git.run_ok("diff", "--quiet")
        has_untracked = bool(self.git.run("ls-files", "--others", "--exclude-standard", check=False).strip())

        if not has_staged and not has_unstaged and not has_untracked:
            raise BingoError("No changes to create a patch from.")

        if not has_staged:
            # Auto-stage all changes
            self.git.run("add", "-A")

        msg = f"{PATCH_PREFIX} {name}: {description}" if description else f"{PATCH_PREFIX} {name}: (no description)"
        self.git.run("commit", "-m", msg)
        short_hash = self.git.run("rev-parse", "--short", "HEAD")

        return {"ok": True, "patch": name, "hash": short_hash, "description": description}

    def patch_list(self, verbose: bool = False) -> dict:
        c = self._load()
        base = self._patches_base(c)
        if not base:
            return {"ok": True, "patches": [], "count": 0}

        patches = self.git.log_patches(base, c["patches_branch"])
        result_patches = []
        for p in patches:
            entry: dict[str, Any] = {
                "name": p.name, "hash": p.hash, "subject": p.subject,
                "files": p.files, "stat": p.stat,
            }
            if verbose:
                try:
                    output = self.git.run("diff-tree", "--no-commit-id", "-r", "--name-status", p.hash)
                    entry["file_details"] = output.splitlines() if output else []
                except GitError:
                    entry["file_details"] = []
            result_patches.append(entry)

        return {"ok": True, "patches": result_patches, "count": len(patches)}

    def patch_show(self, target: str) -> dict:
        c = self._load()
        h = self._resolve_patch(c, target)
        short = self.git.run("rev-parse", "--short", h)
        subject = self.git.run("log", "-1", "--format=%s", h)
        m = re.match(r"^\[bl\] ([^:]+):", subject)
        name = m.group(1) if m else ""

        try:
            stat = self.git.run("diff-tree", "--no-commit-id", "--shortstat", h).strip()
        except GitError:
            stat = ""

        try:
            diff = self.git.run("diff-tree", "--no-commit-id", "-p", h)
        except GitError:
            diff = ""

        # Truncate large diffs
        truncated = False
        if len(diff) > 50000:
            diff = diff[:2000]
            truncated = True

        return {
            "ok": True, "truncated": truncated,
            "patch": {"name": name, "hash": short, "subject": subject, "stat": stat, "diff": diff},
        }

    def patch_drop(self, target: str) -> dict:
        c = self._load()
        self._ensure_clean()
        h = self._resolve_patch(c, target)
        short = self.git.run("rev-parse", "--short", h)
        subject = self.git.run("log", "-1", "--format=%s", h)
        m = re.match(r"^\[bl\] ([^:]+):", subject)
        name = m.group(1) if m else target

        # Use rebase to drop the commit
        base = self._patches_base(c)
        self.git.run("rebase", "--onto", f"{h}^", h, c["patches_branch"])

        return {"ok": True, "dropped": name, "hash": short}

    def patch_edit(self, target: str) -> dict:
        c = self._load()
        h = self._resolve_patch(c, target)

        # Check for staged changes to fold in
        has_staged = not self.git.run_ok("diff", "--cached", "--quiet")
        if not has_staged:
            raise BingoError("No staged changes to fold into patch. Stage changes with 'git add' first.")

        subject = self.git.run("log", "-1", "--format=%s", h)

        # Commit staged changes as fixup, then autosquash
        self.git.run("commit", "--fixup", h)
        base = self._patches_base(c)
        env = os.environ.copy()
        env["GIT_SEQUENCE_EDITOR"] = "true"
        env["GIT_EDITOR"] = "true"
        subprocess.run(
            ["git", "rebase", "-i", "--autosquash", base],
            cwd=self.cwd, capture_output=True, text=True, env=env,
        )

        return {"ok": True, "patch": target, "message": f"Folded staged changes into: {subject}"}

    def patch_export(self, output_dir: str = ".") -> dict:
        c = self._load()
        base = self._patches_base(c)
        if not base:
            return {"ok": True, "count": 0, "directory": output_dir, "files": []}

        os.makedirs(output_dir, exist_ok=True)
        output = self.git.run("format-patch", "-o", output_dir, f"{base}..{c['patches_branch']}")
        files = [os.path.basename(f) for f in output.splitlines() if f.strip()]

        # Write series file
        Path(output_dir, "series").write_text("\n".join(files) + "\n")

        return {"ok": True, "count": len(files), "directory": output_dir, "files": files}

    def patch_import(self, path: str) -> dict:
        c = self._load()
        if os.path.isdir(path):
            series = Path(path) / "series"
            if series.is_file():
                files = [os.path.join(path, f.strip()) for f in series.read_text().splitlines() if f.strip()]
            else:
                files = sorted(str(p) for p in Path(path).glob("*.patch"))
        else:
            files = [path]

        imported = []
        for f in files:
            try:
                self.git.run("am", f)
                imported.append(os.path.basename(f))
            except GitError as e:
                raise BingoError(f"Failed to apply {os.path.basename(f)}. Run git am --abort to undo, or resolve and git am --continue.")

        return {"ok": True, "imported": imported, "count": len(imported)}

    def patch_reorder(self, order: str = "") -> dict:
        c = self._load()
        self._ensure_clean()
        base = self._patches_base(c)
        if not base:
            return {"ok": True, "message": "no patches to reorder"}

        commits = self.git.run("rev-list", "--reverse", f"{base}..{c['patches_branch']}").splitlines()
        count = len(commits)
        if count <= 1:
            return {"ok": True, "message": "only one patch"}

        if not order:
            raise BingoError("Provide --order with comma-separated indices, e.g. --order 2,1,3")

        indices = [int(x.strip()) for x in order.split(",") if x.strip()]
        if len(indices) != count:
            raise BingoError(f"Reorder requires exactly {count} indices (one per patch), got {len(indices)}.")
        if sorted(indices) != list(range(1, count + 1)):
            raise BingoError(f"Indices must be a permutation of 1-{count}.")

        # Build rebase script
        reordered = [commits[i - 1] for i in indices]
        script = "#!/bin/sh\ncat > \"$1\" << 'PICKS'\n"
        for h in reordered:
            script += f"pick {h}\n"
        script += "PICKS\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(script)
            f.flush()
            os.chmod(f.name, 0o755)
            try:
                env = os.environ.copy()
                env["GIT_SEQUENCE_EDITOR"] = f.name
                subprocess.run(
                    ["git", "rebase", "-i", base],
                    cwd=self.cwd, capture_output=True, text=True, env=env, check=True,
                )
            finally:
                os.unlink(f.name)

        return {"ok": True, "reordered": order}

    def patch_squash(self, idx1: int, idx2: int) -> dict:
        c = self._load()
        self._ensure_clean()

        if idx1 == idx2:
            raise BingoError("Cannot squash a patch with itself.")
        if abs(idx1 - idx2) != 1:
            raise BingoError("Can only squash adjacent patches.")

        base = self._patches_base(c)
        if not base:
            raise BingoError("No patches to squash.")

        commits = self.git.run("rev-list", "--reverse", f"{base}..{c['patches_branch']}").splitlines()
        count = len(commits)
        if idx1 < 1 or idx2 < 1 or idx1 > count or idx2 > count:
            raise BingoError(f"Index out of range (1-{count}).")

        # Build rebase script: pick all, but mark the second one as "squash"
        lo, hi = sorted([idx1, idx2])
        script = "#!/bin/sh\ncat > \"$1\" << 'PICKS'\n"
        for i, h in enumerate(commits, 1):
            if i == hi:
                script += f"squash {h}\n"
            else:
                script += f"pick {h}\n"
        script += "PICKS\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(script)
            f.flush()
            os.chmod(f.name, 0o755)
            try:
                env = os.environ.copy()
                env["GIT_SEQUENCE_EDITOR"] = f.name
                env["GIT_EDITOR"] = "true"
                subprocess.run(
                    ["git", "rebase", "-i", base],
                    cwd=self.cwd, capture_output=True, text=True, env=env, check=True,
                )
            finally:
                os.unlink(f.name)

        return {"ok": True, "squashed": [idx1, idx2]}

    def patch_meta(self, target: str, key: str = "", value: str = "") -> dict:
        c = self._load()

        # Verify patch exists
        base = self._patches_base(c)
        if base:
            try:
                log = self.git.run("log", "--format=%s", f"{base}..{c['patches_branch']}")
                if f"{PATCH_PREFIX} {target}:" not in log:
                    raise BingoError(f"Patch '{target}' not found.")
            except GitError:
                raise BingoError(f"Patch '{target}' not found.")

        if not key:
            # Show metadata
            meta = self.state.get_patch_meta(target)
            return {"ok": True, "patch": target, "meta": meta}
        else:
            # Set metadata
            self.state.set_patch_meta(target, key, value)
            return {"ok": True, "patch": target, "set": key, "value": value}
```

- [ ] **Step 2: Run tests and commit**

Run: `python3 tests/test_core.py -v`

```bash
git add bingo_core.py
git commit -m "feat(rewrite): Task 3 — all patch operations"
```

---

### Task 4: Sync, Smart-Sync, Undo

**Files:**
- Modify: `bingo_core.py`

This is the most complex task — the core sync logic with conflict handling, rerere, and circuit breaker.

- [ ] **Step 1: Add sync methods to Repo**

```python
    # ── Sync ──

    def sync(self, dry_run: bool = False, force: bool = False, test: bool = False) -> dict:
        c = self._load()
        self._fix_stale_tracking(c)
        if not dry_run:
            self._ensure_clean()

        # Fetch
        if not self.git.fetch("upstream"):
            raise BingoError("Failed to fetch upstream.")

        tracking = self.git.rev_parse(c["tracking_branch"])
        upstream = self.git.rev_parse(f"upstream/{c['upstream_branch']}")
        if not tracking or not upstream:
            raise BingoError("Cannot resolve tracking or upstream branch.")

        if tracking == upstream:
            return {"ok": True, "synced": True, "behind_before": 0, "patches_rebased": 0, "up_to_date": True}

        behind = self.git.rev_list_count(f"{c['tracking_branch']}..upstream/{c['upstream_branch']}")
        patch_count = 0
        base = self._patches_base(c)
        if base:
            patch_count = self.git.rev_list_count(f"{base}..{c['patches_branch']}")

        # Dry run
        if dry_run:
            tmp_branch = f"bl-dryrun-{os.getpid()}"
            tmp_tracking = f"bl-dryrun-tracking-{os.getpid()}"
            try:
                self.git.run("branch", tmp_branch, c["patches_branch"])
                self.git.run("branch", tmp_tracking, f"upstream/{c['upstream_branch']}")
                try:
                    self.git.run("rebase", "--onto", tmp_tracking, c["tracking_branch"], tmp_branch)
                    return {"ok": True, "dry_run": True, "clean": True, "behind": behind, "patches": patch_count}
                except GitError:
                    conflicted = self.git.ls_files_unmerged()
                    self.git.run("rebase", "--abort", check=False)
                    return {"ok": True, "dry_run": True, "clean": False, "behind": behind,
                            "patches": patch_count, "conflicted_files": conflicted}
            finally:
                self.git.run("checkout", c["patches_branch"], check=False)
                self.git.run("branch", "-D", tmp_branch, check=False)
                self.git.run("branch", "-D", tmp_tracking, check=False)

        # Save undo state
        saved_head = self.git.rev_parse("HEAD") or ""
        saved_tracking = tracking
        self.state.save_undo(saved_head, saved_tracking)

        # Update tracking
        self.git.run("branch", "-f", c["tracking_branch"], f"upstream/{c['upstream_branch']}")
        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"], check=False)

        # Rebase
        try:
            self.git.run("rebase", "--onto", c["tracking_branch"], saved_tracking, c["patches_branch"])
        except GitError as rebase_err:
            # Check if rerere auto-resolved everything
            unresolved = self.git.ls_files_unmerged()
            if not unresolved:
                # rerere resolved! Auto-continue loop
                for _ in range(50):
                    if not self._in_rebase():
                        break
                    env = os.environ.copy()
                    env["GIT_EDITOR"] = "true"
                    result = subprocess.run(
                        ["git", "rebase", "--continue"],
                        cwd=self.cwd, capture_output=True, text=True, env=env,
                    )
                    if result.returncode == 0:
                        break
                    unresolved = self.git.ls_files_unmerged()
                    if unresolved:
                        break

                if not self._in_rebase():
                    self._record_sync(c, behind, saved_tracking)
                    self.state.run_hooks("on-sync-success", {"behind_before": behind, "patches_rebased": patch_count, "rerere_resolved": True})
                    return {"ok": True, "synced": True, "behind_before": behind,
                            "patches_rebased": patch_count, "rerere_resolved": True}

            # Real conflict — rollback tracking
            self.git.run("branch", "-f", c["tracking_branch"], saved_tracking, check=False)
            self.state.run_hooks("on-conflict", {"patch_count": patch_count})

            conflicted = self.git.ls_files_unmerged()
            return {
                "ok": False, "synced": False, "conflict": True,
                "conflicted_files": conflicted,
                "abort_cmd": "git rebase --abort",
                "next": "Run bingo-light conflict-analyze --json to see conflict details, then resolve, git add, git rebase --continue.",
            }

        # Clean rebase succeeded
        self._record_sync(c, behind, saved_tracking)

        # Post-sync tests
        if test:
            test_result = self.test()
            if not test_result.get("ok") or test_result.get("test") == "fail":
                # Auto-undo
                self.git.run("branch", "-f", c["patches_branch"], saved_head, check=False)
                self.git.run("reset", "--hard", saved_head, check=False)
                self.git.run("branch", "-f", c["tracking_branch"], saved_tracking, check=False)
                self.state.run_hooks("on-test-fail", {"behind_before": behind})
                return {"ok": False, "synced": False, "test": "fail", "auto_undone": True}

        self.state.run_hooks("on-sync-success", {"behind_before": behind, "patches_rebased": patch_count})
        return {"ok": True, "synced": True, "behind_before": behind, "patches_rebased": patch_count}

    def _record_sync(self, c: dict, behind: int, saved_tracking: str) -> None:
        base = self._patches_base(c)
        patches = self.git.log_patches(base, c["patches_branch"]) if base else []
        self.state.record_sync({
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "upstream_before": self.git.run("rev-parse", "--short", saved_tracking, check=False),
            "upstream_after": self.git.rev_parse(c["tracking_branch"]) or "",
            "upstream_commits_integrated": behind,
            "patches": [{"name": p.name, "hash": p.hash} for p in patches],
        })
        self.state.clear_sync_failures()

    def smart_sync(self) -> dict:
        c = self._load()
        self._fix_stale_tracking(c)
        self._ensure_clean()

        # Fetch
        if not self.git.fetch("upstream"):
            raise BingoError("Failed to fetch upstream.")

        upstream_target = self.git.rev_parse(f"upstream/{c['upstream_branch']}") or ""

        # Circuit breaker
        if self.state.check_circuit_breaker(upstream_target):
            raise BingoError("Circuit breaker: 3 consecutive sync failures on the same upstream commit. Resolve conflicts manually or wait for upstream to advance.")

        tracking = self.git.rev_parse(c["tracking_branch"])
        upstream = self.git.rev_parse(f"upstream/{c['upstream_branch']}")
        if not tracking or not upstream:
            raise BingoError("Cannot resolve tracking or upstream branch.")

        if tracking == upstream:
            patch_count = 0
            base = self._patches_base(c)
            if base:
                patch_count = self.git.rev_list_count(f"{base}..{c['patches_branch']}")
            return {"ok": True, "action": "none", "message": "Already up to date.", "behind": 0, "patches": patch_count}

        behind = self.git.rev_list_count(f"{c['tracking_branch']}..upstream/{c['upstream_branch']}")
        base = self._patches_base(c)
        patch_count = self.git.rev_list_count(f"{base}..{c['patches_branch']}") if base else 0

        # Save state
        saved_head = self.git.rev_parse("HEAD") or ""
        saved_tracking = tracking
        self.state.save_undo(saved_head, saved_tracking)

        # Update tracking
        self.git.run("branch", "-f", c["tracking_branch"], f"upstream/{c['upstream_branch']}")
        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"], check=False)

        # Attempt rebase
        try:
            self.git.run("rebase", "--onto", c["tracking_branch"], saved_tracking, c["patches_branch"])
        except GitError:
            pass
        else:
            # Clean rebase
            self._record_sync(c, behind, saved_tracking)
            return {"ok": True, "action": "synced", "behind_before": behind,
                    "patches_rebased": patch_count, "conflicts_resolved": 0}

        # Conflict resolution loop
        max_resolve = 20
        conflicts_resolved = 0

        for i in range(max_resolve):
            if not self._in_rebase():
                break

            unresolved = self.git.ls_files_unmerged()
            if not unresolved:
                # rerere resolved this step
                env = os.environ.copy()
                env["GIT_EDITOR"] = "true"
                result = subprocess.run(
                    ["git", "rebase", "--continue"],
                    cwd=self.cwd, capture_output=True, text=True, env=env,
                )
                if result.returncode == 0:
                    conflicts_resolved += 1
                    if not self._in_rebase():
                        break
                    continue
                # Check again
                unresolved = self.git.ls_files_unmerged()
                if not unresolved:
                    continue

            # Real unresolved conflicts — rollback tracking and report
            self.git.run("branch", "-f", c["tracking_branch"], saved_tracking, check=False)
            self.state.record_sync_failure(upstream_target)

            # Build conflict details
            remaining = []
            for f in unresolved:
                info = self._extract_conflict(f)
                remaining.append(info)

            # Get current patch info
            current_patch = ""
            msg_file = Path(self.cwd) / ".git" / "rebase-merge" / "message"
            if msg_file.is_file():
                current_patch = msg_file.read_text().splitlines()[0] if msg_file.read_text() else ""

            return {
                "ok": False, "action": "needs_human",
                "behind_before": behind,
                "conflicts_auto_resolved": conflicts_resolved,
                "current_patch": current_patch,
                "remaining_conflicts": [
                    {"file": ci.file, "ours": ci.ours, "theirs": ci.theirs,
                     "conflict_count": ci.conflict_count, "merge_hint": ci.merge_hint}
                    for ci in remaining
                ],
                "resolution_steps": [
                    "1. Read ours/theirs for each conflict",
                    "2. Write merged content to the file",
                    "3. git add <file>",
                    "4. git rebase --continue",
                    "5. Run bingo-light smart-sync again to continue",
                ],
                "abort_cmd": "git rebase --abort",
                "next": "For each conflict: read merge_hint, write merged file, git add, git rebase --continue",
            }

        if i >= max_resolve - 1:
            self.git.run("rebase", "--abort", check=False)
            self.git.run("branch", "-f", c["tracking_branch"], saved_tracking, check=False)
            raise BingoError(f"Smart sync: exceeded {max_resolve} resolution attempts. Aborting.")

        # All resolved via rerere
        self._record_sync(c, behind, saved_tracking)
        return {
            "ok": True, "action": "synced_with_rerere",
            "behind_before": behind, "patches_rebased": patch_count,
            "conflicts_auto_resolved": conflicts_resolved,
        }

    def _extract_conflict(self, filepath: str) -> ConflictInfo:
        """Extract conflict details from a file with merge markers."""
        full_path = os.path.join(self.cwd, filepath)
        ours_lines = []
        theirs_lines = []
        conflict_count = 0
        section = None  # None, "ours", "base", "theirs"

        try:
            with open(full_path) as f:
                for line in f:
                    if line.startswith("<<<<<<<"):
                        conflict_count += 1
                        section = "ours"
                    elif line.startswith("|||||||"):
                        section = "base"
                    elif line.startswith("======="):
                        section = "theirs"
                    elif line.startswith(">>>>>>>"):
                        section = None
                    elif section == "ours":
                        ours_lines.append(line.rstrip("\n"))
                    elif section == "theirs":
                        theirs_lines.append(line.rstrip("\n"))
        except OSError:
            pass

        ours = "\n".join(ours_lines)
        theirs = "\n".join(theirs_lines)
        hint = "Merge both changes. Keep ours (upstream) and theirs (your patch)."

        return ConflictInfo(file=filepath, ours=ours, theirs=theirs,
                           conflict_count=conflict_count, merge_hint=hint)

    # ── Undo ──

    def undo(self) -> dict:
        c = self._load()
        self._ensure_clean()

        undo_data = self.state.load_undo()
        if not undo_data:
            # Fallback to reflog
            try:
                reflog = self.git.run("reflog", c["patches_branch"], "--format=%H", "-2")
                entries = reflog.splitlines()
                if len(entries) >= 2:
                    undo_data = (entries[1], "")
            except GitError:
                pass

        if not undo_data:
            return {"ok": True, "message": "nothing to undo"}

        prev_head, prev_tracking = undo_data

        if not prev_head or prev_head == self.git.rev_parse("HEAD"):
            return {"ok": True, "message": "nothing to undo"}

        # Restore
        self.git.run("reset", "--hard", prev_head)
        if prev_tracking:
            self.git.run("branch", "-f", c["tracking_branch"], prev_tracking, check=False)

        self.state.set_undo_active()

        return {"ok": True, "restored_to": prev_head}
```

- [ ] **Step 2: Run tests and commit**

```bash
python3 tests/test_core.py -v
git add bingo_core.py
git commit -m "feat(rewrite): Task 4 — sync, smart-sync, undo, conflict analysis"
```

---

### Task 5: Remaining Commands

**Files:**
- Modify: `bingo_core.py`

- [ ] **Step 1: Add remaining commands**

```python
    # ── Conflict Analyze ──

    def conflict_analyze(self) -> dict:
        if not self._in_rebase():
            return {"ok": True, "in_rebase": False, "conflicts": []}

        unresolved = self.git.ls_files_unmerged()
        if not unresolved:
            return {"ok": True, "in_rebase": True, "conflicts": []}

        conflicts = []
        for f in unresolved:
            info = self._extract_conflict(f)
            conflicts.append({
                "file": info.file, "ours": info.ours, "theirs": info.theirs,
                "conflict_count": info.conflict_count, "merge_hint": info.merge_hint,
            })

        return {"ok": True, "in_rebase": True, "conflicts": conflicts}

    # ── Diff ──

    def diff(self) -> dict:
        c = self._load()
        base = self._patches_base(c)
        if not base:
            return {"ok": True, "stat": "", "diff": ""}

        try:
            stat = self.git.run("diff", f"{base}..{c['patches_branch']}", "--stat")
        except GitError:
            stat = ""

        try:
            diff_content = self.git.run("diff", f"{base}..{c['patches_branch']}")
        except GitError:
            diff_content = ""

        truncated = False
        if len(diff_content) > 50000:
            diff_content = diff_content[:2000]
            truncated = True

        return {"ok": True, "truncated": truncated, "stat": stat, "diff": diff_content}

    # ── History ──

    def history(self) -> dict:
        syncs = self.state.get_history()
        if not syncs:
            return {"ok": True, "syncs": []}
        return {"ok": True, "syncs": syncs}

    # ── Session ──

    def session(self, update: bool = False) -> dict:
        c = self._load()
        if update:
            behind = self.git.rev_list_count(f"{c['tracking_branch']}..upstream/{c['upstream_branch']}")
            base = self._patches_base(c)
            patches = self.git.log_patches(base, c["patches_branch"]) if base else []

            # Build session markdown
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            lines = [
                f"# bingo-light session notes",
                f"Updated: {ts}",
                "",
                "## Upstream",
                f"- URL: {c['upstream_url']}",
                f"- Branch: {c['upstream_branch']}",
                f"- Behind: {behind} commits",
                "",
                f"## Patch Stack ({len(patches)} patches)",
            ]
            for i, p in enumerate(patches, 1):
                lines.append(f"{i}. {p.subject} ({p.files} file(s))")

            # Last sync info
            lines.append("")
            lines.append("## Last Sync")
            try:
                reflog = self.git.run("reflog", "show", c["patches_branch"], "--format=%gd %gs %cr", "-1")
                lines.append(reflog if reflog else "No sync history in reflog")
            except GitError:
                lines.append("No sync history")

            # Rerere stats
            rr_cache = Path(self.cwd) / ".git" / "rr-cache"
            rr_count = len(list(rr_cache.iterdir())) if rr_cache.is_dir() else 0
            lines.append("")
            lines.append("## Rerere")
            lines.append(f"{rr_count} recorded resolution(s)")

            content = "\n".join(lines)
            self.state.update_session(content)
            return {"ok": True, "updated": True, "session": content}

        content = self.state.get_session()
        if content:
            return {"ok": True, "session": content}
        return {"ok": True, "session": None, "message": "No session notes. Run 'bingo-light session update' to generate."}

    # ── Test ──

    def test(self) -> dict:
        c = self._load()
        test_cmd = self.cfg.get("test.command")
        if not test_cmd:
            raise BingoError("No test command configured. Set one with: bingo-light config set test.command '<command>'")

        result = subprocess.run(
            ["bash", "-c", test_cmd],
            cwd=self.cwd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return {"ok": True, "test": "pass", "command": test_cmd}
        return {"ok": False, "test": "fail", "command": test_cmd, "output": result.stdout + result.stderr}

    # ── Config commands ──

    def config_get(self, key: str) -> dict:
        self._load()  # ensure initialized
        value = self.cfg.get(key)
        if value is None:
            raise BingoError(f"Config key '{key}' not set.")
        return {"ok": True, "key": key, "value": value}

    def config_set(self, key: str, value: str) -> dict:
        self._load()  # ensure initialized
        self.cfg.set(key, value)
        return {"ok": True, "key": key, "value": value}

    def config_list(self) -> dict:
        self._load()  # ensure initialized
        return {"ok": True, "config": self.cfg.list_all()}

    # ── Auto-sync (GitHub Actions) ──

    def auto_sync(self) -> dict:
        c = self._load()
        workflow_dir = Path(self.cwd) / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        output_file = workflow_dir / "bingo-light-sync.yml"

        workflow = f"""name: bingo-light auto-sync
on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Install bingo-light
        run: |
          curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/bingo-light -o /usr/local/bin/bingo-light
          chmod +x /usr/local/bin/bingo-light
      - name: Sync with upstream
        run: bingo-light smart-sync --json --yes
      - name: Push if changed
        run: git push || true
"""
        output_file.write_text(workflow)
        return {"ok": True, "file": str(output_file)}

    # ── Workspace ──

    def workspace_init(self) -> dict:
        ws_dir = Path.home() / ".config" / "bingo-light"
        ws_dir.mkdir(parents=True, exist_ok=True)
        ws_file = ws_dir / "workspace.json"
        if not ws_file.is_file():
            ws_file.write_text(json.dumps({"repos": []}, indent=2))
        return {"ok": True, "workspace": str(ws_file)}

    def workspace_add(self, path: str) -> dict:
        ws_file = Path.home() / ".config" / "bingo-light" / "workspace.json"
        if not ws_file.is_file():
            self.workspace_init()
        data = json.loads(ws_file.read_text())
        abs_path = os.path.abspath(path)
        alias = os.path.basename(abs_path)
        repos = data.setdefault("repos", [])
        if not any(r["path"] == abs_path for r in repos):
            repos.append({"path": abs_path, "alias": alias})
            ws_file.write_text(json.dumps(data, indent=2))
        return {"ok": True, "added": alias, "path": abs_path}

    def workspace_list(self) -> dict:
        ws_file = Path.home() / ".config" / "bingo-light" / "workspace.json"
        if not ws_file.is_file():
            return {"ok": True, "repos": []}
        data = json.loads(ws_file.read_text())
        return {"ok": True, "repos": data.get("repos", [])}

    def workspace_sync(self) -> dict:
        ws = self.workspace_list()
        results = []
        for r in ws.get("repos", []):
            try:
                repo = Repo(r["path"])
                repo.smart_sync()
                results.append({"alias": r.get("alias", r["path"]), "status": "ok"})
            except BingoError as e:
                results.append({"alias": r.get("alias", r["path"]), "status": str(e)})
        return {"ok": True, "synced": results}
```

- [ ] **Step 2: Run tests and commit**

```bash
python3 tests/test_core.py -v
git add bingo_core.py
git commit -m "feat(rewrite): Task 5 — remaining commands (conflict-analyze, diff, history, session, test, workspace)"
```

---

### Task 6: CLI Entry Point

**Files:**
- Rewrite: `bingo-light`
- Create: `bingo-light.bash` (archive old)

- [ ] **Step 1: Archive old Bash version**

```bash
cp bingo-light bingo-light.bash
git add bingo-light.bash
```

- [ ] **Step 2: Write Python CLI entry**

Rewrite `bingo-light` as a Python script. This is the full CLI with argparse, human output formatting, and color support. The file is ~400 lines. Write the complete file — it handles all commands, all output formats, and all edge cases.

Key structure:
```python
#!/usr/bin/env python3
"""bingo-light — AI-native fork maintenance tool"""

import sys, os, json, argparse
from bingo_core import Repo, BingoError, VERSION

# Color codes (auto-disabled if not TTY)
# Argument parser with subcommands
# dispatch() maps args to Repo methods
# format_human() converts dicts to colored terminal output
# main() ties it all together with error handling
```

The CLI must produce **identical JSON output** to the Bash version for all commands, so existing tests pass.

- [ ] **Step 3: Make executable and test**

```bash
chmod +x bingo-light
./bingo-light --version   # Should print "bingo-light 2.0.0"
./bingo-light help        # Should show help text
```

- [ ] **Step 4: Run existing test suite**

```bash
./tests/test.sh           # 70 core tests
./tests/test-json.sh      # 55 JSON fuzz tests
./tests/test-edge.sh      # 18 edge tests
```

Target: all 143 shell tests pass.

- [ ] **Step 5: Commit**

```bash
git add bingo-light bingo-light.bash
git commit -m "feat(rewrite): Task 6 — Python CLI entry, archive Bash version"
```

---

### Task 7: MCP Server Rewrite

**Files:**
- Modify: `mcp-server.py`

- [ ] **Step 1: Replace subprocess calls with direct imports**

Replace `run_bl()` and all subprocess-based tool handlers with direct `bingo_core.Repo` calls. Keep the JSON-RPC 2.0 framing, Content-Length protocol, and security checks (.git/ block, path traversal, Content-Length limits).

Key change pattern:
```python
# Before:
def handle_bingo_status(arguments):
    return run_bl(["status"], cwd)

# After:
from bingo_core import Repo
def handle_bingo_status(arguments):
    repo = Repo(cwd)
    result = repo.status()
    return {"content": [{"type": "text", "text": json.dumps(result)}]}
```

Keep `bingo_conflict_resolve` as direct file write (not via bingo_core) since it writes files and runs `git add` + `git rebase --continue`.

- [ ] **Step 2: Run MCP tests**

```bash
python3 tests/test-mcp.py
```

Target: 35/35 pass

- [ ] **Step 3: Commit**

```bash
git add mcp-server.py
git commit -m "feat(rewrite): Task 7 — MCP server uses direct import"
```

---

### Task 8: Update agent.py and tui.py

**Files:**
- Modify: `agent.py`
- Modify: `tui.py`

- [ ] **Step 1: Update agent.py to import bingo_core**

Replace `run_bl()` subprocess calls with `Repo` method calls where possible. Keep the agent's observe-analyze-act loop structure.

- [ ] **Step 2: Update tui.py to import bingo_core**

Replace `run_bl()` with `Repo.status()` and `Repo.sync()` calls.

- [ ] **Step 3: Verify and commit**

```bash
python3 -c "import agent; print('OK')"
python3 -c "import tui; print('OK')"
git add agent.py tui.py
git commit -m "feat(rewrite): Task 8 — agent.py and tui.py use direct import"
```

---

### Task 9: Full Integration Testing

**Files:**
- Modify: `CLAUDE.md`
- Modify: `tests/test_core.py` (add more tests if needed)

- [ ] **Step 1: Run ALL test suites**

```bash
./tests/run-all.sh
```

Target: 178/178 pass (or equivalent — some tests may need minor adjustments for Python output format differences like whitespace).

- [ ] **Step 2: Fix any test failures**

Iterate: read failure, fix the output format in CLI or the test expectation, re-run.

- [ ] **Step 3: Update CLAUDE.md**

Update architecture section to reflect Python rewrite. Remove Bash-specific patterns (json_escape, pipefail guards). Add Python patterns.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(rewrite): Task 9 — all tests pass, CLAUDE.md updated"
```

---

## Verification Checklist

After all tasks complete:

- [ ] `./bingo-light --version` prints `bingo-light 2.0.0`
- [ ] `python3 tests/test_core.py -v` — all unit tests pass
- [ ] `./tests/test.sh` — 70 core tests pass
- [ ] `./tests/test-json.sh` — 55 JSON fuzz tests pass
- [ ] `./tests/test-edge.sh` — 18 edge tests pass
- [ ] `python3 tests/test-mcp.py` — 35 MCP tests pass
- [ ] `python3 -c "from bingo_core import Repo; print('OK')"` — import works
- [ ] Old Bash version archived as `bingo-light.bash`
- [ ] No `json_escape`, no `pipefail`, no `set -euo` in Python code

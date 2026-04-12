"""
bingo_core.state — State management (.bingo/ directory) for bingo-light.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from bingo_core import (
    BINGO_DIR,
    CIRCUIT_BREAKER_LIMIT,
    SYNC_HISTORY_MAX,
)
from bingo_core.exceptions import BingoError


class State:
    """Manages .bingo/ directory state: undo, circuit breaker, metadata, etc."""

    def __init__(self, repo_dir: str):
        self.repo_dir = repo_dir
        self.bingo_dir = os.path.join(repo_dir, BINGO_DIR)
        self.metadata_file = os.path.join(self.bingo_dir, "metadata.json")
        self.sync_history_file = os.path.join(self.bingo_dir, "sync-history.json")
        self.session_file = os.path.join(self.bingo_dir, "session.md")

    def _ensure_dir(self) -> None:
        """Create .bingo/ directory if it doesn't exist."""
        os.makedirs(self.bingo_dir, exist_ok=True)

    def acquire_lock(self) -> None:
        """Acquire an exclusive operation lock. Raises BingoError if locked."""
        self._ensure_dir()
        lock_path = os.path.join(self.bingo_dir, ".lock")
        if os.path.isfile(lock_path):
            try:
                with open(lock_path) as f:
                    pid = int(f.read().strip())
                # Check if the locking process is still running
                os.kill(pid, 0)
                raise BingoError(
                    f"Another bingo-light operation is in progress (pid {pid}). "
                    "If this is stale, remove .bingo/.lock"
                )
            except (ValueError, OSError):
                pass  # Stale lock — process is gone
        with open(lock_path, "w") as f:
            f.write(str(os.getpid()))

    def release_lock(self) -> None:
        """Release the operation lock."""
        lock_path = os.path.join(self.bingo_dir, ".lock")
        try:
            os.unlink(lock_path)
        except OSError:
            pass

    # -- Undo --

    def save_undo(self, head: str, tracking: str) -> None:
        """Save undo state for rollback."""
        self._ensure_dir()
        self._write(os.path.join(self.bingo_dir, ".undo-head"), head)
        self._write(os.path.join(self.bingo_dir, ".undo-tracking"), tracking)
        # Clear undo marker -- new sync starts a new cycle
        self._remove(os.path.join(self.bingo_dir, ".undo-active"))

    def load_undo(self) -> Tuple[Optional[str], Optional[str]]:
        """Load saved undo state. Returns (head, tracking) or (None, None)."""
        head = self._read(os.path.join(self.bingo_dir, ".undo-head"))
        tracking = self._read(os.path.join(self.bingo_dir, ".undo-tracking"))
        return head, tracking

    def mark_undo_active(self) -> None:
        """Mark that undo was used -- prevents _fix_stale_tracking from auto-advancing."""
        self._ensure_dir()
        self._write(os.path.join(self.bingo_dir, ".undo-active"), "")

    def is_undo_active(self) -> bool:
        """Check if undo marker is set."""
        return os.path.isfile(os.path.join(self.bingo_dir, ".undo-active"))

    def clear_undo_tracking(self) -> None:
        """Remove the undo tracking file after restoring."""
        self._remove(os.path.join(self.bingo_dir, ".undo-tracking"))

    # -- Circuit Breaker --

    def check_circuit_breaker(self, upstream_target: str) -> bool:
        """Check if circuit breaker is tripped (3+ failures on same commit).

        Returns True if we should STOP (breaker is tripped).
        """
        path = os.path.join(self.bingo_dir, ".sync-failures")
        if not os.path.isfile(path):
            return False
        try:
            content = self._read(path)
            if content is None:
                return False
            lines = content.strip().split("\n")
            if len(lines) < 2:
                return False
            target = lines[0]
            count = int(lines[1])
            return target == upstream_target and count >= CIRCUIT_BREAKER_LIMIT
        except (ValueError, IndexError):
            return False

    def record_circuit_breaker(self, upstream_target: str) -> None:
        """Record a sync failure for circuit breaker."""
        self._ensure_dir()
        path = os.path.join(self.bingo_dir, ".sync-failures")
        prev_count = 0
        if os.path.isfile(path):
            try:
                content = self._read(path)
                if content:
                    lines = content.strip().split("\n")
                    if len(lines) >= 2 and lines[0] == upstream_target:
                        prev_count = int(lines[1])
            except (ValueError, IndexError):
                pass
        self._write(path, f"{upstream_target}\n{prev_count + 1}")

    def clear_circuit_breaker(self) -> None:
        """Reset circuit breaker on success."""
        self._remove(os.path.join(self.bingo_dir, ".sync-failures"))

    # -- Metadata --

    def _load_metadata(self) -> dict:
        """Load metadata.json, creating it if needed."""
        self._ensure_dir()
        if not os.path.isfile(self.metadata_file):
            return {"patches": {}}
        try:
            with open(self.metadata_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"patches": {}}

    def _save_metadata(self, data: dict) -> None:
        """Atomically write metadata.json."""
        self._ensure_dir()
        self._write_json(self.metadata_file, data)

    def patch_meta_get(self, patch_name: str) -> dict:
        """Get metadata for a patch."""
        data = self._load_metadata()
        return data.get("patches", {}).get(
            patch_name,
            {
                "reason": "",
                "tags": [],
                "expires": None,
                "upstream_pr": "",
                "status": "permanent",
            },
        )

    def patch_meta_set(self, patch_name: str, key: str, value: str) -> None:
        """Set a metadata field for a patch."""
        data = self._load_metadata()
        patches = data.setdefault("patches", {})
        p = patches.setdefault(
            patch_name,
            {
                "reason": "",
                "tags": [],
                "expires": None,
                "upstream_pr": "",
                "status": "permanent",
                "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        if key in ("tag", "tags"):
            tags_list = p.setdefault("tags", [])
            for t in (v.strip() for v in value.split(",")):
                if t and t not in tags_list:
                    tags_list.append(t)
        elif key in ("reason", "expires", "upstream_pr", "status"):
            p[key] = value
        self._save_metadata(data)

    # -- Sync History --

    def record_sync(
        self,
        behind: int,
        upstream_before: str,
        upstream_after: str,
        patches: List[dict],
    ) -> None:
        """Record a sync event."""
        self._ensure_dir()
        data: dict = {"syncs": []}
        if os.path.isfile(self.sync_history_file):
            try:
                with open(self.sync_history_file) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                data = {"syncs": []}

        data["syncs"].append(
            {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "upstream_before": upstream_before,
                "upstream_after": upstream_after,
                "upstream_commits_integrated": behind,
                "patches": patches,
            }
        )
        # Keep only the last N entries
        data["syncs"] = data["syncs"][-SYNC_HISTORY_MAX:]
        self._write_json(self.sync_history_file, data)

    def get_sync_history(self) -> dict:
        """Get sync history."""
        if not os.path.isfile(self.sync_history_file):
            return {"syncs": []}
        try:
            with open(self.sync_history_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"syncs": []}

    # -- Session --

    def update_session(self, content: str) -> None:
        """Write session notes."""
        self._ensure_dir()
        self._write(self.session_file, content)

    def get_session(self) -> Optional[str]:
        """Read session notes."""
        return self._read(self.session_file)

    # -- Hooks --

    def run_hook(self, event: str, data: Optional[dict] = None) -> None:
        """Run a hook script if it exists: .bingo/hooks/<event>."""
        hook_path = os.path.join(self.bingo_dir, "hooks", event)
        if os.path.isfile(hook_path) and os.access(hook_path, os.X_OK):
            try:
                json_data = json.dumps(data or {})
                result = subprocess.run(
                    [hook_path],
                    cwd=self.repo_dir,
                    input=json_data,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    import sys
                    print(
                        f"warning: hook '{event}' exited {result.returncode}",
                        file=sys.stderr,
                    )
            except subprocess.TimeoutExpired:
                import sys
                print(f"warning: hook '{event}' timed out", file=sys.stderr)
            except OSError:
                pass  # Hook not executable or missing interpreter

    # -- Internal helpers --

    def _write(self, path: str, content: str) -> None:
        with open(path, "w") as f:
            f.write(content)

    def _read(self, path: str) -> Optional[str]:
        if not os.path.isfile(path):
            return None
        try:
            with open(path) as f:
                return f.read().strip()
        except IOError:
            return None

    def _remove(self, path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    def _write_json(self, path: str, data: dict) -> None:
        """Atomically write JSON file using temp file + rename."""
        dir_name = os.path.dirname(path) or "."
        fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_name)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise

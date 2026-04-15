"""
bingo_core.team — Team collaboration state (.bingo/team.json).

Manages patch locks and team membership for multi-person fork maintenance.
Advisory locking: prevents accidental concurrent edits, not a security boundary.

Storage:
    .bingo/team.json
    {
        "locks": {
            "<patch_name>": {
                "owner": "<user>",
                "locked_at": "ISO8601",
                "reason": ""
            }
        }
    }

Python 3.8+ stdlib only.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import List, Optional

from bingo_core import BINGO_DIR
from bingo_core.exceptions import BingoError


class TeamState:
    """Manages .bingo/team.json for patch locking and team coordination."""

    def __init__(self, repo_dir: str, git=None):
        self.repo_dir = repo_dir
        self._git = git  # optional Git instance for get_user()
        self.bingo_dir = os.path.join(repo_dir, BINGO_DIR)
        self.team_file = os.path.join(self.bingo_dir, "team.json")

    def _load(self) -> dict:
        """Load team.json, returning empty structure if missing."""
        if not os.path.isfile(self.team_file):
            return {"locks": {}}
        try:
            with open(self.team_file) as f:
                data = json.load(f)
            if "locks" not in data:
                data["locks"] = {}
            return data
        except (json.JSONDecodeError, IOError):
            return {"locks": {}}

    def _save(self, data: dict) -> None:
        """Atomically write team.json."""
        os.makedirs(self.bingo_dir, exist_ok=True)
        dir_name = os.path.dirname(self.team_file)
        fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_name)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.team_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise

    def get_user(self) -> str:
        """Detect current user from git config or environment."""
        if self._git:
            for key in ("user.name", "user.email"):
                try:
                    val = self._git.run("config", key, check=False)
                    if val and val.strip():
                        return val.strip()
                except Exception:
                    pass
        return os.environ.get("USER", "unknown")

    def lock(self, patch_name: str, owner: str = "", reason: str = "") -> dict:
        """Lock a patch for exclusive editing.

        Returns {"ok": True, "patch": ..., "owner": ..., "locked_at": ...}
        Raises BingoError if already locked by another user.
        """
        if not owner:
            owner = self.get_user()
        data = self._load()
        existing = data["locks"].get(patch_name)
        if existing and existing["owner"] != owner:
            raise BingoError(
                f"Patch '{patch_name}' is locked by {existing['owner']} "
                f"(since {existing['locked_at']}). "
                f"They must unlock it first, or use --force."
            )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        data["locks"][patch_name] = {
            "owner": owner,
            "locked_at": now,
            "reason": reason,
        }
        self._save(data)
        return {
            "ok": True,
            "patch": patch_name,
            "owner": owner,
            "locked_at": now,
            "reason": reason,
        }

    def unlock(self, patch_name: str, owner: str = "", force: bool = False) -> dict:
        """Unlock a patch.

        Returns {"ok": True, "patch": ..., "owner": ...}
        Raises BingoError if locked by someone else (unless force=True).
        """
        if not owner:
            owner = self.get_user()
        data = self._load()
        existing = data["locks"].get(patch_name)
        if not existing:
            return {"ok": True, "patch": patch_name, "owner": owner, "was_locked": False}
        if existing["owner"] != owner and not force:
            raise BingoError(
                f"Patch '{patch_name}' is locked by {existing['owner']}. "
                "Use --force to override."
            )
        del data["locks"][patch_name]
        self._save(data)
        return {
            "ok": True,
            "patch": patch_name,
            "owner": owner,
            "was_locked": True,
            "previous_owner": existing["owner"],
        }

    def get_lock(self, patch_name: str) -> Optional[dict]:
        """Get lock info for a patch, or None if unlocked."""
        data = self._load()
        return data["locks"].get(patch_name)

    def is_locked_by_other(self, patch_name: str, current_user: str = "") -> bool:
        """Check if a patch is locked by someone other than current_user."""
        if not current_user:
            current_user = self.get_user()
        lock = self.get_lock(patch_name)
        if not lock:
            return False
        return lock["owner"] != current_user

    def list_locks(self) -> List[dict]:
        """List all active locks.

        Returns list of {"patch": ..., "owner": ..., "locked_at": ..., "reason": ...}
        """
        data = self._load()
        result = []
        for patch_name, info in data["locks"].items():
            result.append({
                "patch": patch_name,
                "owner": info.get("owner", ""),
                "locked_at": info.get("locked_at", ""),
                "reason": info.get("reason", ""),
            })
        return result

"""
bingo_core.exceptions — Exception classes for bingo-light.
"""

from __future__ import annotations

from typing import List


class BingoError(Exception):
    """Base error for bingo-light operations."""


class GitError(BingoError):
    """A git command failed."""

    def __init__(self, cmd: List[str], returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"git command failed (exit {returncode}): {' '.join(cmd)}\n{stderr}"
        )


class NotGitRepoError(BingoError):
    """Not inside a git repository."""

    def __init__(self):
        super().__init__("Not a git repository. Run this inside a git repo.")


class NotInitializedError(BingoError):
    """bingo-light not initialized in this repo."""

    def __init__(self):
        super().__init__(
            "bingo-light not initialized. Run: bingo-light init <upstream-url>"
        )


class DirtyTreeError(BingoError):
    """Working tree has uncommitted changes."""

    def __init__(self, msg: str = ""):
        super().__init__(
            msg or "Working tree is dirty. Commit or stash your changes first."
        )

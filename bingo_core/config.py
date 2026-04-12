"""
bingo_core.config — Configuration management for bingo-light.
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

from bingo_core import CONFIG_FILE, DEFAULT_PATCHES, DEFAULT_TRACKING
from bingo_core.exceptions import NotInitializedError


class Config:
    """Manages the .bingolight configuration file (git config format)."""

    def __init__(self, repo_dir: str):
        self.repo_dir = repo_dir
        self.config_path = os.path.join(repo_dir, CONFIG_FILE)

    def exists(self) -> bool:
        """Check if config file exists."""
        return os.path.isfile(self.config_path)

    def load(self) -> dict:
        """Load all bingo-light config values.

        Returns:
            dict with upstream_url, upstream_branch, patches_branch, tracking_branch

        Raises:
            NotInitializedError: if config file doesn't exist
        """
        if not self.exists():
            raise NotInitializedError()

        return {
            "upstream_url": self.get("upstream-url") or "",
            "upstream_branch": self.get("upstream-branch") or "main",
            "patches_branch": self.get("patches-branch") or DEFAULT_PATCHES,
            "tracking_branch": self.get("tracking-branch") or DEFAULT_TRACKING,
        }

    def save(
        self,
        url: str,
        branch: str,
        patches_branch: str = DEFAULT_PATCHES,
        tracking_branch: str = DEFAULT_TRACKING,
    ) -> None:
        """Write config values."""
        self.set("upstream-url", url)
        self.set("upstream-branch", branch)
        self.set("patches-branch", patches_branch)
        self.set("tracking-branch", tracking_branch)

    def get(self, key: str) -> Optional[str]:
        """Get a config value. Returns None if not found."""
        try:
            result = subprocess.run(
                ["git", "config", "--file", self.config_path, f"bingolight.{key}"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            # Try without bingolight prefix
            result = subprocess.run(
                ["git", "config", "--file", self.config_path, key],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def set(self, key: str, value: str) -> None:
        """Set a config value."""
        subprocess.run(
            ["git", "config", "--file", self.config_path, f"bingolight.{key}", value],
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )

    def list_all(self) -> dict:
        """List all config values as a dict."""
        try:
            result = subprocess.run(
                ["git", "config", "--file", self.config_path, "--list"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return {}
            items = {}
            for line in result.stdout.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    items[k] = v
            return items
        except Exception:
            return {}

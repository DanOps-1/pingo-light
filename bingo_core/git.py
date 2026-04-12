"""
bingo_core.git — Git subprocess wrapper.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import List, Optional

from bingo_core.exceptions import GitError
from bingo_core.models import PatchInfo


class Git:
    """Unified git subprocess wrapper. All git calls go through here."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    def run(self, *args: str, check: bool = True) -> str:
        """Run a git command and return stdout (stripped).

        Args:
            *args: git subcommand and arguments (e.g. "rev-parse", "HEAD")
            check: if True, raise GitError on non-zero exit

        Returns:
            stdout as stripped string

        Raises:
            GitError: if check=True and command fails
        """
        cmd = ["git"] + list(args)
        result = subprocess.run(
            cmd,
            cwd=self.cwd,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise GitError(cmd, result.returncode, result.stderr.strip())
        return result.stdout.strip()

    def run_ok(self, *args: str) -> bool:
        """Run a git command and return True if it succeeds."""
        try:
            cmd = ["git"] + list(args)
            result = subprocess.run(
                cmd,
                cwd=self.cwd,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def run_unchecked(self, *args: str) -> subprocess.CompletedProcess:
        """Run a git command and return the full CompletedProcess."""
        cmd = ["git"] + list(args)
        return subprocess.run(
            cmd,
            cwd=self.cwd,
            capture_output=True,
            text=True,
        )

    def rev_parse(self, ref: str) -> Optional[str]:
        """Resolve a ref to a commit hash. Returns None if missing."""
        try:
            return self.run("rev-parse", ref)
        except GitError:
            return None

    def rev_parse_short(self, ref: str) -> str:
        """Resolve a ref to a short commit hash."""
        try:
            return self.run("rev-parse", "--short", ref)
        except GitError:
            return ""

    def rev_list_count(self, range_spec: str) -> int:
        """Count commits in a range. Returns 0 on error."""
        try:
            return int(self.run("rev-list", "--count", range_spec))
        except (GitError, ValueError):
            return 0

    def fetch(self, remote: str) -> bool:
        """Fetch from a remote. Returns True on success."""
        return self.run_ok("fetch", remote)

    def is_clean(self) -> bool:
        """Check if working tree is clean (no staged or unstaged changes)."""
        return (
            self.run_ok("diff", "--quiet", "HEAD")
            and self.run_ok("diff", "--cached", "--quiet")
        )

    def ls_files_unmerged(self) -> List[str]:
        """Return list of unmerged file paths (sorted, unique)."""
        try:
            output = self.run("ls-files", "--unmerged", check=False)
            if not output:
                return []
            files = set()
            for line in output.splitlines():
                # format: mode hash stage\tfilename
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    files.add(parts[1])
            return sorted(files)
        except Exception:
            return []

    def diff_names(self, range_spec: str) -> List[str]:
        """Return list of changed file names in a range."""
        try:
            output = self.run("diff", "--name-only", range_spec, check=False)
            if not output:
                return []
            return sorted(set(output.splitlines()))
        except Exception:
            return []

    def merge_base(self, ref1: str, ref2: str) -> Optional[str]:
        """Find merge base of two refs. Returns None if not found."""
        try:
            return self.run("merge-base", ref1, ref2)
        except GitError:
            return None

    def current_branch(self) -> str:
        """Return name of current branch."""
        try:
            return self.run("branch", "--show-current")
        except GitError:
            return ""

    def log_patches(self, base: str, branch: str) -> List[PatchInfo]:
        """Parse patches from git log in a single pass.

        Returns list of PatchInfo for commits in base..branch.
        """
        try:
            output = self.run(
                "log",
                "--format=PATCH\t%h\t%s",
                "--shortstat",
                "--numstat",
                "--reverse",
                f"{base}..{branch}",
            )
        except GitError:
            return []

        patches: List[PatchInfo] = []
        current: Optional[PatchInfo] = None

        for line in output.splitlines():
            if line.startswith("PATCH\t"):
                if current is not None:
                    patches.append(current)
                parts = line.split("\t", 2)
                hash_val = parts[1] if len(parts) > 1 else ""
                subject = parts[2] if len(parts) > 2 else ""
                name = ""
                m = re.match(r"^\[bl\] ([^:]+):", subject)
                if m:
                    name = m.group(1)
                current = PatchInfo(
                    name=name, hash=hash_val, subject=subject, files=0, stat=""
                )
            elif current is not None:
                # numstat line: add\tdel\tfile (binary shows -\t-\tfile)
                if re.match(r"^(\d+|-)\t(\d+|-)\t", line):
                    current.files += 1
                    parts = line.split("\t", 2)
                    if len(parts) >= 2:
                        try:
                            current.insertions += int(parts[0])
                            current.deletions += int(parts[1])
                        except ValueError:
                            pass  # binary: -\t-\t — counted but no line stats
                # shortstat line
                elif re.match(r"^\s*\d+ file", line):
                    current.stat = line.strip()

        if current is not None:
            patches.append(current)

        return patches

"""
bingo_core.repo — Repo class: top-level facade with ALL bingo-light commands.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import List, Optional

from bingo_core import (
    PATCH_PREFIX,
    CONFIG_FILE,
    BINGO_DIR,
    DEFAULT_TRACKING,
    DEFAULT_PATCHES,
    MAX_PATCHES,
    MAX_DIFF_SIZE,
    PATCH_NAME_RE,
    PATCH_NAME_MAX,
    MAX_RESOLVE_ITER,
    RERERE_MAX_ITER,
)
from bingo_core.exceptions import (
    BingoError,
    GitError,
    NotGitRepoError,
    DirtyTreeError,
)
from bingo_core.models import ConflictInfo
from bingo_core.git import Git
from bingo_core.config import Config
from bingo_core.state import State


class Repo:
    """Top-level facade with ALL bingo-light commands."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.getcwd()
        self.git = Git(self.path)
        self.config = Config(self.path)
        self.state = State(self.path)

    # -- Internal helpers --

    def _ensure_git_repo(self) -> None:
        """Verify we're in a git repository."""
        if not self.git.run_ok("rev-parse", "--is-inside-work-tree"):
            raise NotGitRepoError()
        # Auto-unshallow if shallow clone
        try:
            result = self.git.run("rev-parse", "--is-shallow-repository", check=False)
            if result == "true":
                self.git.run_ok("fetch", "--unshallow")
        except Exception:
            pass

    def _load(self) -> dict:
        """Load config, raising NotInitializedError if needed.

        Returns dict with upstream_url, upstream_branch, patches_branch, tracking_branch.
        """
        self._ensure_git_repo()
        # Guard: reject .bingolight if tracked by git (possible upstream injection)
        result = self.git.run_unchecked("ls-files", "--error-unmatch", ".bingolight")
        if result.returncode == 0:
            raise BingoError(
                ".bingolight is tracked by git. This is a security risk — "
                "upstream may have injected it. Run: git rm --cached .bingolight"
            )
        c = self.config.load()
        # Auto-fix stale tracking branch (e.g. after manual conflict resolution)
        self._fix_stale_tracking(c)
        return c

    def _ensure_clean(self) -> None:
        """Raise DirtyTreeError if working tree is dirty."""
        if not self.git.is_clean():
            raise DirtyTreeError()

    def _patches_base(self, c: dict) -> Optional[str]:
        """Get merge base between tracking and patches branches."""
        return self.git.merge_base(c["tracking_branch"], c["patches_branch"])

    def _in_rebase(self) -> bool:
        """Check if a rebase is in progress."""
        return os.path.isdir(
            os.path.join(self.path, ".git", "rebase-merge")
        ) or os.path.isdir(os.path.join(self.path, ".git", "rebase-apply"))

    def _fix_stale_tracking(self, c: dict) -> None:
        """Auto-fix tracking branch after manual conflict resolution.

        If a sync was rolled back on conflict and user completed rebase manually,
        tracking branch may be stale. Detect and fix.
        """
        if self._in_rebase():
            return
        if self.state.is_undo_active():
            return

        tracking_pos = self.git.rev_parse(c["tracking_branch"])
        upstream_pos = self.git.rev_parse(f"upstream/{c['upstream_branch']}")
        if not tracking_pos or not upstream_pos:
            return
        if tracking_pos == upstream_pos:
            return

        # Count non-[bl] commits in tracking..patches
        # Only auto-fix if there are exactly the expected non-bl commits
        # (upstream commits that were merged manually after conflict resolution).
        # If there are too many, something else is wrong -- don't touch it.
        try:
            log_output = self.git.run(
                "log",
                "--format=%s",
                f"{c['tracking_branch']}..{c['patches_branch']}",
            )
            non_bl_count = 0
            total_count = 0
            for line in log_output.splitlines():
                if not line:
                    continue
                total_count += 1
                if not line.startswith("[bl] "):
                    non_bl_count += 1
            # Only auto-advance if non-bl commits exist AND they don't
            # outnumber bl commits (heuristic: user manually resolved a sync)
            if 0 < non_bl_count <= total_count // 2 + 1:
                self.git.run(
                    "branch", "-f", c["tracking_branch"], upstream_pos
                )
        except GitError:
            pass

    def _resolve_patch(self, c: dict, target: str) -> str:
        """Resolve a patch target (name or 1-based index) to a commit hash.

        Raises BingoError if not found.
        """
        base = self._patches_base(c)
        if not base:
            raise BingoError("No patches found.")

        try:
            commits_output = self.git.run(
                "rev-list", "--reverse", f"{base}..{c['patches_branch']}"
            )
        except GitError:
            raise BingoError("No patches found.")

        if not commits_output:
            raise BingoError("No patches found.")

        commits = commits_output.splitlines()

        # Try as index first
        if target.isdigit():
            idx = int(target)
            if 1 <= idx <= len(commits):
                return commits[idx - 1]
            raise BingoError(f"Patch index {target} out of range.")

        # Try as exact name
        for h in commits:
            subject = self.git.run("log", "-1", "--format=%s", h)
            if f"{PATCH_PREFIX} {target}:" in subject:
                return h

        # Try as partial match on patch name (not arbitrary substring)
        matches = []
        for h in commits:
            subject = self.git.run("log", "-1", "--format=%s", h)
            m = re.match(r"^\[bl\] ([^:]+):", subject)
            if m and target in m.group(1):
                matches.append(h)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise BingoError(
                f"Ambiguous patch target '{target}': matches {len(matches)} patches. "
                "Use the exact name or index number."
            )

        raise BingoError(f"Patch '{target}' not found.")

    def _validate_patch_name(self, name: str) -> None:
        """Validate a patch name."""
        if len(name) > PATCH_NAME_MAX:
            raise BingoError(f"Patch name too long (max {PATCH_NAME_MAX} characters).")
        if not PATCH_NAME_RE.match(name):
            raise BingoError(
                "Invalid patch name. Use letters, numbers, hyphens, underscores. "
                "Must start with a letter or number."
            )

    def _current_rebase_patch(self) -> str:
        """Read the current patch subject from an in-progress rebase.

        Returns the first line of .git/rebase-merge/message, or "" if
        unavailable. Used by conflict_analyze() and _smart_sync_locked().
        """
        msg_file = os.path.join(self.path, ".git", "rebase-merge", "message")
        if os.path.isfile(msg_file):
            try:
                with open(msg_file) as f:
                    return f.readline().strip()
            except IOError:
                pass
        return ""

    def _build_conflict_result(
        self,
        conflicted_files: List[str],
        **extra: object,
    ) -> dict:
        """Build a standardized conflict result dict.

        Extracts conflict details for each file and includes the current
        rebase patch. Callers can pass additional keys via **extra which
        are merged into the returned dict.

        Always includes:
            ok, conflict, current_patch, conflicted_files,
            conflicts, resolution_steps, abort_cmd
        """
        conflicts = [self._extract_conflict(f) for f in conflicted_files]
        current_patch = self._current_rebase_patch()

        result: dict = {
            "ok": False,
            "conflict": True,
            "current_patch": current_patch,
            "conflicted_files": conflicted_files,
            "conflicts": [c.to_dict() for c in conflicts],
            "resolution_steps": [
                "1. Read ours (upstream) and theirs (your patch) for each conflict",
                "2. Write the merged file content (include both changes where possible)",
                "3. Run: git add <conflicted-files>",
                "4. Run: bingo-light conflict-resolve (or git rebase --continue)",
                "5. If more conflicts appear, repeat from step 1",
                "6. To abort instead: git rebase --abort",
            ],
            "abort_cmd": "git rebase --abort",
        }
        result.update(extra)
        return result

    _CONFLICT_SIZE_LIMIT = 1024 * 1024  # 1MB per file

    def _extract_conflict(self, filepath: str) -> ConflictInfo:
        """Parse conflict markers from a file and return ConflictInfo."""
        full_path = os.path.join(self.path, filepath)
        ours_lines: List[str] = []
        theirs_lines: List[str] = []
        conflict_count = 0
        state = "normal"

        if not os.path.isfile(full_path):
            return ConflictInfo(
                file=filepath, conflict_count=1,
                ours="", theirs="",
                merge_hint="File deleted on one side. Decide: keep or remove.",
            )

        try:
            file_size = os.path.getsize(full_path)
            if file_size > self._CONFLICT_SIZE_LIMIT:
                return ConflictInfo(
                    file=filepath, conflict_count=1,
                    ours="(file too large to display)",
                    theirs="(file too large to display)",
                    merge_hint="Large or binary file conflict. Resolve manually.",
                )
            with open(full_path) as f:
                for line in f:
                    if line.startswith("<<<<<<< "):
                        conflict_count += 1
                        state = "ours"
                    elif line.startswith("||||||| "):
                        state = "base"
                    elif line.startswith("======="):
                        state = "theirs"
                    elif line.startswith(">>>>>>> "):
                        state = "normal"
                    else:
                        if state == "ours":
                            ours_lines.append(line.rstrip("\n"))
                        elif state == "theirs":
                            theirs_lines.append(line.rstrip("\n"))
        except IOError:
            return ConflictInfo(
                file=filepath, conflict_count=1,
                ours="", theirs="",
                merge_hint="Cannot read file. Resolve manually.",
            )

        ours = "\n".join(ours_lines)
        theirs = "\n".join(theirs_lines)

        # Generate merge hint
        if not ours and theirs:
            merge_hint = (
                "Upstream deleted content that your patch modifies. "
                "Decide: keep your version or accept upstream deletion."
            )
        elif ours and not theirs:
            merge_hint = (
                "Your patch deleted content that upstream modified. "
                "Decide: keep upstream changes or accept your deletion."
            )
        elif conflict_count > 1:
            merge_hint = (
                "Multiple conflict regions. Resolve each <<<<<<< ... >>>>>>> "
                "block independently. Usually: keep both additions, reconcile edits."
            )
        else:
            merge_hint = (
                "Merge both changes. Keep ours (upstream) and theirs (your patch)."
            )

        return ConflictInfo(
            file=filepath,
            ours=ours,
            theirs=theirs,
            conflict_count=conflict_count,
            merge_hint=merge_hint,
        )

    def _record_sync(self, c: dict, behind: int, saved_tracking: str) -> None:
        """Record a sync event to history."""
        try:
            upstream_after = (
                self.git.rev_parse(f"upstream/{c['upstream_branch']}") or ""
            )
            base = self._patches_base(c)
            patches_list: List[dict] = []
            if base:
                try:
                    commits = self.git.run(
                        "rev-list", "--reverse", f"{base}..{c['patches_branch']}"
                    )
                    for h in commits.splitlines():
                        if not h:
                            continue
                        subject = self.git.run("log", "-1", "--format=%s", h)
                        pname = ""
                        m = re.match(r"^\[bl\] ([^:]+):", subject)
                        if m:
                            pname = m.group(1)
                        patches_list.append(
                            {
                                "name": pname,
                                "hash": self.git.rev_parse_short(h),
                            }
                        )
                except GitError:
                    pass

            upstream_before_short = saved_tracking[:8] if saved_tracking else ""
            self.state.record_sync(
                behind=behind,
                upstream_before=upstream_before_short,
                upstream_after=upstream_after,
                patches=patches_list,
            )
        except Exception as e:
            import sys
            print(f"warning: failed to record sync history: {e}", file=sys.stderr)

    def _get_patch_mapping(self, c: dict) -> List[dict]:
        """Get current patches as list of {name, hash} dicts."""
        base = self._patches_base(c)
        if not base:
            return []
        patches = self.git.log_patches(base, c["patches_branch"])
        return [{"name": p.name, "hash": p.hash} for p in patches]

    # -- Init --

    def init(self, upstream_url: str, branch: str = "") -> dict:
        """Initialize bingo-light in a git repository.

        Args:
            upstream_url: URL of the original upstream repository
            branch: upstream branch to track (default: auto-detect)

        Returns:
            {"ok": True, "upstream": ..., "branch": ..., "tracking": ..., "patches": ...}
        """
        self._ensure_git_repo()

        # Detect re-init
        reinit = bool(self.git.run_ok("remote", "get-url", "upstream"))

        # Add/update upstream remote
        if reinit:
            self.git.run("remote", "set-url", "upstream", upstream_url)
        else:
            self.git.run("remote", "add", "upstream", upstream_url)

        # Fetch upstream
        if not self.git.fetch("upstream"):
            raise BingoError(f"Failed to fetch upstream. Check the URL: {upstream_url}")

        # Auto-detect upstream branch if not specified
        if not branch:
            try:
                output = self.git.run("remote", "show", "upstream", check=False)
                for line in output.splitlines():
                    if "HEAD branch" in line:
                        detected = line.split()[-1]
                        if detected and detected != "(unknown)":
                            branch = detected
                            break
            except Exception:
                pass

            if not branch:
                for candidate in ["main", "master", "develop"]:
                    if self.git.rev_parse(f"upstream/{candidate}"):
                        branch = candidate
                        break

            branch = branch or "main"

        # Verify upstream branch exists
        if not self.git.rev_parse(f"upstream/{branch}"):
            try:
                output = self.git.run(
                    "branch", "-r", "--list", "upstream/*", check=False
                )
                avail = ", ".join(
                    line.strip().replace("upstream/", "")
                    for line in output.splitlines()
                    if line.strip()
                )
            except Exception:
                avail = "none"
            raise BingoError(
                f"Branch 'upstream/{branch}' not found. Available: {avail or 'none'}"
            )

        patches_branch = DEFAULT_PATCHES
        tracking_branch = DEFAULT_TRACKING

        # Enable rerere + diff3
        self.git.run("config", "rerere.enabled", "true")
        self.git.run("config", "rerere.autoupdate", "true")
        self.git.run("config", "merge.conflictstyle", "diff3")

        # Create tracking branch
        self.git.run(
            "branch", "-f", tracking_branch, f"upstream/{branch}"
        )

        # Create patches branch
        if not self.git.rev_parse(patches_branch):
            # Check if current branch has commits ahead of upstream
            ahead = 0
            merge_base_val = self.git.merge_base(f"upstream/{branch}", "HEAD")
            if merge_base_val:
                ahead = self.git.rev_list_count(f"{merge_base_val}..HEAD")

            if ahead > 0:
                self.git.run("branch", patches_branch, "HEAD")
            else:
                self.git.run("branch", patches_branch, tracking_branch)

        # Save config
        self.config.save(upstream_url, branch, patches_branch, tracking_branch)

        # Exclude config from git tracking
        exclude_file = os.path.join(self.path, ".git", "info", "exclude")
        try:
            exclude_content = ""
            if os.path.isfile(exclude_file):
                with open(exclude_file) as f:
                    exclude_content = f.read()
            if ".bingolight" not in exclude_content:
                with open(exclude_file, "a") as f:
                    f.write("\n.bingolight\n")
        except IOError:
            pass

        # Switch to patches branch
        current = self.git.current_branch()
        if current != patches_branch:
            self.git.run_ok("checkout", patches_branch)

        result = {
            "ok": True,
            "upstream": upstream_url,
            "branch": branch,
            "tracking": tracking_branch,
            "patches": patches_branch,
        }
        if reinit:
            result["reinit"] = True
        return result

    # -- Status & Diagnostics --

    def status(self) -> dict:
        """Get structured status of the fork.

        Returns dict with recommended_action: up_to_date, sync_safe, sync_risky, resolve_conflict
        """
        c = self._load()

        # Fetch upstream silently
        self.git.run_ok("fetch", "upstream")

        tracking_head = self.git.rev_parse(c["tracking_branch"]) or ""
        upstream_head = (
            self.git.rev_parse(f"upstream/{c['upstream_branch']}") or ""
        )

        behind = 0
        if tracking_head and upstream_head and tracking_head != upstream_head:
            behind = self.git.rev_list_count(
                f"{c['tracking_branch']}..upstream/{c['upstream_branch']}"
            )

        base = self._patches_base(c)
        patch_count = 0
        patches: List[dict] = []
        if base:
            patch_count = self.git.rev_list_count(f"{base}..{c['patches_branch']}")
            patch_infos = self.git.log_patches(base, c["patches_branch"])
            patches = [
                {
                    "name": p.name,
                    "hash": p.hash,
                    "subject": p.subject,
                    "files": p.files,
                }
                for p in patch_infos
            ]

        # Conflict risk: overlap between patch files and upstream files
        overlap: List[str] = []
        if behind > 0 and patch_count > 0 and base:
            patch_files = set(self.git.diff_names(f"{base}..{c['patches_branch']}"))
            upstream_files = set(
                self.git.diff_names(
                    f"{c['tracking_branch']}..upstream/{c['upstream_branch']}"
                )
            )
            overlap = sorted(patch_files & upstream_files)

        in_rebase = self._in_rebase()

        # Detect stale patches
        patches_stale = False
        if base and tracking_head and base != tracking_head:
            patches_stale = True

        up_to_date = behind == 0 and not patches_stale

        # Compute recommended action
        if in_rebase:
            action = "resolve_conflict"
            reason = (
                "Rebase in progress. Run conflict-analyze to see conflicts, "
                "resolve them, then git add + git rebase --continue."
            )
        elif patches_stale and behind == 0:
            action = "sync_safe"
            reason = (
                "Patches are on an older base than tracking branch. "
                "Run sync to rebase patches onto current upstream."
            )
        elif up_to_date:
            action = "up_to_date"
            reason = "Fork is in sync with upstream. No action needed."
        elif behind > 0 and not overlap:
            action = "sync_safe"
            reason = (
                f"{behind} commits behind. No file overlap detected. Safe to sync."
            )
        elif behind > 0 and overlap:
            action = "sync_risky"
            reason = (
                f"{behind} commits behind. {len(overlap)} file(s) overlap with "
                "your patches — conflicts likely. Run sync --dry-run first."
            )
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
            "patches": patches,
            "conflict_risk": overlap,
            "in_rebase": in_rebase,
            "up_to_date": up_to_date,
            "recommended_action": action,
            "reason": reason,
        }

    def doctor(self) -> dict:
        """Run health checks on the repository.

        Returns {"ok": True/False, "issues": N, "checks": [...]}
        """
        c = self._load()
        issues = 0
        checks: List[dict] = []

        def _check(name: str, status: str, detail: str = "") -> None:
            nonlocal issues
            checks.append({"name": name, "status": status, "detail": detail})
            if status == "fail":
                issues += 1

        # Git version
        try:
            git_ver = self.git.run("--version").replace("git version ", "")
            _check("git", "pass", git_ver)
        except GitError:
            _check("git", "fail", "git not found")

        # Rerere
        try:
            rerere = self.git.run("config", "rerere.enabled", check=False)
            if rerere == "true":
                _check("rerere", "pass", "enabled")
            else:
                _check("rerere", "fail", "disabled")
        except Exception:
            _check("rerere", "fail", "disabled")

        # Upstream remote
        if self.git.run_ok("remote", "get-url", "upstream"):
            url = self.git.run("remote", "get-url", "upstream", check=False)
            _check("upstream remote", "pass", url)
        else:
            _check("upstream remote", "fail", "not found")

        # Tracking branch
        if self.git.rev_parse(c["tracking_branch"]):
            _check("tracking branch", "pass", c["tracking_branch"])
        else:
            _check("tracking branch", "fail", "missing")

        # Patches branch
        if self.git.rev_parse(c["patches_branch"]):
            _check("patches branch", "pass", c["patches_branch"])
        else:
            _check("patches branch", "fail", "missing")

        # Rebase in progress
        if self._in_rebase():
            _check("rebase", "fail", "rebase in progress — resolve or abort")
        else:
            _check("rebase", "pass", "none")

        # Stale tracking
        tracking_head = self.git.rev_parse(c["tracking_branch"])
        upstream_head = self.git.rev_parse(f"upstream/{c['upstream_branch']}")
        if tracking_head and upstream_head and tracking_head != upstream_head:
            behind = self.git.rev_list_count(
                f"{c['tracking_branch']}..upstream/{c['upstream_branch']}"
            )
            if behind > 0:
                _check(
                    "tracking_freshness", "warn",
                    f"{behind} commit(s) behind upstream — run sync",
                )
            else:
                _check("tracking_freshness", "pass", "up to date")
        elif tracking_head and upstream_head:
            _check("tracking_freshness", "pass", "up to date")

        # .bingo state directory
        bingo_dir = os.path.join(self.path, ".bingo")
        if os.path.isdir(bingo_dir):
            _check("state_dir", "pass", ".bingo/")
        else:
            _check("state_dir", "warn", ".bingo/ missing — undo/history unavailable")

        # Patch stack integrity
        if issues == 0 and not self._in_rebase():
            base = self._patches_base(c)
            if not base:
                _check("patch_stack", "pass", "no patches")
            else:
                patch_count = self.git.rev_list_count(
                    f"{base}..{c['patches_branch']}"
                )
                if patch_count == 0:
                    _check("patch_stack", "pass", "no patches")
                else:
                    tmp_branch = f"bl-doctor-{os.getpid()}"
                    original_branch = self.git.current_branch()
                    try:
                        self.git.run("branch", tmp_branch, c["patches_branch"])
                        current_tracking = self.git.rev_parse(c["tracking_branch"])
                        result = self.git.run_unchecked(
                            "rebase",
                            "--onto",
                            c["tracking_branch"],
                            current_tracking or c["tracking_branch"],
                            tmp_branch,
                        )
                        if result.returncode == 0:
                            _check(
                                "patch_stack",
                                "pass",
                                f"all {patch_count} patch(es) clean",
                            )
                        else:
                            _check("patch_stack", "fail", "conflicts detected")
                            self.git.run_ok("rebase", "--abort")
                    finally:
                        # Restore original branch before deleting tmp
                        if original_branch:
                            self.git.run_ok("checkout", original_branch)
                        else:
                            self.git.run_ok("checkout", c["patches_branch"])
                        self.git.run_ok("branch", "-D", tmp_branch)

        # Config file
        if self.config.exists():
            _check("config", "pass", "present")
        else:
            _check("config", "fail", "missing")

        return {"ok": issues == 0, "issues": issues, "checks": checks}

    def diff(self) -> dict:
        """Show all changes vs upstream (with 50K truncation).

        Returns {"ok": True, "stat": "...", "diff": "...", "truncated": bool}
        """
        c = self._load()
        base = self._patches_base(c)
        if not base:
            return {"ok": True, "stat": "", "diff": "", "truncated": False}

        try:
            stat = self.git.run(
                "diff", f"{base}..{c['patches_branch']}", "--stat", check=False
            )
            diff_content = self.git.run(
                "diff", f"{base}..{c['patches_branch']}", check=False
            )
        except Exception:
            stat = ""
            diff_content = ""

        if len(diff_content) > MAX_DIFF_SIZE:
            preview = diff_content[:2000]
            size_kb = len(diff_content) // 1024
            return {
                "ok": True,
                "truncated": True,
                "stat": stat,
                "preview": preview,
                "full_size": len(diff_content),
                "message": (
                    f"Diff too large ({size_kb}KB). Showing preview. "
                    "Use bingo-light diff without --json for full output."
                ),
            }

        return {
            "ok": True,
            "truncated": False,
            "stat": stat,
            "diff": diff_content,
        }

    def history(self) -> dict:
        """Get sync history from .bingo/sync-history.json.

        Returns {"ok": True, "syncs": [...]}
        """
        self._load()  # validate repo is initialized
        data = self.state.get_sync_history()
        data["ok"] = True
        return data

    def session(self, update: bool = False) -> dict:
        """Get or update session notes.

        Returns {"ok": True, "session": "...", ...}
        """
        c = self._load()

        if update:
            # Fetch upstream silently
            self.git.run_ok("fetch", "upstream")

            tracking_head = self.git.rev_parse(c["tracking_branch"]) or ""
            upstream_head = (
                self.git.rev_parse(f"upstream/{c['upstream_branch']}") or ""
            )
            behind = 0
            if (
                tracking_head
                and upstream_head
                and tracking_head != upstream_head
            ):
                behind = self.git.rev_list_count(
                    f"{c['tracking_branch']}..upstream/{c['upstream_branch']}"
                )

            base = self._patches_base(c)
            patch_count = 0
            patch_list_str = "(none)"
            if base:
                patch_count = self.git.rev_list_count(
                    f"{base}..{c['patches_branch']}"
                )
                if patch_count > 0:
                    patches = self.git.log_patches(base, c["patches_branch"])
                    lines = []
                    for i, p in enumerate(patches, 1):
                        lines.append(f"{i}. {p.subject} ({p.files} file(s))")
                    patch_list_str = "\n".join(lines)

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            content = (
                f"# bingo-light session notes\n"
                f"Updated: {ts}\n\n"
                f"## Upstream\n"
                f"- URL: {c['upstream_url']}\n"
                f"- Branch: {c['upstream_branch']}\n"
                f"- Behind: {behind} commits\n\n"
                f"## Patch Stack ({patch_count} patches)\n"
                f"{patch_list_str}\n\n"
                f"## Last Sync\n"
                f"(see history)\n"
            )
            self.state.update_session(content)
            return {"ok": True, "updated": True, "session": content}

        existing = self.state.get_session()
        if existing:
            return {"ok": True, "session": existing}
        return {
            "ok": True,
            "session": "",
            "message": "No session notes yet. Run bingo-light session update to create.",
        }

    def conflict_analyze(self) -> dict:
        """Analyze current rebase conflicts.

        Returns structured info about each conflicted file.
        """
        self._ensure_git_repo()

        if not self._in_rebase():
            return {"ok": True, "in_rebase": False, "conflicts": []}

        conflicted = self.git.ls_files_unmerged()
        if not conflicted:
            return {"ok": True, "in_rebase": True, "conflicts": []}

        current_patch = self._current_rebase_patch()
        conflicts = [self._extract_conflict(f) for f in conflicted]

        return {
            "ok": True,
            "in_rebase": True,
            "current_patch": current_patch,
            "conflicts": [c.to_dict() for c in conflicts],
            "resolution_steps": [
                "1. Read ours (upstream) and theirs (your patch) for each conflict",
                "2. Write the merged file content (include both changes where possible)",
                "3. Run: git add <conflicted-files>",
                "4. Run: bingo-light conflict-resolve (or git rebase --continue)",
                "5. If more conflicts appear, repeat from step 1",
                "6. To abort instead: git rebase --abort",
            ],
        }

    def conflict_resolve(self, file_path: str, content: str = "") -> dict:
        """Resolve a single conflicted file and continue rebase if possible.

        Args:
            file_path: Path to the conflicted file (relative to repo root)
            content: If non-empty, write this content to the file before staging

        Returns:
            Result dict with resolved file, remaining conflicts, and rebase state
        """
        import pathlib

        self._ensure_git_repo()

        if not self._in_rebase():
            raise BingoError("No rebase in progress. Nothing to resolve.")

        if not file_path:
            raise BingoError("No file specified. Usage: conflict-resolve <file>")

        # Resolve and validate path doesn't escape repo root
        repo_root = pathlib.Path(self.path).resolve()
        resolved = (repo_root / file_path).resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            raise BingoError(
                f"Path escapes repository root: {file_path}"
            )
        rel_path = str(resolved.relative_to(repo_root))

        # Verify file is actually in the unmerged list
        unmerged = self.git.ls_files_unmerged()
        if rel_path not in unmerged:
            raise BingoError(
                f"File is not in the unmerged list: {rel_path}\n"
                f"Unmerged files: {', '.join(unmerged) if unmerged else '(none)'}"
            )

        # Write content if provided
        if content:
            full_path = str(resolved)
            parent = os.path.dirname(full_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        # Stage the resolved file
        if not self.git.run_ok("add", rel_path):
            raise BingoError(f"Failed to stage file: {rel_path}")

        # Check remaining unmerged files
        remaining = self.git.ls_files_unmerged()
        if remaining:
            # Still have unresolved files in this patch
            conflicts = [self._extract_conflict(f) for f in remaining]
            return {
                "ok": True,
                "resolved": rel_path,
                "remaining": remaining,
                "conflicts": [c.to_dict() for c in conflicts],
            }

        # All files resolved for this patch -- try to continue rebase
        env = os.environ.copy()
        env["GIT_EDITOR"] = "true"
        cont_result = subprocess.run(
            ["git", "rebase", "--continue"],
            cwd=self.path,
            capture_output=True,
            text=True,
            env=env,
        )

        if cont_result.returncode == 0:
            # Rebase may have completed or moved to next patch
            if self._in_rebase():
                # Next patch is being applied, check for new conflicts
                new_unmerged = self.git.ls_files_unmerged()
                if new_unmerged:
                    result = self._build_conflict_result(
                        new_unmerged,
                        resolved=rel_path,
                        rebase_continued=True,
                    )
                    result["ok"] = True
                    return result
                # No conflicts on next patch -- it applied cleanly
                # but rebase still in progress (more patches to go)
                return {
                    "ok": True,
                    "resolved": rel_path,
                    "rebase_continued": True,
                    "sync_complete": False,
                }
            # Rebase fully complete
            return {
                "ok": True,
                "resolved": rel_path,
                "rebase_continued": True,
                "sync_complete": True,
            }

        # rebase --continue failed -- check why
        new_unmerged = self.git.ls_files_unmerged()
        if new_unmerged:
            # Next patch triggered new conflicts
            result = self._build_conflict_result(
                new_unmerged,
                resolved=rel_path,
                rebase_continued=True,
            )
            result["ok"] = True
            return result

        # Failed for some other reason
        stderr = cont_result.stderr.strip()
        raise BingoError(
            f"git rebase --continue failed: {stderr or '(unknown error)'}"
        )

    # -- Sync --

    def sync(
        self,
        dry_run: bool = False,
        force: bool = False,
        test: bool = False,
    ) -> dict:
        """Fetch upstream and rebase patches.

        Args:
            dry_run: Preview only, don't modify anything
            force: Skip confirmation
            test: Run tests after sync; auto-undo on failure

        Returns sync result dict
        """
        c = self._load()
        if self._in_rebase():
            raise BingoError(
                "A rebase is already in progress. Resolve it first with "
                "'git rebase --continue' or 'git rebase --abort'."
            )
        self.state.acquire_lock()
        try:
            return self._sync_locked(c, dry_run, force, test)
        finally:
            self.state.release_lock()

    def _sync_locked(
        self, c: dict, dry_run: bool, force: bool, test: bool
    ) -> dict:
        self._ensure_clean()

        # 1. Fetch upstream
        if not self.git.fetch("upstream"):
            raise BingoError("Failed to fetch upstream.")

        # 2. Check how far behind
        tracking_head = self.git.rev_parse(c["tracking_branch"]) or ""
        upstream_head = (
            self.git.rev_parse(f"upstream/{c['upstream_branch']}") or ""
        )

        if tracking_head == upstream_head:
            return {
                "ok": True,
                "synced": True,
                "behind_before": 0,
                "patches_rebased": 0,
                "up_to_date": True,
            }

        behind = self.git.rev_list_count(
            f"{c['tracking_branch']}..upstream/{c['upstream_branch']}"
        )

        base = self._patches_base(c)
        patch_count = 0
        if base:
            patch_count = self.git.rev_list_count(f"{base}..{c['patches_branch']}")

        # 3. Dry run
        if dry_run:
            tmp_branch = f"bl-dryrun-{os.getpid()}"
            tmp_tracking = f"bl-dryrun-tracking-{os.getpid()}"
            try:
                self.git.run("branch", tmp_branch, c["patches_branch"])
                self.git.run(
                    "branch", tmp_tracking, f"upstream/{c['upstream_branch']}"
                )
                result = self.git.run_unchecked(
                    "rebase",
                    "--onto",
                    tmp_tracking,
                    c["tracking_branch"],
                    tmp_branch,
                )
                if result.returncode == 0:
                    return {
                        "ok": True,
                        "dry_run": True,
                        "clean": True,
                        "behind": behind,
                        "patches": patch_count,
                    }
                else:
                    conflicted = self.git.ls_files_unmerged()
                    self.git.run_ok("rebase", "--abort")
                    return {
                        "ok": True,
                        "dry_run": True,
                        "clean": False,
                        "behind": behind,
                        "patches": patch_count,
                        "conflicted_files": conflicted,
                    }
            finally:
                self.git.run_ok("checkout", c["patches_branch"])
                self.git.run_ok("branch", "-D", tmp_branch)
                self.git.run_ok("branch", "-D", tmp_tracking)

        # 4. Ensure we're on the patches branch
        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"])

        # 5. Save current state for rollback
        saved_head = self.git.rev_parse("HEAD")
        if not saved_head:
            raise BingoError("Cannot determine current HEAD. Aborting sync.")
        saved_tracking = self.git.rev_parse(c["tracking_branch"])
        if not saved_tracking:
            raise BingoError(
                f"Cannot resolve tracking branch '{c['tracking_branch']}'. "
                "Run 'bingo-light doctor' to diagnose."
            )
        self.state.save_undo(saved_head, saved_tracking)

        # 6. Update tracking branch
        self.git.run(
            "branch", "-f", c["tracking_branch"], f"upstream/{c['upstream_branch']}"
        )

        # 7. Rebase patches
        result = self.git.run_unchecked(
            "rebase",
            "--onto",
            c["tracking_branch"],
            saved_tracking,
            c["patches_branch"],
        )

        if result.returncode == 0:
            self._record_sync(c, behind, saved_tracking)
            self.state.run_hook(
                "on-sync-success",
                {"behind_before": behind, "patches_rebased": patch_count},
            )

            # Run tests if requested
            if test:
                try:
                    test_result = self.test()
                    if not test_result.get("ok"):
                        # Undo the sync -- restore both branches
                        try:
                            self.git.run(
                                "branch", "-f", c["patches_branch"], saved_head
                            )
                            if self.git.current_branch() == c["patches_branch"]:
                                self.git.run("reset", "--hard", saved_head)
                            self.git.run(
                                "branch", "-f",
                                c["tracking_branch"], saved_tracking,
                            )
                        except GitError:
                            # Rollback failed -- abort any in-progress rebase
                            self.git.run_ok("rebase", "--abort")
                        self.state.run_hook(
                            "on-test-fail", {"behind_before": behind}
                        )
                        return {
                            "ok": False,
                            "synced": False,
                            "test": "fail",
                            "auto_undone": True,
                        }
                except BingoError as e:
                    # Test command not configured or failed to run --
                    # sync succeeded but test was skipped
                    return {
                        "ok": True,
                        "synced": True,
                        "behind_before": behind,
                        "patches_rebased": patch_count,
                        "test": "skipped",
                        "test_error": str(e),
                    }

            return {
                "ok": True,
                "synced": True,
                "behind_before": behind,
                "patches_rebased": patch_count,
            }

        # Rebase failed -- check if rerere auto-resolved
        unresolved = self.git.ls_files_unmerged()
        if not unresolved:
            # rerere resolved everything -- try to continue
            rerere_ok = True
            rerere_iter = 0
            while self._in_rebase():
                rerere_iter += 1
                if rerere_iter > RERERE_MAX_ITER:
                    self.git.run_ok("rebase", "--abort")
                    raise BingoError(
                        "rerere auto-continue exceeded 50 iterations, aborting."
                    )
                env = os.environ.copy()
                env["GIT_EDITOR"] = "true"
                cont_result = subprocess.run(
                    ["git", "rebase", "--continue"],
                    cwd=self.path,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                if cont_result.returncode == 0:
                    break
                unresolved = self.git.ls_files_unmerged()
                if unresolved:
                    rerere_ok = False
                    break

            if rerere_ok:
                self._record_sync(c, behind, saved_tracking)
                self.state.run_hook(
                    "on-sync-success",
                    {
                        "behind_before": behind,
                        "patches_rebased": patch_count,
                        "rerere_resolved": True,
                    },
                )
                return {
                    "ok": True,
                    "synced": True,
                    "behind_before": behind,
                    "patches_rebased": patch_count,
                    "rerere_resolved": True,
                }

        # Rollback tracking branch
        self.git.run_ok("branch", "-f", c["tracking_branch"], saved_tracking)

        self.state.run_hook("on-conflict", {"patch_count": patch_count})

        conflicted_files = self.git.ls_files_unmerged()
        return self._build_conflict_result(
            conflicted_files,
            synced=False,
            next=(
                "Run bingo-light conflict-analyze --json to see conflict details, "
                "then resolve each file"
            ),
            tracking_restore=(
                f"git branch -f {c['tracking_branch']} {saved_tracking}"
            ),
        )

    def smart_sync(self) -> dict:
        """Smart sync: circuit breaker + auto-rerere + detailed conflict JSON.

        Returns sync result dict with detailed conflict information.
        """
        c = self._load()
        if self._in_rebase():
            raise BingoError(
                "A rebase is already in progress. Resolve it first with "
                "'git rebase --continue' or 'git rebase --abort'."
            )
        self.state.acquire_lock()
        try:
            return self._smart_sync_locked(c)
        finally:
            self.state.release_lock()

    def _smart_sync_locked(self, c: dict) -> dict:
        self._ensure_clean()

        # Circuit breaker check (pre-fetch)
        self.git.run_ok("fetch", "upstream")
        upstream_target = (
            self.git.rev_parse(f"upstream/{c['upstream_branch']}") or ""
        )
        if self.state.check_circuit_breaker(upstream_target):
            raise BingoError(
                "Circuit breaker: 3 consecutive sync failures on the same "
                "upstream commit. Resolve conflicts manually or wait for "
                "upstream to advance."
            )

        tracking_head = self.git.rev_parse(c["tracking_branch"]) or ""
        upstream_head = upstream_target

        if tracking_head == upstream_head:
            base = self._patches_base(c)
            patch_count = 0
            if base:
                patch_count = self.git.rev_list_count(
                    f"{base}..{c['patches_branch']}"
                )
            return {
                "ok": True,
                "action": "none",
                "message": "Already up to date.",
                "behind": 0,
                "patches": patch_count,
            }

        behind = self.git.rev_list_count(
            f"{c['tracking_branch']}..upstream/{c['upstream_branch']}"
        )
        base = self._patches_base(c)
        patch_count = 0
        if base:
            patch_count = self.git.rev_list_count(f"{base}..{c['patches_branch']}")

        # Save state for rollback
        saved_head = self.git.rev_parse("HEAD")
        if not saved_head:
            raise BingoError("Cannot determine current HEAD. Aborting smart-sync.")
        saved_tracking = self.git.rev_parse(c["tracking_branch"])
        if not saved_tracking:
            raise BingoError(
                f"Cannot resolve tracking branch '{c['tracking_branch']}'. "
                "Run 'bingo-light doctor' to diagnose."
            )
        self.state.save_undo(saved_head, saved_tracking)

        # Update tracking
        self.git.run(
            "branch", "-f", c["tracking_branch"], f"upstream/{c['upstream_branch']}"
        )
        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"])

        # Attempt rebase
        result = self.git.run_unchecked(
            "rebase",
            "--onto",
            c["tracking_branch"],
            saved_tracking,
            c["patches_branch"],
        )

        if result.returncode == 0:
            # Clean rebase
            self.state.clear_circuit_breaker()
            self._record_sync(c, behind, saved_tracking)
            return {
                "ok": True,
                "action": "synced",
                "behind_before": behind,
                "patches_rebased": patch_count,
                "conflicts_resolved": 0,
            }

        # Enter conflict resolution loop
        conflicts_resolved = 0
        resolve_iter = 0

        while self._in_rebase():
            resolve_iter += 1
            if resolve_iter > MAX_RESOLVE_ITER:
                self.git.run_ok("rebase", "--abort")
                self.git.run_ok("branch", "-f", c["tracking_branch"], saved_tracking)
                raise BingoError(
                    f"Smart sync: exceeded {MAX_RESOLVE_ITER} resolution attempts. Aborting."
                )

            unresolved = self.git.ls_files_unmerged()

            if not unresolved:
                # rerere resolved everything in this step
                env = os.environ.copy()
                env["GIT_EDITOR"] = "true"
                cont_result = subprocess.run(
                    ["git", "rebase", "--continue"],
                    cwd=self.path,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                if cont_result.returncode == 0:
                    conflicts_resolved += 1
                    continue
                # Continue failed -- check for new conflicts
                unresolved = self.git.ls_files_unmerged()
                if not unresolved:
                    continue

            # Real unresolved conflicts -- report and stop
            self.git.run_ok("branch", "-f", c["tracking_branch"], saved_tracking)

            # Circuit breaker: increment failure count
            self.state.record_circuit_breaker(upstream_target)

            result = self._build_conflict_result(
                unresolved,
                action="needs_human",
                behind_before=behind,
                conflicts_auto_resolved=conflicts_resolved,
                remaining_conflicts=[
                    self._extract_conflict(f).to_dict() for f in unresolved
                ],
                next=(
                    "For each conflict: read merge_hint, write merged file, "
                    "git add, git rebase --continue"
                ),
            )
            return result

        # If we get here, all conflicts were auto-resolved by rerere
        self.state.clear_circuit_breaker()
        self._record_sync(c, behind, saved_tracking)
        return {
            "ok": True,
            "action": "synced_with_rerere",
            "behind_before": behind,
            "patches_rebased": patch_count,
            "conflicts_auto_resolved": conflicts_resolved,
        }

    def undo(self) -> dict:
        """Undo the last sync operation.

        Returns {"ok": True, "restored_to": "..."}
        """
        c = self._load()
        self._ensure_clean()

        prev_head, prev_tracking = self.state.load_undo()

        if not prev_head:
            # Fallback to reflog
            try:
                output = self.git.run(
                    "reflog", c["patches_branch"], "--format=%H", "-2"
                )
                lines = output.splitlines()
                if len(lines) >= 2:
                    prev_head = lines[1]
            except GitError:
                pass

        if not prev_head:
            raise BingoError("No previous state found to undo. Have you synced yet?")

        current_head = self.git.rev_parse(c["patches_branch"])
        if not current_head:
            raise BingoError(
                f"Patch branch '{c['patches_branch']}' not found. "
                "Cannot determine current state."
            )
        if prev_head == current_head:
            return {"ok": True, "message": "nothing to undo"}

        # Restore patches branch
        if self.git.current_branch() == c["patches_branch"]:
            self.git.run("reset", "--hard", prev_head)
        else:
            self.git.run("branch", "-f", c["patches_branch"], prev_head)

        # Restore tracking branch
        if prev_tracking:
            self.git.run("branch", "-f", c["tracking_branch"], prev_tracking)
            self.state.clear_undo_tracking()

        # Mark undo active
        self.state.mark_undo_active()

        return {"ok": True, "restored_to": prev_head}

    # -- Patches --

    def patch_new(self, name: str, description: str = "") -> dict:
        """Create a new patch from current changes.

        Args:
            name: Patch name (alphanumeric, hyphens, underscores)
            description: Brief description

        Returns {"ok": True, "patch": "...", "hash": "...", "description": "..."}
        """
        c = self._load()
        self._validate_patch_name(name)

        # Check for duplicate patch name
        base = self._patches_base(c)
        if base:
            try:
                log_output = self.git.run(
                    "log", "--format=%s", f"{base}..{c['patches_branch']}"
                )
                for line in log_output.splitlines():
                    if f"{PATCH_PREFIX} {name}:" in line:
                        raise BingoError(
                            f"A patch named '{name}' already exists. "
                            "Use a different name or drop the existing one."
                        )
            except BingoError:
                raise  # re-raise duplicate name errors
            except GitError:
                pass  # git log failed (empty stack, etc.) -- safe to continue

        # Ensure on patches branch
        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"])

        # Check for changes
        has_staged = not self.git.run_ok("diff", "--cached", "--quiet")
        has_unstaged = not self.git.run_ok("diff", "--quiet")
        try:
            untracked = self.git.run(
                "ls-files", "--others", "--exclude-standard", check=False
            )
            has_untracked = bool(untracked.strip())
        except Exception:
            has_untracked = False

        if not has_staged and not has_unstaged and not has_untracked:
            raise BingoError("No changes to create a patch from. Make some changes first!")

        # If nothing is staged, stage everything
        if not has_staged:
            if has_unstaged or has_untracked:
                self.git.run("add", "-A")

        if not description:
            description = os.environ.get("BINGO_DESCRIPTION", "no description")

        commit_msg = f"{PATCH_PREFIX} {name}: {description}"
        self.git.run("commit", "-m", commit_msg)
        short_hash = self.git.rev_parse_short("HEAD")

        return {
            "ok": True,
            "patch": name,
            "hash": short_hash,
            "description": description,
        }

    def patch_list(self, verbose: bool = False) -> dict:
        """List all patches in the stack.

        Returns {"ok": True, "patches": [...], "count": N}
        """
        c = self._load()
        base = self._patches_base(c)
        if not base:
            return {"ok": True, "patches": [], "count": 0}

        patches = self.git.log_patches(base, c["patches_branch"])
        if not patches:
            return {"ok": True, "patches": [], "count": 0}

        result_patches = []
        for p in patches:
            entry: dict = {
                "name": p.name,
                "hash": p.hash,
                "subject": p.subject,
                "files": p.files,
                "stat": p.stat,
            }
            if verbose:
                # Include per-file details
                try:
                    file_output = self.git.run(
                        "diff-tree", "--no-commit-id", "--name-status", "-r",
                        p.hash, check=False,
                    )
                    file_details: List[str] = []
                    if file_output:
                        for line in file_output.splitlines():
                            parts = line.split("\t", 1)
                            if len(parts) == 2:
                                status_code = parts[0].strip()
                                fname = parts[1].strip()
                                prefix = {"M": "~", "A": "+", "D": "-"}.get(
                                    status_code, "?"
                                )
                                file_details.append(f"{prefix} {fname}")
                    entry["file_details"] = file_details
                except Exception:
                    entry["file_details"] = []
            result_patches.append(entry)

        return {
            "ok": True,
            "patches": result_patches,
            "count": len(result_patches),
        }

    def patch_show(self, target: str) -> dict:
        """Show full diff and stats for a specific patch.

        Returns {"ok": True, "patch": {...}} with truncation support.
        """
        c = self._load()
        hash_val = self._resolve_patch(c, target)

        short_hash = self.git.rev_parse_short(hash_val)
        subject = self.git.run("log", "-1", "--format=%s", hash_val)

        pname = ""
        m = re.match(r"^\[bl\] ([^:]+):", subject)
        if m:
            pname = m.group(1)

        stat = self.git.run(
            "diff-tree", "--no-commit-id", "--shortstat", hash_val, check=False
        ).strip()

        diff_content = self.git.run(
            "diff-tree", "--no-commit-id", "-p", hash_val, check=False
        )

        if len(diff_content) > MAX_DIFF_SIZE:
            preview = diff_content[:2000]
            size_kb = len(diff_content) // 1024
            return {
                "ok": True,
                "truncated": True,
                "patch": {
                    "name": pname,
                    "hash": short_hash,
                    "subject": subject,
                    "stat": stat,
                    "preview": preview,
                    "full_size": len(diff_content),
                    "message": (
                        f"Diff too large ({size_kb}KB). Showing preview."
                    ),
                },
            }

        return {
            "ok": True,
            "truncated": False,
            "patch": {
                "name": pname,
                "hash": short_hash,
                "subject": subject,
                "stat": stat,
                "diff": diff_content,
            },
        }

    def patch_drop(self, target: str) -> dict:
        """Remove a patch from the stack.

        Returns {"ok": True, "dropped": "...", "hash": "..."}
        """
        c = self._load()
        self._ensure_clean()
        hash_val = self._resolve_patch(c, target)

        subject = self.git.run("log", "-1", "--format=%s", hash_val)
        pname = ""
        m = re.match(r"^\[bl\] ([^:]+):", subject)
        if m:
            pname = m.group(1)

        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"])

        short_hash = self.git.rev_parse_short(hash_val)

        result = self.git.run_unchecked(
            "rebase", "--onto", f"{hash_val}^", hash_val, c["patches_branch"]
        )
        if result.returncode == 0:
            return {"ok": True, "dropped": pname, "hash": short_hash}
        else:
            self.git.run_ok("rebase", "--abort")
            raise BingoError(
                "Failed to drop patch. There may be dependencies between patches."
            )

    def patch_edit(self, target: str) -> dict:
        """Fold staged changes into an existing patch.

        Returns {"ok": True, "edited": "..."}
        """
        c = self._load()
        # Check for unstaged changes (staged are expected for patch edit)
        has_unstaged = not self.git.run_ok("diff", "--quiet")
        if has_unstaged:
            raise DirtyTreeError(
                "Unstaged changes detected. Stage the changes you want to fold "
                "into the patch with 'git add', or stash unstaged changes first."
            )
        hash_val = self._resolve_patch(c, target)

        has_staged = not self.git.run_ok("diff", "--cached", "--quiet")
        if not has_staged:
            raise BingoError(
                "No staged changes. Stage your fixes first with 'git add', "
                "then run this command."
            )

        subject = self.git.run("log", "-1", "--format=%s", hash_val)

        # Save HEAD before creating fixup commit (for rollback)
        pre_fixup_head = self.git.rev_parse("HEAD")

        # Create a fixup commit
        self.git.run("commit", f"--fixup={hash_val}")

        # Non-interactive rebase with autosquash
        base = self._patches_base(c)
        if not base:
            # Undo fixup commit
            if pre_fixup_head:
                self.git.run_ok("reset", "--hard", pre_fixup_head)
            raise BingoError("No patches base found.")

        env = os.environ.copy()
        env["GIT_SEQUENCE_EDITOR"] = "true"
        result = subprocess.run(
            ["git", "rebase", "--autosquash", base],
            cwd=self.path,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            self.git.run_ok("rebase", "--abort")
            # Remove orphaned fixup commit
            if pre_fixup_head:
                self.git.run_ok("reset", "--hard", pre_fixup_head)
            return {
                "ok": False,
                "error": "Rebase conflict while editing patch. Rebase aborted.",
            }

        return {"ok": True, "edited": subject}

    def patch_export(self, output_dir: str = ".bl-patches") -> dict:
        """Export all patches as .patch files + series file.

        Returns {"ok": True, "count": N, "directory": "...", "files": [...]}
        """
        c = self._load()
        base = self._patches_base(c)
        if not base:
            return {"ok": True, "count": 0, "patches": []}

        count = self.git.rev_list_count(f"{base}..{c['patches_branch']}")
        if count == 0:
            return {"ok": True, "count": 0, "patches": []}

        if os.path.isabs(output_dir):
            abs_output = os.path.realpath(output_dir)
        else:
            abs_output = os.path.realpath(os.path.join(self.path, output_dir))
            # For relative paths, ensure they stay within the repo
            if not abs_output.startswith(os.path.realpath(self.path)):
                raise BingoError(
                    f"Export path escapes repository: {output_dir}. "
                    "Use a path within the repo or an absolute path."
                )
        os.makedirs(abs_output, exist_ok=True)

        self.git.run(
            "format-patch",
            "--numbered",
            "--output-directory",
            abs_output,
            f"{base}..{c['patches_branch']}",
        )

        # Create series file
        patch_files = sorted(
            f for f in os.listdir(abs_output) if f.endswith(".patch")
        )
        with open(os.path.join(abs_output, "series"), "w") as f:
            for pf in patch_files:
                f.write(pf + "\n")

        return {
            "ok": True,
            "count": count,
            "directory": output_dir,
            "files": patch_files,
        }

    def _restore_bl_prefix(self) -> None:
        """Restore [bl] prefix on HEAD if git am stripped it."""
        try:
            subject = self.git.run("log", "-1", "--format=%s", "HEAD")
            if not subject.startswith(PATCH_PREFIX + " "):
                body = self.git.run("log", "-1", "--format=%B", "HEAD")
                subprocess.run(
                    ["git", "commit", "--amend", "-m", PATCH_PREFIX + " " + body],
                    cwd=self.path, capture_output=True, text=True,
                )
        except (GitError, OSError):
            pass

    def patch_import(self, path: str) -> dict:
        """Import .patch file(s) into the stack.

        Returns {"ok": True, "imported": True, "patch_count": N}
        """
        c = self._load()
        self._ensure_clean()

        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"])

        abs_path = os.path.realpath(
            os.path.join(self.path, path) if not os.path.isabs(path) else path
        )

        if os.path.isdir(abs_path):
            series_file = os.path.join(abs_path, "series")
            if os.path.isfile(series_file):
                with open(series_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        # Validate entry stays within the import directory
                        entry_path = os.path.realpath(
                            os.path.join(abs_path, line)
                        )
                        if not entry_path.startswith(abs_path):
                            raise BingoError(
                                f"Series entry escapes import directory: {line}"
                            )
                        result = self.git.run_unchecked("am", entry_path)
                        if result.returncode != 0:
                            raise BingoError(
                                f"Failed to apply {line}. "
                                "Run git am --abort to undo."
                            )
                        self._restore_bl_prefix()
            else:
                for pf in sorted(os.listdir(abs_path)):
                    if not pf.endswith(".patch"):
                        continue
                    result = self.git.run_unchecked(
                        "am", os.path.join(abs_path, pf)
                    )
                    if result.returncode != 0:
                        raise BingoError(
                            f"Failed to apply {pf}. Run git am --abort to undo."
                        )
                    self._restore_bl_prefix()
        else:
            if not os.path.isfile(abs_path):
                raise BingoError(f"File not found: {path}")
            result = self.git.run_unchecked("am", abs_path)
            if result.returncode != 0:
                raise BingoError(
                    "Failed to apply patch. Run git am --abort to undo."
                )
            self._restore_bl_prefix()

        base = self._patches_base(c)
        imported_count = 0
        if base:
            imported_count = self.git.rev_list_count(
                f"{base}..{c['patches_branch']}"
            )

        return {"ok": True, "imported": True, "patch_count": imported_count}

    def patch_reorder(self, order: str = "") -> dict:
        """Reorder patches by specifying new order as comma-separated indices.

        Args:
            order: e.g. "2,1,3" to swap first two patches

        Returns {"ok": True, "reordered": "..."}
        """
        c = self._load()
        self._ensure_clean()
        base = self._patches_base(c)
        if not base:
            return {"ok": True, "message": "no patches to reorder"}

        patch_total = self.git.rev_list_count(f"{base}..{c['patches_branch']}")
        if patch_total <= 1:
            return {"ok": True, "message": "only one patch"}

        if not order:
            raise BingoError(
                "Reorder requires --order \"2,1,3\" in non-interactive mode."
            )

        # Parse and validate indices
        try:
            indices = [int(x.strip()) for x in order.split(",")]
        except ValueError:
            raise BingoError("Invalid order format. Use comma-separated integers.")

        if len(indices) != patch_total:
            raise BingoError(
                f"Reorder requires exactly {patch_total} indices "
                f"(one per patch), got {len(indices)}."
            )

        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"])

        # Create a GIT_SEQUENCE_EDITOR script
        # Build sed-like reorder: read all pick lines, then emit in new order
        script_content = "#!/bin/bash\n"
        for i, idx in enumerate(indices):
            script_content += f'line{i}=$(sed -n "{idx}p" "$1")\n'
        for i in range(len(indices)):
            op = ">" if i == 0 else ">>"
            script_content += f'echo "$line{i}" {op} "$1.tmp"\n'
        script_content += 'mv "$1.tmp" "$1"\n'

        fd, script_path = tempfile.mkstemp(suffix=".sh")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = f"bash {script_path}"
            result = subprocess.run(
                ["git", "rebase", "-i", base],
                cwd=self.path,
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode == 0:
                return {"ok": True, "reordered": order}
            else:
                self.git.run_ok("rebase", "--abort")
                raise BingoError("Failed to reorder patches.")
        finally:
            try:
                os.unlink(script_path)
            except FileNotFoundError:
                pass

    def patch_squash(self, idx1: int, idx2: int) -> dict:
        """Merge two adjacent patches into one.

        Args:
            idx1: 1-based index of first patch
            idx2: 1-based index of second patch (must be adjacent to idx1)

        Returns {"ok": True, "squashed": [idx1, idx2]}
        """
        c = self._load()
        self._ensure_clean()

        base = self._patches_base(c)
        if not base:
            raise BingoError("No patches.")

        total = self.git.rev_list_count(f"{base}..{c['patches_branch']}")
        if not (1 <= idx1 <= total):
            raise BingoError(f"Index out of range: {idx1} (1-{total})")
        if not (1 <= idx2 <= total):
            raise BingoError(f"Index out of range: {idx2} (1-{total})")
        if idx1 == idx2:
            raise BingoError("Cannot squash a patch with itself.")

        if self.git.current_branch() != c["patches_branch"]:
            self.git.run("checkout", c["patches_branch"])

        # Create GIT_SEQUENCE_EDITOR that changes line idx2 to squash
        script_content = (
            f'#!/bin/bash\n'
            f'awk \'NR=={idx2} && /^pick/{{sub(/^pick/,"squash")}} {{print}}\' '
            f'"$1" > "$1.tmp" && mv "$1.tmp" "$1"\n'
        )

        fd, script_path = tempfile.mkstemp(suffix=".sh")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = script_path
            result = subprocess.run(
                ["git", "rebase", "-i", base],
                cwd=self.path,
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode == 0:
                return {"ok": True, "squashed": [idx1, idx2]}
            else:
                self.git.run_ok("rebase", "--abort")
                raise BingoError("Failed to squash patches.")
        finally:
            try:
                os.unlink(script_path)
            except FileNotFoundError:
                pass

    def patch_meta(
        self, target: str, key: str = "", value: str = ""
    ) -> dict:
        """Get/set patch metadata.

        If key is empty, return all metadata.
        If key is set but value is empty, return that key's value.
        If both key and value are set, set the value.

        Returns {"ok": True, ...}
        """
        c = self._load()

        # Verify patch exists
        base = self._patches_base(c)
        if base:
            try:
                log_output = self.git.run(
                    "log", "--format=%s", f"{base}..{c['patches_branch']}"
                )
                found = False
                for line in log_output.splitlines():
                    if f"{PATCH_PREFIX} {target}:" in line:
                        found = True
                        break
                if not found:
                    raise BingoError(f"Patch '{target}' not found.")
            except GitError:
                raise BingoError(f"Patch '{target}' not found.")

        if not key:
            # Return all metadata
            meta = self.state.patch_meta_get(target)
            return {"ok": True, "patch": target, "meta": meta}

        if not value:
            # Get specific key
            meta = self.state.patch_meta_get(target)
            return {"ok": True, "patch": target, "key": key, "value": meta.get(key, "")}

        # Set value
        self.state.patch_meta_set(target, key, value)
        return {"ok": True, "patch": target, "set": key, "value": value}

    # -- Config --

    def config_get(self, key: str) -> dict:
        """Get a config value.

        Returns {"ok": True, "key": "...", "value": "..."}
        """
        self._load()  # ensure initialized
        val = self.config.get(key) or ""
        return {"ok": True, "key": key, "value": val}

    def config_set(self, key: str, value: str) -> dict:
        """Set a config value.

        Returns {"ok": True, "key": "...", "value": "..."}
        """
        self._load()  # ensure initialized
        self.config.set(key, value)
        return {"ok": True, "key": key, "value": value}

    def config_list(self) -> dict:
        """List all config values.

        Returns {"ok": True, "config": {...}}
        """
        self._load()  # ensure initialized
        return {"ok": True, "config": self.config.list_all()}

    # -- Other --

    def test(self) -> dict:
        """Run configured test command.

        Returns {"ok": True/False, "test": "pass"/"fail", "command": "..."}
        """
        self._load()  # validate repo is initialized
        test_cmd = self.config.get("test.command")
        if not test_cmd:
            raise BingoError(
                "No test command. Set one with: bingo-light config set test.command 'make test'"
            )

        try:
            result = subprocess.run(
                ["bash", "-c", test_cmd],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute limit
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "test": "timeout", "command": test_cmd}
        if result.returncode == 0:
            return {"ok": True, "test": "pass", "command": test_cmd}
        else:
            return {
                "ok": False,
                "test": "fail",
                "command": test_cmd,
                "output": result.stdout + result.stderr,
            }

    def auto_sync(self, schedule: str = "daily") -> dict:
        """Generate GitHub Actions workflow YAML for automated sync.

        Returns {"ok": True, "workflow": "...", "schedule": "..."}
        """
        c = self._load()

        cron_map = {
            "6h": ("0 */6 * * *", "every 6 hours"),
            "weekly": ("0 0 * * 1", "weekly (Monday)"),
            "daily": ("0 0 * * *", "daily"),
        }
        cron_schedule, schedule_desc = cron_map.get(
            schedule, cron_map["daily"]
        )

        output_dir = os.path.join(self.path, ".github", "workflows")
        output_file = os.path.join(output_dir, "bingo-light-sync.yml")
        os.makedirs(output_dir, exist_ok=True)

        # Sanitize config values for shell safety in YAML
        url = shlex.quote(c["upstream_url"])
        tb = shlex.quote(c["tracking_branch"])
        ub = shlex.quote(c["upstream_branch"])
        pb = shlex.quote(c["patches_branch"])

        # Validate branch names (no shell metacharacters)
        _branch_re = re.compile(r"^[a-zA-Z0-9._/-]+$")
        for name, val in [("tracking_branch", c["tracking_branch"]),
                          ("upstream_branch", c["upstream_branch"]),
                          ("patches_branch", c["patches_branch"])]:
            if not _branch_re.match(val):
                raise BingoError(
                    f"Unsafe characters in {name}: {val!r}. "
                    "Branch names must be alphanumeric with . / _ - only."
                )

        workflow = f"""# Generated by bingo-light
# Automatically syncs your fork with upstream and rebases patches.
# On failure, creates a GitHub Issue to notify you.

name: Bingo Light Auto-Sync

on:
  schedule:
    - cron: '{cron_schedule}'
  workflow_dispatch:  # Manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      issues: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Configure Git
        run: |
          git config user.name "bingo-light[bot]"
          git config user.email "bingo-light[bot]@users.noreply.github.com"

      - name: Fetch upstream
        run: |
          git remote add upstream {url} || git remote set-url upstream {url}
          git fetch upstream

      - name: Rebase patches
        id: rebase
        run: |
          SAVED_TRACKING=$(git rev-parse {tb})
          git branch -f {tb} upstream/{ub}
          git checkout {pb}
          if git rebase --onto {tb} $SAVED_TRACKING {pb} 2>&1; then
            echo "result=success" >> $GITHUB_OUTPUT
          else
            git rebase --abort || true
            echo "result=conflict" >> $GITHUB_OUTPUT
          fi

      - name: Push if successful
        if: steps.rebase.outputs.result == 'success'
        run: |
          git push origin {pb} --force-with-lease
          git push origin {tb} --force-with-lease

      - name: Create issue on conflict
        if: steps.rebase.outputs.result == 'conflict'
        uses: actions/github-script@v7
        with:
          script: |
            const title = `[bingo-light] Sync conflict detected (${{new Date().toISOString().split('T')[0]}})`;
            const body = `## Auto-sync failed\\n\\nUpstream has changes that conflict with your patches.\\n\\n**Action required:** Run \\`bingo-light sync\\` locally to resolve conflicts.\\n\\n---\\n*This issue was created automatically by bingo-light.*`;
            await github.rest.issues.create({{
              owner: context.repo.owner,
              repo: context.repo.repo,
              title,
              body,
              labels: ['bingo-light', 'sync-conflict']
            }});
"""

        with open(output_file, "w") as f:
            f.write(workflow)

        return {
            "ok": True,
            "workflow": ".github/workflows/bingo-light-sync.yml",
            "schedule": schedule_desc,
        }

    @staticmethod
    def _workspace_config_path() -> str:
        config_dir = os.environ.get(
            "XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")
        )
        return os.path.join(config_dir, "bingo-light", "workspace.json")

    @staticmethod
    def _load_workspace(config_path: str) -> dict:
        """Load workspace.json safely, handling corruption."""
        try:
            with open(config_path) as f:
                data = json.load(f)
            if not isinstance(data, dict) or "repos" not in data:
                return {"repos": []}
            return data
        except (json.JSONDecodeError, IOError):
            return {"repos": []}

    def workspace_init(self) -> dict:
        """Initialize workspace config."""
        workspace_config = self._workspace_config_path()
        os.makedirs(os.path.dirname(workspace_config), exist_ok=True)
        if not os.path.isfile(workspace_config):
            with open(workspace_config, "w") as f:
                json.dump({"repos": []}, f)
        return {"ok": True, "workspace": workspace_config}

    def workspace_add(
        self, repo_path: str = "", alias: str = ""
    ) -> dict:
        """Add a repo to workspace."""
        workspace_config = self._workspace_config_path()
        if not os.path.isfile(workspace_config):
            raise BingoError("Run 'bingo-light workspace init' first.")

        repo_path = repo_path or self.path
        repo_path = os.path.realpath(repo_path)
        alias = alias or os.path.basename(repo_path)

        # Validate the path is a git repo
        if not os.path.isdir(repo_path):
            raise BingoError(f"Directory not found: {repo_path}")
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            raise BingoError(f"Not a git repository: {repo_path}")

        data = self._load_workspace(workspace_config)
        repos = data.setdefault("repos", [])

        # Check for duplicate path or alias
        for r in repos:
            if r.get("path") == repo_path:
                raise BingoError(f"Repo already in workspace: {repo_path}")
            if r.get("alias") == alias:
                raise BingoError(
                    f"Alias '{alias}' already in use. Use a different alias."
                )

        repos.append({"path": repo_path, "alias": alias})

        with open(workspace_config, "w") as f:
            json.dump(data, f, indent=2)

        return {"ok": True, "added": alias, "path": repo_path}

    def workspace_list(self) -> dict:
        """List workspace repos."""
        workspace_config = self._workspace_config_path()
        if not os.path.isfile(workspace_config):
            raise BingoError("No workspace. Run 'bingo-light workspace init'.")

        data = self._load_workspace(workspace_config)
        return {"ok": True, "repos": data.get("repos", [])}

    def workspace_status(self) -> dict:
        """List workspace repos with per-repo sync status."""
        workspace_config = self._workspace_config_path()
        if not os.path.isfile(workspace_config):
            raise BingoError("No workspace. Run 'bingo-light workspace init'.")

        data = self._load_workspace(workspace_config)
        repos = []
        for r in data.get("repos", []):
            alias = r.get("alias", r.get("path", "unknown"))
            path = r.get("path", "")
            entry: dict = {"alias": alias, "path": path}
            if not path or not os.path.isdir(path):
                entry["status"] = "missing"
                repos.append(entry)
                continue
            try:
                sub = Repo(path)
                st = sub.status()
                entry["behind"] = st.get("behind", 0)
                entry["patches"] = st.get("patch_count", 0)
                entry["status"] = "ok" if st.get("up_to_date") else "behind"
            except (BingoError, OSError) as e:
                entry["status"] = "error"
                entry["error"] = str(e)
            repos.append(entry)
        return {"ok": True, "repos": repos}

    def workspace_sync(self) -> dict:
        """Sync all workspace repos."""
        workspace_config = self._workspace_config_path()
        if not os.path.isfile(workspace_config):
            raise BingoError("No workspace.")

        data = self._load_workspace(workspace_config)

        results = []
        for r in data.get("repos", []):
            alias = r.get("alias", r.get("path", "unknown"))
            path = r.get("path", "")
            if not path or not os.path.isdir(path):
                results.append({
                    "alias": alias, "status": "failed",
                    "error": f"Directory not found: {path}",
                })
                continue
            try:
                repo = Repo(path)
                repo.sync(force=True)
                results.append({"alias": alias, "status": "ok"})
            except (BingoError, OSError) as e:
                status = "conflict" if "conflict" in str(e).lower() else "failed"
                results.append({
                    "alias": alias, "status": status, "error": str(e),
                })

        all_ok = all(r["status"] == "ok" for r in results)
        return {"ok": all_ok, "synced": results}

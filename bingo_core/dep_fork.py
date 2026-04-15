"""
bingo_core.dep_fork — Fork-as-dependency tracking for npm projects.

Scans package.json for git-based dependencies (github:user/repo, git+https://,
etc.), detects drift from upstream releases, and updates fork refs.

Python 3.8+ stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


# Git dependency patterns in package.json
_GIT_DEP_PATTERNS = [
    re.compile(r'^github:(.+)$'),                          # github:user/repo#ref
    re.compile(r'^git\+https?://github\.com/(.+?)(?:\.git)?(?:#(.+))?$'),  # git+https://
    re.compile(r'^git\+ssh://git@github\.com[:/](.+?)(?:\.git)?(?:#(.+))?$'),  # git+ssh://
    re.compile(r'^([a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+)(?:#(.+))?$'),  # user/repo shorthand
]


class ForkTracker:
    """Track git-based dependencies in npm projects."""

    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)

    def _read_package_json(self) -> Optional[dict]:
        pj = os.path.join(self.cwd, "package.json")
        if not os.path.isfile(pj):
            return None
        try:
            with open(pj) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _write_package_json(self, data: dict) -> None:
        pj = os.path.join(self.cwd, "package.json")
        fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=self.cwd)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, pj)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def _parse_git_dep(self, value: str) -> Optional[dict]:
        """Parse a git-based dependency value. Returns {repo, ref, protocol} or None."""
        for pat in _GIT_DEP_PATTERNS:
            m = pat.match(value)
            if m:
                groups = m.groups()
                repo_part = groups[0]
                ref = groups[1] if len(groups) > 1 and groups[1] else ""

                # Handle github:user/repo#ref
                if "#" in repo_part:
                    repo_part, ref = repo_part.split("#", 1)

                # Normalize repo
                repo_part = repo_part.rstrip("/")

                return {"repo": repo_part, "ref": ref, "raw": value}
        return None

    def _fetch_json(self, url: str) -> Optional[dict]:
        """Fetch JSON from URL with timeout and error handling."""
        headers = {"Accept": "application/json", "User-Agent": "bingo-light"}
        # Use GITHUB_TOKEN if available
        token = os.environ.get("GITHUB_TOKEN", "")
        if token and "github" in url:
            headers["Authorization"] = f"token {token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                # Check GitHub rate limit
                remaining = resp.headers.get("X-RateLimit-Remaining", "")
                if remaining and int(remaining) <= 1:
                    import sys
                    print(
                        "warning: GitHub API rate limit nearly exhausted. "
                        "Set GITHUB_TOKEN env var for higher limits.",
                        file=sys.stderr,
                    )
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
                OSError, ValueError):
            return None

    @staticmethod
    def _is_sha_like(ref: str) -> bool:
        """Check if a ref looks like a commit SHA (hex string, 7+ chars)."""
        return len(ref) >= 7 and all(c in "0123456789abcdef" for c in ref.lower())

    def fork_list(self) -> dict:
        """List all git-based dependencies in package.json.

        Returns {"ok": True, "forks": [...], "count": N}
        """
        pj = self._read_package_json()
        if pj is None:
            return {"ok": True, "forks": [], "count": 0, "note": "No package.json"}

        forks: List[dict] = []
        for dep_type in ("dependencies", "devDependencies"):
            deps = pj.get(dep_type, {})
            for name, value in deps.items():
                if not isinstance(value, str):
                    continue
                parsed = self._parse_git_dep(value)
                if parsed:
                    forks.append({
                        "package": name,
                        "repo": parsed["repo"],
                        "ref": parsed["ref"],
                        "dep_type": dep_type,
                        "raw": parsed["raw"],
                    })

        return {"ok": True, "forks": forks, "count": len(forks)}

    def fork_check(self) -> dict:
        """Check fork drift against upstream npm releases and GitHub commits.

        Returns {"ok": True, "forks": [...], "drifted": N}
        """
        list_result = self.fork_list()
        forks = list_result.get("forks", [])
        if not forks:
            return {"ok": True, "forks": [], "drifted": 0}

        results: List[dict] = []
        drifted = 0

        for fork in forks:
            entry: Dict[str, Any] = {
                "package": fork["package"],
                "repo": fork["repo"],
                "ref": fork["ref"],
            }

            # Check npm registry for latest published version
            npm_url = f"https://registry.npmjs.org/{fork['package']}/latest"
            npm_data = self._fetch_json(npm_url)
            if npm_data:
                entry["npm_latest"] = npm_data.get("version", "")
            else:
                entry["npm_latest"] = ""

            # Check GitHub for latest commit on default branch
            gh_url = f"https://api.github.com/repos/{fork['repo']}/commits?per_page=1"
            gh_data = self._fetch_json(gh_url)
            if gh_data and isinstance(gh_data, list) and len(gh_data) > 0:
                latest_sha = gh_data[0].get("sha", "")[:12]
                entry["latest_commit"] = latest_sha
                entry["commit_date"] = gh_data[0].get("commit", {}).get(
                    "committer", {}
                ).get("date", "")

                # Compare ref — handle SHA, tag, and branch refs
                ref = fork["ref"]
                if not ref:
                    entry["status"] = "no_ref_pinned"
                elif self._is_sha_like(ref):
                    # ref looks like a commit SHA — compare directly
                    if latest_sha.startswith(ref[:8]) or ref.startswith(latest_sha[:8]):
                        entry["status"] = "up_to_date"
                    else:
                        entry["status"] = "drifted"
                        drifted += 1
                else:
                    # ref is a tag or branch name — resolve via GitHub API
                    ref_url = f"https://api.github.com/repos/{fork['repo']}/git/ref/tags/{ref}"
                    ref_data = self._fetch_json(ref_url)
                    if not ref_data:
                        # Try as branch
                        ref_url = f"https://api.github.com/repos/{fork['repo']}/git/ref/heads/{ref}"
                        ref_data = self._fetch_json(ref_url)
                    if ref_data and isinstance(ref_data, dict):
                        ref_sha = ref_data.get("object", {}).get("sha", "")[:12]
                        if ref_sha and (latest_sha.startswith(ref_sha[:8]) or ref_sha.startswith(latest_sha[:8])):
                            entry["status"] = "up_to_date"
                        else:
                            entry["status"] = "drifted"
                            entry["ref_resolved"] = ref_sha
                            drifted += 1
                    else:
                        # Can't resolve ref — report as unknown
                        entry["status"] = "unknown"
                        entry["note"] = f"Cannot resolve ref '{ref}'"
            else:
                entry["latest_commit"] = ""
                entry["status"] = "unknown"

            results.append(entry)

        return {"ok": True, "forks": results, "drifted": drifted}

    def fork_sync(self, package: str) -> dict:
        """Update a fork dependency ref to the latest commit.

        Returns {"ok": True, "package": ..., "old_ref": ..., "new_ref": ...}
        """
        pj = self._read_package_json()
        if pj is None:
            return {"ok": False, "error": "No package.json found"}

        # Find the package
        found_type = None
        old_value = None
        for dep_type in ("dependencies", "devDependencies"):
            deps = pj.get(dep_type, {})
            if package in deps:
                found_type = dep_type
                old_value = deps[package]
                break

        if not found_type or not isinstance(old_value, str):
            return {"ok": False, "error": f"Package '{package}' not found in dependencies"}

        parsed = self._parse_git_dep(old_value)
        if not parsed:
            return {"ok": False, "error": f"'{package}' is not a git-based dependency"}

        old_ref = parsed["ref"]

        # Fetch latest commit from GitHub
        gh_url = f"https://api.github.com/repos/{parsed['repo']}/commits?per_page=1"
        gh_data = self._fetch_json(gh_url)
        if not gh_data or not isinstance(gh_data, list) or len(gh_data) == 0:
            return {"ok": False, "error": f"Cannot fetch latest commit for {parsed['repo']}"}

        new_ref = gh_data[0].get("sha", "")[:12]
        if not new_ref:
            return {"ok": False, "error": "Empty commit SHA from GitHub"}

        # Update the dependency value
        if "#" in old_value:
            new_value = old_value.rsplit("#", 1)[0] + "#" + new_ref
        else:
            new_value = old_value + "#" + new_ref

        pj[found_type][package] = new_value
        self._write_package_json(pj)

        return {
            "ok": True,
            "package": package,
            "old_ref": old_ref,
            "new_ref": new_ref,
            "old_value": old_value,
            "new_value": new_value,
        }

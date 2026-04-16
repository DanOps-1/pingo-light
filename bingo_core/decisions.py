"""
bingo_core.decisions — per-patch conflict-resolution memory.

Complements git rerere (which keys by literal conflict text) with a
pattern-level memory: records how patch X was resolved against upstream
commit Y, keyed by (patch_name, file, semantic_class). When the same
patch conflicts again in a similar pattern, previous decisions are
surfaced to the AI during conflict-analyze so it can consider the
prior choice.

Storage: .bingo/decisions/<patch-name>.json, one file per patch.
This avoids hot contention and keeps each patch's history isolated.

Python 3.8+ stdlib only. No external dependencies.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import List, Optional

# Patch name constraint mirrors PATCH_NAME_RE to keep filenames safe.
_SAFE_PATCH_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
MAX_DECISIONS_PER_PATCH = 50


class DecisionMemory:
    """Per-patch decision log stored under .bingo/decisions/."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.dir = os.path.join(repo_path, ".bingo", "decisions")

    def _path_for(self, patch_name: str) -> Optional[str]:
        if not patch_name or not _SAFE_PATCH_NAME.match(patch_name):
            return None
        return os.path.join(self.dir, f"{patch_name}.json")

    def _load_all(self, patch_name: str) -> List[dict]:
        path = self._path_for(patch_name)
        if not path or not os.path.isfile(path):
            return []
        try:
            with open(path) as f:
                data = json.load(f)
        except (IOError, OSError, json.JSONDecodeError):
            return []
        decisions = data.get("decisions", [])
        return decisions if isinstance(decisions, list) else []

    def _save_all(self, patch_name: str, decisions: List[dict]) -> None:
        path = self._path_for(patch_name)
        if not path:
            return
        os.makedirs(self.dir, exist_ok=True)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(
                    {"patch": patch_name, "decisions": decisions},
                    f, indent=2,
                )
            os.replace(tmp, path)
        except (IOError, OSError):
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def record(
        self,
        patch_name: str,
        file: str,
        semantic_class: str,
        resolution_strategy: str,
        upstream_sha: Optional[str] = None,
        upstream_subject: Optional[str] = None,
        notes: str = "",
    ) -> None:
        """Append one decision for a patch.

        Silently no-ops if patch_name is empty or invalid. The newest
        MAX_DECISIONS_PER_PATCH entries are retained; older entries are
        dropped FIFO to keep files bounded.
        """
        if not patch_name or not _SAFE_PATCH_NAME.match(patch_name):
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "file": file,
            "semantic_class": semantic_class,
            "resolution_strategy": resolution_strategy,
            "upstream_sha": upstream_sha,
            "upstream_subject": upstream_subject,
            "notes": notes,
        }
        decisions = self._load_all(patch_name)
        decisions.append(entry)
        if len(decisions) > MAX_DECISIONS_PER_PATCH:
            decisions = decisions[-MAX_DECISIONS_PER_PATCH:]
        self._save_all(patch_name, decisions)

    def lookup(
        self,
        patch_name: str,
        file: Optional[str] = None,
        semantic_class: Optional[str] = None,
        limit: int = 5,
    ) -> List[dict]:
        """Return up to `limit` previous decisions, most-recent first,
        ranked by relevance to the given file/semantic_class.

        Ranking: +2 if file matches, +1 if semantic_class matches.
        Ties broken by recency.
        """
        decisions = self._load_all(patch_name)
        if not decisions:
            return []

        def score(d: dict) -> tuple:
            relevance = 0
            if file and d.get("file") == file:
                relevance += 2
            if semantic_class and d.get("semantic_class") == semantic_class:
                relevance += 1
            return (relevance, d.get("timestamp", ""))

        ranked = sorted(decisions, key=score, reverse=True)
        result = []
        for d in ranked[:limit]:
            # Add a human-readable relevance tag
            tag = []
            if file and d.get("file") == file:
                tag.append("same_file")
            if semantic_class and d.get("semantic_class") == semantic_class:
                tag.append("same_class")
            entry = dict(d)
            entry["relevance"] = "+".join(tag) if tag else "recent"
            result.append(entry)
        return result


def detect_resolution_strategy(
    resolved_content: str, ours: str, theirs: str
) -> str:
    """Classify how a resolution was produced by comparing bytes.

    Returns "keep_ours" / "keep_theirs" / "manual". Exact-match required
    because partial merges still count as manual. Empty `resolved_content`
    returns "manual" (caller didn't tell us what was written).
    """
    if not resolved_content:
        return "manual"
    # Strip trailing whitespace on both sides to be forgiving of newline diffs.
    r = resolved_content.rstrip()
    o = (ours or "").rstrip()
    t = (theirs or "").rstrip()
    if r == o:
        return "keep_ours"
    if r == t:
        return "keep_theirs"
    return "manual"

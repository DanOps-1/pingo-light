"""
bingo_core.models — Data classes for bingo-light.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class PatchInfo:
    """Information about a single patch in the stack."""

    name: str
    hash: str
    subject: str
    files: int = 0
    stat: str = ""
    insertions: int = 0
    deletions: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConflictInfo:
    """Information about a conflict in a single file."""

    file: str
    ours: str = ""
    theirs: str = ""
    conflict_count: int = 0
    merge_hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

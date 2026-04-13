"""
bingo_core — Complete Python core library for bingo-light.

AI-native fork maintenance: manages customizations as a clean patch stack
on top of upstream. Every public method returns a dict with {"ok": True, ...}
or raises BingoError.

Python 3.8+ stdlib only. No pip dependencies.
"""

from __future__ import annotations

import re

# --- Constants ---

VERSION = "2.1.1"
PATCH_PREFIX = "[bl]"
CONFIG_FILE = ".bingolight"
BINGO_DIR = ".bingo"
DEFAULT_TRACKING = "upstream-tracking"
DEFAULT_PATCHES = "bingo-patches"
MAX_PATCHES = 100
MAX_DIFF_SIZE = 50000
PATCH_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
PATCH_NAME_MAX = 100
CIRCUIT_BREAKER_LIMIT = 3
RERERE_MAX_ITER = 50
MAX_RESOLVE_ITER = 20
SYNC_HISTORY_MAX = 50

# --- Re-exports (keep `from bingo_core import X` working) ---

from bingo_core.exceptions import (  # noqa: E402
    BingoError,
    GitError,
    NotGitRepoError,
    NotInitializedError,
    DirtyTreeError,
)
from bingo_core.models import PatchInfo, ConflictInfo  # noqa: E402
from bingo_core.git import Git  # noqa: E402
from bingo_core.config import Config  # noqa: E402
from bingo_core.state import State  # noqa: E402
from bingo_core.repo import Repo  # noqa: E402

__all__ = [
    # Constants
    "VERSION",
    "PATCH_PREFIX",
    "CONFIG_FILE",
    "BINGO_DIR",
    "DEFAULT_TRACKING",
    "DEFAULT_PATCHES",
    "MAX_PATCHES",
    "MAX_DIFF_SIZE",
    "PATCH_NAME_RE",
    "PATCH_NAME_MAX",
    "CIRCUIT_BREAKER_LIMIT",
    "RERERE_MAX_ITER",
    "MAX_RESOLVE_ITER",
    "SYNC_HISTORY_MAX",
    # Exceptions
    "BingoError",
    "GitError",
    "NotGitRepoError",
    "NotInitializedError",
    "DirtyTreeError",
    # Data classes
    "PatchInfo",
    "ConflictInfo",
    # Classes
    "Git",
    "Config",
    "State",
    "Repo",
]

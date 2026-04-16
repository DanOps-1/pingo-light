"""
bingo_core.semantic — semantic classification of conflict regions.

Given ours/theirs text for a single conflict region, return one of:
    "whitespace"       — regions differ only in whitespace
    "import_reorder"   — both regions are only import statements,
                         same set of imports, just reordered
    "signature_change" — function/method signature changed (params
                         added, removed, or renamed) but name same
    "logic"            — default; real logic change requiring human
                         or AI reasoning

The classifier is intentionally conservative: when unsure, return
"logic" so callers treat it as a real conflict.

Python 3.8+ stdlib only.
"""

from __future__ import annotations

import re

# Matches Python "import X" or "from X import Y" lines.
_IMPORT_RE_PY = re.compile(r"^\s*(?:import|from)\s+\S")
# Matches JS/TS imports and CommonJS require.
_IMPORT_RE_JS = re.compile(r"^\s*(?:import\s|const\s+\w+\s*=\s*require\()")

# Function signature captures: (name, params) for Python def and JS function.
_FN_SIG_PY = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)")
_FN_SIG_JS = re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)")


def classify_conflict(ours: str, theirs: str, file: str = "") -> str:
    """Classify a conflict region as whitespace / import_reorder /
    signature_change / logic.

    `file` is accepted for future extension (language-specific rules)
    but not currently used.
    """
    if _is_whitespace_only(ours, theirs):
        return "whitespace"
    if _is_import_reorder(ours, theirs):
        return "import_reorder"
    if _is_signature_change(ours, theirs):
        return "signature_change"
    return "logic"


def _is_whitespace_only(a: str, b: str) -> bool:
    """True if the only difference is whitespace (tabs, spaces, newlines).

    All whitespace is removed for comparison — matching git's
    `diff --ignore-all-space` semantics.
    """
    na = "".join(a.split())
    nb = "".join(b.split())
    return na == nb and na != ""


def _is_import_reorder(a: str, b: str) -> bool:
    """True if both sides contain only import statements, with the same
    set of imports (just reordered)."""
    a_lines = [ln for ln in a.splitlines() if ln.strip()]
    b_lines = [ln for ln in b.splitlines() if ln.strip()]
    if not a_lines or not b_lines:
        return False
    for line in a_lines + b_lines:
        if not (_IMPORT_RE_PY.match(line) or _IMPORT_RE_JS.match(line)):
            return False
    # Compare as sorted sets: order-insensitive match.
    return sorted(a_lines) == sorted(b_lines)


def _is_signature_change(a: str, b: str) -> bool:
    """True if both sides contain a function definition for the same
    name but with different parameter lists."""
    for pattern in (_FN_SIG_PY, _FN_SIG_JS):
        a_match = pattern.search(a)
        b_match = pattern.search(b)
        if a_match and b_match:
            same_name = a_match.group(1) == b_match.group(1)
            different_params = a_match.group(2).strip() != b_match.group(2).strip()
            if same_name and different_params:
                return True
    return False

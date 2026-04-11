#!/usr/bin/env python3
"""
bingo-light TUI — Terminal dashboard for fork maintenance.

Reads status from bingo-light --json and displays a real-time overview.
Supports both single-repo and workspace (multi-repo) modes.

Usage:
  python3 tui.py                         # current directory
  python3 tui.py --cwd /path/to/repo     # specific repo
  python3 tui.py --workspace             # all workspace repos

Keys:
  s  sync current repo     d  dry-run sync     r  refresh
  j/k  navigate repos      q  quit
"""

from __future__ import annotations

import curses
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BL = os.environ.get("BINGO_LIGHT_BIN", str(Path(__file__).parent / "bingo-light"))


def run_bl(args, cwd="."):
    try:
        result = subprocess.run(
            [BL, "--json", "--yes"] + args,
            cwd=cwd, capture_output=True, text=True, timeout=30,
            env={**os.environ, "NO_COLOR": "1"},
        )
        return json.loads(result.stdout) if result.stdout.strip() else {"ok": False}
    except Exception:
        return {"ok": False, "error": "command failed"}


def get_workspace_repos():
    config = os.path.expanduser("~/.config/bingo-light/workspace.json")
    if not os.path.exists(config):
        return []
    with open(config) as f:
        data = json.load(f)
    return data.get("repos", [])


def draw_header(win, y, text, width):
    win.attron(curses.A_BOLD)
    win.addnstr(y, 0, text.center(width), width)
    win.attroff(curses.A_BOLD)


def draw_repo_status(win, y, status, alias="", selected=False):
    height, width = win.getmaxyx()
    if y >= height - 1:
        return y

    attr = curses.A_REVERSE if selected else 0

    behind = status.get("behind", "?")
    patches = status.get("patch_count", "?")
    up_to_date = status.get("up_to_date", False)
    risk = status.get("conflict_risk", [])
    branch = status.get("current_branch", "?")

    label = alias or branch
    state = "UP TO DATE" if up_to_date else f"BEHIND {behind}"
    risk_str = f"RISK: {len(risk)} file(s)" if risk else "no risk"

    line = f" {label:20s}  {state:15s}  patches: {patches:3}  {risk_str}"
    win.addnstr(y, 0, line[:width - 1], width - 1, attr)
    y += 1

    # Show patches
    for p in status.get("patches", [])[:5]:
        if y >= height - 1:
            break
        name = p.get("name", p.get("subject", "?"))
        phash = p.get("hash", "")
        pline = f"   [{phash}] {name}"
        win.addnstr(y, 0, pline[:width - 1], width - 1)
        y += 1

    if len(status.get("patches", [])) > 5:
        if y < height - 1:
            win.addnstr(y, 0, f"   ... +{len(status['patches']) - 5} more", width - 1)
            y += 1

    return y + 1


def main(stdscr):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--workspace", action="store_true")
    # Parse from sys.argv (curses wraps main)
    args_list = sys.argv[1:]
    args = parser.parse_args(args_list)

    curses.curs_set(0)
    curses.use_default_colors()
    stdscr.timeout(500)  # 500ms refresh

    repos = []
    selected = 0
    last_refresh = 0
    statuses = {}

    def refresh_data():
        nonlocal repos, statuses
        if args.workspace:
            repos = get_workspace_repos()
            for r in repos:
                statuses[r["path"]] = run_bl(["status"], r["path"])
        else:
            cwd = os.path.abspath(args.cwd)
            repos = [{"path": cwd, "alias": os.path.basename(cwd)}]
            statuses[cwd] = run_bl(["status"], cwd)

    refresh_data()
    last_refresh = time.time()
    selected = min(selected, max(0, len(repos) - 1))

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        draw_header(stdscr, 0, "bingo-light TUI", width)
        stdscr.addnstr(1, 0, "─" * width, width)

        y = 3
        for i, repo in enumerate(repos):
            if y >= height - 2:
                break
            status = statuses.get(repo["path"], {})
            y = draw_repo_status(stdscr, y, status, repo.get("alias", ""), selected == i)

        # Footer
        footer = " [s]ync  [d]ry-run  [r]efresh  [j/k]navigate  [q]uit "
        if height > 2:
            stdscr.addnstr(height - 1, 0, footer.center(width)[:width - 1], width - 1, curses.A_DIM)

        stdscr.refresh()

        # Auto-refresh every 30s
        now = time.time()
        if now - last_refresh > 30:
            refresh_data()
            selected = min(selected, max(0, len(repos) - 1))
            last_refresh = now

        key = stdscr.getch()
        if key == ord("q"):
            break
        elif key == ord("r"):
            refresh_data()
            selected = min(selected, max(0, len(repos) - 1))
            last_refresh = time.time()
        elif key == ord("j") and selected < len(repos) - 1:
            selected += 1
        elif key == ord("k") and selected > 0:
            selected -= 1
        elif key == ord("s") and repos:
            repo = repos[selected]
            stdscr.addnstr(height - 2, 0, f" Syncing {repo['alias']}...", width - 1)
            stdscr.refresh()
            run_bl(["sync"], repo["path"])
            refresh_data()
            selected = min(selected, max(0, len(repos) - 1))
        elif key == ord("d") and repos:
            repo = repos[selected]
            stdscr.addnstr(height - 2, 0, f" Dry-run {repo['alias']}...", width - 1)
            stdscr.refresh()
            result = run_bl(["sync", "--dry-run"], repo["path"])
            msg = json.dumps(result)[:width - 2]
            stdscr.addnstr(height - 2, 0, f" {msg}", width - 1)
            stdscr.refresh()
            time.sleep(2)


if __name__ == "__main__":
    curses.wrapper(main)

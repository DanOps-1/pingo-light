#!/usr/bin/env python3
"""
pingo-light agent — Autonomous fork maintenance powered by LLM.

Monitors upstream changes, syncs automatically, resolves conflicts via Claude,
and reports results through GitHub Issues/PRs.

Architecture inspired by Claude Code's agent loop:
  observe → think (LLM) → act (tools) → observe

Usage:
  # One-shot: check and sync now
  python3 agent.py --cwd /path/to/repo

  # Daemon: check every 6 hours
  python3 agent.py --cwd /path/to/repo --daemon --interval 6h

  # Dry run: see what would happen without acting
  python3 agent.py --cwd /path/to/repo --dry-run

Environment:
  ANTHROPIC_API_KEY  — Required for conflict resolution
  GITHUB_TOKEN       — Optional, for creating Issues/PRs
"""

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

PINGO_BIN = os.environ.get("PINGO_LIGHT_BIN", str(Path(__file__).parent / "pingo-light"))
STATE_FILE = ".pingo-agent-state.json"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds

# ─── Tool Layer: wraps pingo-light CLI ────────────────────────────────────────

def run_pingo(args: list[str], cwd: str) -> dict:
    """Run pingo-light with --json --yes and return parsed result."""
    cmd = [PINGO_BIN, "--json", "--yes"] + args
    env = {**os.environ, "NO_COLOR": "1"}
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120, env=env)

    stdout = result.stdout.strip()
    # Try to parse JSON from output
    if stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            pass

    # Fallback: return raw output
    return {
        "ok": result.returncode == 0,
        "raw_output": stdout,
        "stderr": result.stderr.strip(),
    }


def run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()

# ─── LLM Layer: Claude API for decision-making ───────────────────────────────

def call_llm(system: str, prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    """
    Call Claude API. Implements retry with exponential backoff,
    inspired by Claude Code's withRetry pattern.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set. LLM conflict resolution requires an API key.")

    import urllib.request
    import urllib.error

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = json.dumps({
        "model": model,
        "max_tokens": 8192,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data["content"][0]["text"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 529) and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                log(f"  API rate limited ({e.code}), retrying in {delay}s... (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(delay)
                continue
            raise
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                log(f"  Connection error, retrying in {delay}s... (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(delay)
                continue
            raise

    raise RuntimeError("Max retries exceeded")

# ─── State Persistence (inspired by Claude Code's sessionStorage) ─────────────

def load_state(cwd: str) -> dict:
    path = os.path.join(cwd, STATE_FILE)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"last_check": None, "last_sync": None, "sync_count": 0, "conflict_resolutions": 0, "errors": []}


def save_state(cwd: str, state: dict):
    path = os.path.join(cwd, STATE_FILE)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, default=str)

# ─── Logging ──────────────────────────────────────────────────────────────────

QUIET = False

def log(msg: str):
    if not QUIET:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)


def log_json(event: str, data: dict):
    """Structured logging for machine consumption."""
    entry = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **data}
    print(json.dumps(entry), flush=True)

# ─── Core Agent Loop ─────────────────────────────────────────────────────────
# Inspired by Claude Code's query.ts observe→think→act cycle

def agent_cycle(cwd: str, dry_run: bool = False) -> dict:
    """
    One cycle of the agent loop:
      1. OBSERVE: check fork status
      2. THINK:   decide what to do
      3. ACT:     sync, resolve conflicts, report
      4. OBSERVE: verify result
    """
    state = load_state(cwd)
    result = {"action": "none", "success": True, "details": ""}

    # ── 1. OBSERVE ────────────────────────────────────────────────────────
    log("OBSERVE: checking fork status...")
    status = run_pingo(["status"], cwd)

    if not status.get("ok"):
        log(f"  ERROR: {status}")
        result = {"action": "error", "success": False, "details": f"Status check failed: {status}"}
        state["errors"].append({"time": datetime.now(timezone.utc).isoformat(), "error": result["details"]})
        save_state(cwd, state)
        return result

    behind = status.get("behind", 0)
    patch_count = status.get("patch_count", 0)
    conflict_risk = status.get("conflict_risk", [])
    up_to_date = status.get("up_to_date", True)

    log(f"  behind: {behind}, patches: {patch_count}, conflict_risk: {len(conflict_risk)} file(s)")

    state["last_check"] = datetime.now(timezone.utc).isoformat()

    # ── 2. THINK ──────────────────────────────────────────────────────────
    if up_to_date:
        log("THINK: already up to date. Nothing to do.")
        result = {"action": "none", "success": True, "details": "Already up to date."}
        save_state(cwd, state)
        return result

    if patch_count == 0:
        log("THINK: behind upstream but no patches. Fast-forward sync.")
        action = "sync"
    elif len(conflict_risk) == 0:
        log("THINK: behind upstream, no conflict risk. Safe to sync.")
        action = "sync"
    else:
        log(f"THINK: behind upstream, conflict risk in {conflict_risk}. Will attempt sync with conflict resolution.")
        action = "sync_with_resolve"

    if dry_run:
        log(f"DRY RUN: would {action}. Stopping here.")
        result = {"action": action, "success": True, "details": f"Dry run: would {action}", "dry_run": True}
        save_state(cwd, state)
        return result

    # ── 3. ACT ────────────────────────────────────────────────────────────
    log(f"ACT: executing {action}...")

    sync_result = run_pingo(["sync"], cwd)
    sync_ok = sync_result.get("ok", False)
    sync_raw = sync_result.get("raw_output", "")

    if sync_ok or "Sync complete" in sync_raw or "up to date" in sync_raw.lower():
        log("  sync succeeded cleanly!")
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        state["sync_count"] = state.get("sync_count", 0) + 1
        save_state(cwd, state)
        result = {"action": "sync", "success": True, "details": f"Synced {behind} upstream commit(s), {patch_count} patch(es) rebased."}
        return result

    # Sync failed — likely conflict. Try to resolve.
    log("  sync hit conflict. Attempting LLM-assisted resolution...")
    resolve_result = resolve_conflicts_with_llm(cwd)

    if resolve_result["success"]:
        log("  conflicts resolved by LLM!")
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        state["sync_count"] = state.get("sync_count", 0) + 1
        state["conflict_resolutions"] = state.get("conflict_resolutions", 0) + 1
        save_state(cwd, state)
        result = {"action": "sync_with_resolve", "success": True, "details": resolve_result["details"]}
        return result
    else:
        log(f"  LLM could not resolve: {resolve_result['details']}")
        # Abort the rebase to leave repo clean
        try:
            run_git(["rebase", "--abort"], cwd)
        except RuntimeError:
            pass
        state["errors"].append({"time": datetime.now(timezone.utc).isoformat(), "error": resolve_result["details"]})
        save_state(cwd, state)
        result = {"action": "sync_with_resolve", "success": False, "details": resolve_result["details"]}
        return result


def resolve_conflicts_with_llm(cwd: str, max_rounds: int = 5) -> dict:
    """
    LLM-powered conflict resolution loop.
    Iterates: analyze conflict → ask LLM → write resolution → continue rebase.
    Up to max_rounds to handle multi-patch conflicts.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"success": False, "details": "No ANTHROPIC_API_KEY set. Cannot resolve conflicts automatically."}

    resolved_count = 0

    for round_num in range(1, max_rounds + 1):
        log(f"  resolution round {round_num}/{max_rounds}...")

        # Check if we're still in a rebase
        rebase_dir = os.path.join(cwd, ".git", "rebase-merge")
        rebase_apply = os.path.join(cwd, ".git", "rebase-apply")
        if not os.path.isdir(rebase_dir) and not os.path.isdir(rebase_apply):
            log("  rebase complete!")
            return {"success": True, "details": f"Resolved {resolved_count} conflict(s) via LLM."}

        # Find conflicted files
        try:
            conflicted = run_git(["diff", "--name-only", "--diff-filter=U"], cwd)
        except RuntimeError:
            conflicted = ""

        if not conflicted.strip():
            # No conflicts but still in rebase — try to continue
            try:
                result = subprocess.run(
                    ["git", "rebase", "--continue"], cwd=cwd,
                    capture_output=True, text=True, timeout=30,
                    env={**os.environ, "GIT_EDITOR": "true"},
                )
                if result.returncode == 0:
                    continue  # Check next round
                else:
                    return {"success": False, "details": f"rebase --continue failed: {result.stderr.strip()}"}
            except Exception as e:
                return {"success": False, "details": str(e)}

        # For each conflicted file, ask LLM to resolve
        for file_path in conflicted.strip().split("\n"):
            file_path = file_path.strip()
            if not file_path:
                continue

            full_path = os.path.join(cwd, file_path)
            if not os.path.exists(full_path):
                continue

            with open(full_path) as f:
                content = f.read()

            if "<<<<<<< " not in content:
                # Already resolved (maybe by rerere)
                run_git(["add", file_path], cwd)
                continue

            log(f"    resolving: {file_path}")

            # Get context: what patch is being applied?
            patch_info = ""
            msg_file = os.path.join(cwd, ".git", "rebase-merge", "message")
            if os.path.exists(msg_file):
                with open(msg_file) as f:
                    patch_info = f.read().strip()

            # Ask LLM to resolve
            system_prompt = (
                "You are a code merge conflict resolver. You receive a file with git conflict markers "
                "(<<<<<<< HEAD / ======= / >>>>>>>). Your job is to produce the RESOLVED file content "
                "with all conflict markers removed. Choose the best resolution that preserves both "
                "the upstream changes and the patch's intent. Output ONLY the resolved file content, "
                "nothing else — no markdown fences, no explanation."
            )

            user_prompt = f"""Resolve the merge conflicts in this file.

Patch being applied: {patch_info}
File: {file_path}

Content with conflict markers:
{content}"""

            try:
                resolved_content = call_llm(system_prompt, user_prompt)
            except Exception as e:
                return {"success": False, "details": f"LLM call failed for {file_path}: {e}"}

            # Sanity check: LLM output should not contain conflict markers
            if "<<<<<<< " in resolved_content or "=======" in resolved_content:
                return {"success": False, "details": f"LLM produced output with conflict markers for {file_path}"}

            # Write resolved content
            with open(full_path, "w") as f:
                f.write(resolved_content)

            run_git(["add", file_path], cwd)
            resolved_count += 1
            log(f"    resolved: {file_path}")

        # Continue rebase after resolving all files in this round
        try:
            result = subprocess.run(
                ["git", "rebase", "--continue"], cwd=cwd,
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "GIT_EDITOR": "true"},
            )
            if result.returncode != 0 and "CONFLICT" in result.stderr:
                continue  # More conflicts in next patch, loop again
            elif result.returncode != 0:
                return {"success": False, "details": f"rebase --continue failed: {result.stderr.strip()}"}
        except Exception as e:
            return {"success": False, "details": str(e)}

    return {"success": False, "details": f"Max resolution rounds ({max_rounds}) exceeded."}

# ─── Reporting ────────────────────────────────────────────────────────────────

def report_result(cwd: str, result: dict):
    """Report agent action result. Creates GitHub Issue on failure if gh is available."""
    if result["success"]:
        log(f"RESULT: {result['details']}")
        return

    log(f"RESULT (FAILED): {result['details']}")

    # Try to create GitHub Issue
    gh = subprocess.run(["gh", "--version"], capture_output=True)
    if gh.returncode != 0:
        return

    title = f"[pingo-light-agent] Sync failed ({datetime.now().strftime('%Y-%m-%d')})"
    body = f"""## Auto-sync failed

**Action:** {result['action']}
**Details:** {result['details']}
**Time:** {datetime.now(timezone.utc).isoformat()}

Manual intervention required. Run `pingo-light sync` locally to resolve.

---
*This issue was created by pingo-light agent.*"""

    try:
        subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body, "--label", "pingo-light"],
            cwd=cwd, capture_output=True, text=True, timeout=30,
        )
        log("  created GitHub Issue for failed sync.")
    except Exception:
        pass

# ─── Daemon Mode ──────────────────────────────────────────────────────────────

def parse_interval(s: str) -> int:
    """Parse interval string like '6h', '30m', '1d' to seconds."""
    s = s.strip().lower()
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    elif s.endswith("m"):
        return int(s[:-1]) * 60
    elif s.endswith("d"):
        return int(s[:-1]) * 86400
    elif s.endswith("s"):
        return int(s[:-1])
    else:
        return int(s)  # assume seconds


def daemon_loop(cwd: str, interval: int, dry_run: bool = False):
    """Run agent cycle on a schedule."""
    log(f"DAEMON: starting (interval={interval}s, cwd={cwd})")
    while True:
        try:
            result = agent_cycle(cwd, dry_run=dry_run)
            report_result(cwd, result)
        except KeyboardInterrupt:
            log("DAEMON: interrupted, stopping.")
            break
        except Exception as e:
            log(f"DAEMON: unhandled error: {e}")
            traceback.print_exc()

        log(f"DAEMON: sleeping {interval}s until next check...")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log("DAEMON: interrupted, stopping.")
            break

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="pingo-light agent — Autonomous fork maintenance powered by LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # One-shot sync check
  python3 agent.py --cwd /path/to/repo

  # Dry run (see what would happen)
  python3 agent.py --cwd /path/to/repo --dry-run

  # Daemon mode (check every 6 hours)
  python3 agent.py --cwd /path/to/repo --daemon --interval 6h

  # With specific model
  python3 agent.py --cwd /path/to/repo --model claude-haiku-4-20250414

Environment:
  ANTHROPIC_API_KEY  Required for LLM conflict resolution
  GITHUB_TOKEN       Optional, for creating Issues on failure
  PINGO_LIGHT_BIN    Override path to pingo-light binary
""",
    )
    parser.add_argument("--cwd", required=True, help="Path to the git repository")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without executing")
    parser.add_argument("--daemon", action="store_true", help="Run continuously on a schedule")
    parser.add_argument("--interval", default="6h", help="Check interval for daemon mode (default: 6h)")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Claude model for conflict resolution")
    parser.add_argument("--json-log", action="store_true", help="Output structured JSON logs")
    parser.add_argument("--quiet", action="store_true", help="Suppress human-readable output")

    args = parser.parse_args()

    global QUIET
    QUIET = args.quiet

    cwd = os.path.abspath(args.cwd)
    if not os.path.isdir(os.path.join(cwd, ".git")):
        print(f"Error: {cwd} is not a git repository.", file=sys.stderr)
        sys.exit(1)

    if args.daemon:
        interval = parse_interval(args.interval)
        daemon_loop(cwd, interval, dry_run=args.dry_run)
    else:
        result = agent_cycle(cwd, dry_run=args.dry_run)
        report_result(cwd, result)

        if args.json_log:
            print(json.dumps(result))

        sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()

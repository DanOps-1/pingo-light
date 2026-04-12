#!/usr/bin/env python3
"""
bingo-light agent — Intelligent fork maintenance advisor.

Monitors upstream, auto-syncs when safe, analyzes and explains conflicts
when not. The agent NEVER auto-resolves conflicts or auto-pushes code.

Philosophy:
  - Safe ops (no conflict): auto-execute
  - Risky ops (conflict):   analyze → explain → recommend → WAIT for human
  - LLM role: analyst, not executor — understands intent, explains trade-offs

Architecture (inspired by Claude Code's agent loop):
  observe → analyze → safe-act or report → wait

Usage:
  python3 agent.py --cwd /path/to/repo                  # check + sync if safe
  python3 agent.py --cwd /path/to/repo --report          # full analysis report
  python3 agent.py --cwd /path/to/repo --watch --interval 6h  # periodic monitor
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

BINGO_BIN = os.environ.get("BINGO_LIGHT_BIN", str(Path(__file__).parent / "bingo-light"))
STATE_FILE = ".bingo-agent-state.json"
REPORT_FILE = ".bingo-report.md"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2

# ─── Infra: CLI + Git + LLM ──────────────────────────────────────────────────

def run_bl(args: list[str], cwd: str) -> dict:
    """Run bingo-light with --json --yes and return parsed result."""
    cmd = [BINGO_BIN, "--json", "--yes"] + args
    env = {**os.environ, "NO_COLOR": "1"}
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120, env=env)
    except FileNotFoundError:
        return {"ok": False, "error": "bingo-light not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "command timed out"}
    stdout = result.stdout.strip()
    if stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            pass
    return {"ok": result.returncode == 0, "raw": stdout, "stderr": result.stderr.strip()}


def run_git(args: list[str], cwd: str) -> str:
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def call_llm(system: str, prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Call Claude API with retry. Used for ANALYSIS only, never for code execution."""
    import urllib.request, urllib.error

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""  # Graceful degradation: agent works without LLM, just less insightful

    body = json.dumps({
        "model": model, "max_tokens": 4096, "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    headers = {"x-api-key": api_key, "content-type": "application/json", "anthropic-version": "2023-06-01"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())["content"][0]["text"]
        except urllib.error.HTTPError as e:
            # Don't retry client errors (400, 401, 403)
            if 400 <= e.code < 500 and e.code != 429:
                return ""
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                continue
            return ""
        except (urllib.error.URLError, OSError, ValueError):
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                continue
            return ""
        except (KeyError, IndexError, json.JSONDecodeError):
            return ""  # Unexpected response shape
    return ""

# ─── State ────────────────────────────────────────────────────────────────────

def load_state(cwd: str) -> dict:
    path = os.path.join(cwd, STATE_FILE)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass  # Corrupted state — reset to defaults
    return {"last_check": None, "last_sync": None, "sync_count": 0, "reports": 0}


def save_state(cwd: str, state: dict):
    path = os.path.join(cwd, STATE_FILE)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp_path, path)  # Atomic rename

# ─── Logging ──────────────────────────────────────────────────────────────────

QUIET = False
def log(msg: str):
    if not QUIET:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ─── Analysis Engine ──────────────────────────────────────────────────────────

def analyze_upstream_changes(cwd: str, tracking: str, upstream_ref: str) -> list[dict]:
    """Analyze what changed upstream since last sync."""
    commits = []
    log_output = run_git(["log", "--format=%H|%s|%an|%cr", f"{tracking}..{upstream_ref}"], cwd)
    for line in log_output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        hash_, subject, author, date = parts
        # Get changed files for this commit
        files = run_git(["diff-tree", "--no-commit-id", "-r", "--name-only", hash_], cwd).split("\n")
        commits.append({"hash": hash_[:8], "subject": subject, "author": author, "date": date, "files": [f for f in files if f]})
    return commits


def analyze_patch_impact(cwd: str, upstream_commits: list[dict], patches: list[dict]) -> list[dict]:
    """For each patch, determine if upstream changes affect the same files."""
    impacts = []
    upstream_files = set()
    for c in upstream_commits:
        upstream_files.update(c["files"])

    for p in patches:
        patch_files = set(p.get("files_list", []))
        overlap = patch_files & upstream_files
        risk = "none"
        if overlap:
            risk = "high" if len(overlap) > 2 else "medium"
        impacts.append({
            "patch": p.get("name", p.get("subject", "?")),
            "hash": p.get("hash", ""),
            "files": list(patch_files),
            "overlap": list(overlap),
            "risk": risk,
        })
    return impacts


def analyze_conflict_details(cwd: str) -> list[dict]:
    """When in a rebase conflict, extract structured conflict info."""
    conflicts = []
    try:
        unmerged = run_git(["ls-files", "--unmerged"], cwd)
        # Extract unique file paths (ls-files --unmerged output: mode hash stage\tpath)
        conflicted_files = sorted(set(
            line.split("\t")[-1] for line in unmerged.strip().splitlines() if "\t" in line
        ))
    except RuntimeError:
        return conflicts

    for file_path in conflicted_files:
        file_path = file_path.strip()
        if not file_path:
            continue
        full_path = os.path.join(cwd, file_path)
        if not os.path.exists(full_path):
            continue

        # Skip very large files (>1MB) to avoid OOM
        try:
            if os.path.getsize(full_path) > 1024 * 1024:
                conflicts.append({"file": file_path, "regions": [], "patch": "", "note": "file too large"})
                continue
        except OSError:
            continue

        with open(full_path) as f:
            content = f.read()

        # Extract conflict regions via regex
        regions = []
        for m in re.finditer(r'<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*', content, re.DOTALL):
            regions.append({"ours": m.group(1).rstrip(), "theirs": m.group(2).rstrip()})

        # Get current patch info
        patch_name = ""
        msg_file = os.path.join(cwd, ".git", "rebase-merge", "message")
        if os.path.exists(msg_file):
            with open(msg_file) as f:
                patch_name = f.read().strip().split("\n")[0]

        conflicts.append({
            "file": file_path,
            "regions": regions,
            "region_count": len(regions),
            "patch": patch_name,
        })

    return conflicts


def llm_explain_changes(upstream_commits: list[dict], impacts: list[dict], model: str) -> str:
    """Ask LLM to summarize upstream changes and their impact on patches. Pure analysis."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ""

    system = (
        "You are a technical analyst for a fork maintenance tool. "
        "Analyze upstream changes and explain their impact on the user's patches. "
        "Be concise. Use bullet points. Highlight risks. "
        "DO NOT suggest code changes — only explain what happened and what the user should consider."
    )

    upstream_summary = "\n".join(
        f"  {c['hash']} {c['subject']} ({', '.join(c['files'][:5])}{'...' if len(c['files']) > 5 else ''})"
        for c in upstream_commits[:20]
    )

    impact_summary = "\n".join(
        f"  [{i['risk'].upper()}] patch '{i['patch']}' — overlap: {', '.join(i['overlap']) or 'none'}"
        for i in impacts
    )

    prompt = f"""Upstream has {len(upstream_commits)} new commit(s):
{upstream_summary}

Impact on user's patches:
{impact_summary}

Provide a brief analysis:
1. What are the key upstream changes? (group by theme)
2. Which patches are at risk and why?
3. Should the user sync now or wait? Why?"""

    return call_llm(system, prompt, model)


def llm_explain_conflicts(conflicts: list[dict], model: str) -> str:
    """Ask LLM to explain conflicts and suggest resolution strategies. Does NOT produce code."""
    if not os.environ.get("ANTHROPIC_API_KEY") or not conflicts:
        return ""

    system = (
        "You are a merge conflict advisor. Explain each conflict: what both sides intended, "
        "why they conflict, and what resolution strategies exist. "
        "DO NOT write resolved code. Only explain the situation and trade-offs. "
        "The user will decide how to resolve."
    )

    conflict_desc = ""
    for c in conflicts:
        conflict_desc += f"\nFile: {c['file']} (patch: {c['patch']}, {c['region_count']} conflict region(s))\n"
        for i, r in enumerate(c["regions"][:3]):  # limit to 3 regions per file
            conflict_desc += f"  Region {i+1}:\n"
            conflict_desc += f"    Upstream version:\n      {r['ours'][:300]}\n"
            conflict_desc += f"    Your patch version:\n      {r['theirs'][:300]}\n"

    prompt = f"""The following merge conflicts occurred during sync:
{conflict_desc}

For each conflict:
1. What was upstream trying to do?
2. What was the patch trying to do?
3. What are the resolution options? (keep ours / keep theirs / merge both / rewrite patch)
4. What's your recommendation and why?"""

    return call_llm(system, prompt, model)

# ─── Report Generator ─────────────────────────────────────────────────────────

def generate_report(
    status: dict,
    upstream_commits: list[dict],
    impacts: list[dict],
    llm_analysis: str,
    sync_result: dict | None,
    conflicts: list[dict],
    llm_conflict_analysis: str,
) -> str:
    """Generate a human-readable markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    behind = status.get("behind", 0)
    patches = status.get("patches", [])

    report = f"""# bingo-light sync report
> Generated: {now}

## Fork Status

| | |
|---|---|
| Upstream | {status.get('upstream_url', '?')} |
| Branch | {status.get('upstream_branch', '?')} |
| Behind | **{behind} commit(s)** |
| Patches | {status.get('patch_count', 0)} |

"""

    if behind == 0:
        report += "**Up to date.** No action needed.\n"
        return report

    # Upstream changes
    report += "## Upstream Changes\n\n"
    for c in upstream_commits[:30]:
        files_str = ", ".join(c["files"][:3])
        if len(c["files"]) > 3:
            files_str += f" +{len(c['files'])-3} more"
        report += f"- `{c['hash']}` {c['subject']} — {files_str}\n"
    report += "\n"

    # Impact analysis
    report += "## Patch Impact Analysis\n\n"
    report += "| Patch | Risk | Overlapping Files |\n|---|---|---|\n"
    for i in impacts:
        risk_badge = {"none": "none", "medium": "**MEDIUM**", "high": "**HIGH**"}[i["risk"]]
        overlap = ", ".join(i["overlap"]) if i["overlap"] else "—"
        report += f"| {i['patch']} | {risk_badge} | {overlap} |\n"
    report += "\n"

    # LLM analysis (if available)
    if llm_analysis:
        report += "## AI Analysis\n\n"
        report += llm_analysis + "\n\n"

    # Sync result
    if sync_result:
        if sync_result.get("synced"):
            report += f"## Sync Result\n\n**Synced successfully.** {behind} upstream commit(s) integrated, all patches rebased cleanly.\n\n"
        elif sync_result.get("conflict"):
            report += "## Sync Result\n\n**Conflict detected.** Auto-sync aborted. Manual resolution required.\n\n"

            # Conflict details
            if conflicts:
                report += "### Conflicts\n\n"
                for c in conflicts:
                    report += f"**{c['file']}** (patch: `{c['patch']}`, {c['region_count']} conflict region(s))\n\n"
                    for j, r in enumerate(c["regions"][:3]):
                        report += f"<details><summary>Region {j+1}</summary>\n\n"
                        report += f"```\n<<<<<<< upstream\n{r['ours']}\n=======\n{r['theirs']}\n>>>>>>> your patch\n```\n\n"
                        report += "</details>\n\n"

            # LLM conflict explanation
            if llm_conflict_analysis:
                report += "### AI Conflict Explanation\n\n"
                report += llm_conflict_analysis + "\n\n"

            report += "### What to Do\n\n"
            report += "```bash\n"
            report += "# Option 1: Resolve manually\n"
            report += "bingo-light sync\n"
            report += "# Edit conflicted files, then: git add <files> && git rebase --continue\n\n"
            report += "# Option 2: Skip the conflicting patch\n"
            report += "# git rebase --skip\n\n"
            report += "# Option 3: Abort and stay on current version\n"
            report += "# git rebase --abort\n"
            report += "```\n"

    # Recommendation
    any_high = any(i["risk"] == "high" for i in impacts)
    any_medium = any(i["risk"] == "medium" for i in impacts)

    report += "\n## Recommendation\n\n"
    if sync_result and sync_result.get("synced"):
        report += "Sync completed successfully. No action needed.\n"
    elif any_high:
        report += ("**Wait before syncing.** High-risk overlap detected. "
                   "Review the upstream changes above and consider updating your patches first.\n")
    elif any_medium:
        report += ("**Sync with caution.** Medium-risk overlap. "
                   "Run `bingo-light sync --dry-run` to preview, then sync if clean.\n")
    else:
        report += "**Safe to sync.** No overlap between your patches and upstream changes.\n"

    return report

# ─── Core Agent Loop ──────────────────────────────────────────────────────────

def agent_cycle(cwd: str, model: str, full_report: bool = False) -> dict:
    """
    Agent cycle:
      1. OBSERVE:  check status
      2. ANALYZE:  understand upstream changes + impact
      3. SAFE-ACT: sync if no conflict risk
      4. REPORT:   generate analysis when conflicts exist or report requested
    """
    state = load_state(cwd)
    state["last_check"] = datetime.now(timezone.utc).isoformat()

    # ── 1. OBSERVE ────────────────────────────────────────────────────────
    log("OBSERVE: checking fork status...")
    status = run_bl(["status"], cwd)

    if not status.get("ok"):
        save_state(cwd, state)
        return {"action": "error", "success": False, "details": f"Status failed: {status}"}

    if status.get("in_rebase"):
        save_state(cwd, state)
        return {"action": "conflict_in_progress", "success": False, "status": status,
                "details": "A rebase is already in progress. Resolve conflicts or abort before running the agent."}

    behind = status.get("behind", 0)
    patch_count = status.get("patch_count", 0)
    conflict_risk = status.get("conflict_risk", [])

    log(f"  behind={behind} patches={patch_count} risk_files={len(conflict_risk)}")

    if behind == 0:
        log("UP TO DATE. Nothing to do.")
        report = generate_report(status, [], [], "", None, [], "")
        save_state(cwd, state)
        return {"action": "none", "success": True, "details": "Up to date.", "report": report}

    # ── 2. ANALYZE ────────────────────────────────────────────────────────
    log("ANALYZE: examining upstream changes...")

    tracking = status.get("upstream_branch", "main")
    upstream_commits = analyze_upstream_changes(cwd, "upstream-tracking", f"upstream/{tracking}")
    log(f"  {len(upstream_commits)} upstream commit(s)")

    # Get detailed patch file lists for impact analysis
    patches_detail = []
    for p in status.get("patches", []):
        try:
            files = run_git(["diff-tree", "--no-commit-id", "-r", "--name-only", p["hash"]], cwd).split("\n")
        except RuntimeError:
            files = []
        patches_detail.append({**p, "files_list": [f for f in files if f]})

    impacts = analyze_patch_impact(cwd, upstream_commits, patches_detail)
    any_risk = any(i["risk"] != "none" for i in impacts)

    log(f"  impact: {sum(1 for i in impacts if i['risk']!='none')} patch(es) at risk")

    # LLM analysis (optional, graceful degradation)
    llm_analysis = ""
    if full_report or any_risk:
        log("  requesting AI analysis...")
        llm_analysis = llm_explain_changes(upstream_commits, impacts, model)

    # ── 3. DECIDE + ACT ──────────────────────────────────────────────────

    sync_result = None
    conflicts = []
    llm_conflict_analysis = ""

    if not any_risk and not full_report:
        # SAFE: no overlap, auto-sync
        log("SAFE-ACT: no conflict risk, syncing...")
        bingo_result = run_bl(["sync"], cwd)

        if bingo_result.get("ok"):
            log("  synced successfully!")
            state["last_sync"] = datetime.now(timezone.utc).isoformat()
            state["sync_count"] = state.get("sync_count", 0) + 1
            sync_result = {"synced": True}
        else:
            # Unexpected conflict despite no overlap prediction — analyze and abort
            log("  unexpected conflict during sync!")
            conflicts = analyze_conflict_details(cwd)
            llm_conflict_analysis = llm_explain_conflicts(conflicts, model)
            try:
                run_git(["rebase", "--abort"], cwd)
            except RuntimeError:
                pass
            sync_result = {"conflict": True}

    elif any_risk and not full_report:
        # RISKY: try dry-run first
        log("CAUTION: overlap detected, testing with dry-run...")
        dry_result = run_bl(["sync", "--dry-run"], cwd)

        if dry_result.get("clean", False):
            # Dry-run passed! Safe to sync despite overlap
            log("  dry-run clean, syncing...")
            bingo_result = run_bl(["sync"], cwd)
            if bingo_result.get("ok"):
                state["last_sync"] = datetime.now(timezone.utc).isoformat()
                state["sync_count"] = state.get("sync_count", 0) + 1
                sync_result = {"synced": True}
            else:
                conflicts = analyze_conflict_details(cwd)
                llm_conflict_analysis = llm_explain_conflicts(conflicts, model)
                try:
                    run_git(["rebase", "--abort"], cwd)
                except RuntimeError:
                    pass
                sync_result = {"conflict": True}
        else:
            # Dry-run confirms conflict — DO NOT sync, just report
            log("  dry-run confirms conflict. Will NOT sync. Generating report...")

            # Don't run a real sync just to get conflict details — too risky
            # Report dry-run results and recommend manual resolution
            sync_result = {"conflict": True, "dry_run_conflicts": dry_result.get("conflicted_files", [])}

    # ── 4. REPORT ─────────────────────────────────────────────────────────
    log("REPORT: generating analysis...")

    report = generate_report(
        status, upstream_commits, impacts, llm_analysis,
        sync_result, conflicts, llm_conflict_analysis,
    )

    # Write report to file
    report_path = os.path.join(cwd, REPORT_FILE)
    with open(report_path, "w") as f:
        f.write(report)
    log(f"  report saved to {REPORT_FILE}")

    synced = sync_result and sync_result.get("synced", False)
    has_conflict = sync_result and sync_result.get("conflict", False)

    if has_conflict:
        state["reports"] = state.get("reports", 0) + 1

    save_state(cwd, state)

    if synced:
        return {"action": "synced", "success": True, "details": f"Synced {behind} commit(s), {patch_count} patch(es) rebased.", "report": report}
    elif has_conflict:
        return {"action": "conflict_report", "success": True, "details": f"Conflict detected. Report saved to {REPORT_FILE}", "report": report}
    else:
        return {"action": "report", "success": True, "details": "Analysis complete.", "report": report}


# ─── Notification ─────────────────────────────────────────────────────────────

def notify(cwd: str, result: dict):
    """Print result. Create GitHub Issue only for conflicts that need attention."""
    action = result.get("action", "")
    details = result.get("details", "")

    if action == "synced":
        log(f"DONE: {details}")
    elif action == "conflict_report":
        log(f"ATTENTION: {details}")
        log("  Review the report and resolve manually when ready.")
        # Try GitHub Issue for visibility
        try:
            title = f"[bingo-light] Upstream sync needs attention ({datetime.now().strftime('%Y-%m-%d')})"
            body = result.get("report", details)
            gh_result = subprocess.run(
                ["gh", "issue", "create", "--title", title, "--body", body, "--label", "bingo-light,sync-conflict"],
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            if gh_result.returncode == 0:
                log("  GitHub Issue created for visibility.")
            else:
                log("  GitHub Issue creation failed (gh CLI error).")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # gh not installed or timed out
    elif action == "none":
        log(f"DONE: {details}")
    elif action == "error":
        log(f"ERROR: {details}")
    else:
        log(f"DONE: {details}")


# ─── Watch Mode ───────────────────────────────────────────────────────────────

def parse_interval(s: str) -> int:
    s = s.strip().lower()
    try:
        if s.endswith("h"):   return int(s[:-1]) * 3600
        elif s.endswith("m"): return int(s[:-1]) * 60
        elif s.endswith("d"): return int(s[:-1]) * 86400
        else: return int(s)
    except ValueError:
        print(f"Error: invalid interval '{s}'. Use a number with optional suffix: 30, 5m, 1h, 1d", file=sys.stderr)
        sys.exit(1)


def watch_loop(cwd: str, interval: int, model: str):
    """Periodic monitoring. NOT a daemon — just a scheduled check loop."""
    log(f"WATCH: monitoring every {interval}s")
    while True:
        try:
            result = agent_cycle(cwd, model)
            notify(cwd, result)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"ERROR: {e}")
            traceback.print_exc()
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            break
    log("WATCH: stopped.")

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="bingo-light agent — Intelligent fork maintenance advisor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Behavior:
  Default     Check upstream. Sync if safe. Report if conflict.
  --report    Full analysis report (even if up-to-date).
  --watch     Periodic monitoring loop.

The agent NEVER auto-resolves conflicts or auto-pushes code.
Conflicts generate a detailed report for human review.

Examples:
  python3 agent.py --cwd /path/to/repo
  python3 agent.py --cwd /path/to/repo --report
  python3 agent.py --cwd /path/to/repo --watch --interval 6h

Environment:
  ANTHROPIC_API_KEY  Optional. Enables AI-powered analysis (richer reports).
                     Without it, agent still works — just less insightful.
""",
    )
    parser.add_argument("--cwd", required=True, help="Path to the git repo")
    parser.add_argument("--report", action="store_true", help="Generate full analysis report")
    parser.add_argument("--watch", action="store_true", help="Periodic monitoring loop")
    parser.add_argument("--interval", default="6h", help="Watch interval (default: 6h)")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Claude model for analysis")
    parser.add_argument("--quiet", action="store_true", help="Suppress log output")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()
    global QUIET
    QUIET = args.quiet

    cwd = os.path.abspath(args.cwd)
    if not os.path.isdir(os.path.join(cwd, ".git")):
        print(f"Error: {cwd} is not a git repository.", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(os.path.join(cwd, ".bingolight")):
        print(f"Error: {cwd} is not initialized with bingo-light. Run 'bingo-light init' first.", file=sys.stderr)
        sys.exit(1)

    if args.watch:
        watch_loop(cwd, parse_interval(args.interval), args.model)
    else:
        result = agent_cycle(cwd, args.model, full_report=args.report)
        notify(cwd, result)

        if args.json:
            # Output machine-readable result (without report to save space)
            out = {k: v for k, v in result.items() if k != "report"}
            print(json.dumps(out))

        sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()

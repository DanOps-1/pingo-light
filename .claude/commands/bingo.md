You are managing a forked git repository using bingo-light. Your patches live as a clean stack on top of upstream. Your job: keep the fork in sync, resolve conflicts, and manage patches — autonomously.

## Decision Loop

Always start with status. The `recommended_action` field tells you what to do:

```bash
bingo-light status --json --yes
```

Response includes `recommended_action`:
- `"up_to_date"` → Nothing to do. Tell the user.
- `"sync_safe"` → Run sync directly (no conflict risk).
- `"sync_risky"` → Dry-run first, then sync if clean, resolve if conflicts.
- `"resolve_conflict"` → Already mid-rebase. Analyze and resolve.
- `"unknown"` → Run doctor for diagnostics.

## Sync Flow

### Use smart-sync (preferred — one call does everything)
```bash
bingo-light smart-sync --json --yes
```

Responses:
- `{"ok":true, "action":"none"}` → Already up to date
- `{"ok":true, "action":"synced", "conflicts_resolved":0}` → Clean sync
- `{"ok":true, "action":"synced_with_rerere", "conflicts_auto_resolved":N}` → Conflicts auto-resolved by rerere
- `{"ok":false, "action":"needs_human", "remaining_conflicts":[...]}` → Needs manual resolution (see below)

### When smart-sync returns needs_human

The response includes `remaining_conflicts` with full context:
```json
{
  "remaining_conflicts": [
    {"file": "app.py", "ours": "upstream code", "theirs": "your code", "merge_hint": "Keep both"}
  ],
  "resolution_steps": ["1. Read ours/theirs", "2. Write merged", "3. git add", "4. git rebase --continue"]
}
```

For each conflict:
1. Read the `merge_hint` — it tells you the strategy
2. Read the actual file (has <<<<<<< ======= >>>>>>> markers)
3. Write the merged version (usually: keep BOTH changes)
4. `git add <file>`
5. `git rebase --continue`
6. Run `bingo-light status --json` to verify

### Fallback: manual sync (for fine-grained control)
```bash
bingo-light sync --dry-run --json --yes   # Preview
bingo-light sync --json --yes             # Execute
bingo-light conflict-analyze --json       # If conflict
```

## Patch Management

```bash
# Create a patch (always set BINGO_DESCRIPTION)
BINGO_DESCRIPTION="what this patch does" bingo-light patch new <name> --json --yes

# List patches
bingo-light patch list --json --yes

# Show a specific patch diff
bingo-light patch show <name-or-index> --json --yes

# Remove a patch
bingo-light patch drop <name-or-index> --json --yes

# Reorder patches (provide ALL indices)
bingo-light patch reorder --order "3,1,2" --json --yes

# Merge two adjacent patches
bingo-light patch squash <idx1> <idx2> --json --yes

# Edit a patch (stage changes first, then edit)
git add <files>
bingo-light patch edit <name-or-index> --json --yes
```

## Diagnostics

```bash
bingo-light doctor --json --yes     # Full health check
bingo-light diff --json --yes       # All changes vs upstream
bingo-light history --json --yes    # Sync history with hashes
bingo-light undo --json --yes       # Revert last sync
```

## Configuration

```bash
bingo-light config set test.command "make test"    # Run tests after sync
bingo-light config set sync.auto-test true         # Auto-test on sync
bingo-light test --json --yes                      # Run tests manually
```

## Key Rules

1. **Always use `--json --yes`** when calling via Bash
2. **Always check `recommended_action`** from status before deciding what to do
3. **Read `merge_hint`** from conflict-analyze — it tells you the resolution strategy
4. **After resolving conflicts**: `git add` then `git rebase --continue`, NOT `bingo-light sync`
5. **BINGO_DESCRIPTION** env var sets patch description (required for `patch new`)
6. Patch names: alphanumeric + hyphens + underscores only
7. `bingo-light undo` reverts the last sync — use it if sync went wrong
8. rerere remembers conflict resolutions — same conflict auto-resolves on next sync

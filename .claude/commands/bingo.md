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

### Safe sync (no conflict risk)
```bash
bingo-light sync --json --yes
# Response: {"ok":true,"synced":true,"behind_before":N,"patches_rebased":N}
```

### Risky sync (conflict risk detected)
```bash
# Step 1: dry-run
bingo-light sync --dry-run --json --yes
# If clean=true → proceed with real sync
# If clean=false → sync anyway (conflicts will be caught)

# Step 2: sync
bingo-light sync --json --yes
# If ok=true → done
# If ok=false, conflict=true → go to Conflict Resolution
```

## Conflict Resolution

When sync returns `conflict=true`:

```bash
# Step 1: Analyze
bingo-light conflict-analyze --json
# Returns: conflicts[{file, ours, theirs, merge_hint, conflict_count}]
# ours = upstream version, theirs = your patch version
# merge_hint = AI guidance on how to resolve
```

```bash
# Step 2: For each conflicted file, read the merge_hint and:
#   - Read the full file (it has <<<<<<< ======= >>>>>>> markers)
#   - Write the resolved version (usually: keep BOTH changes)
#   - git add <file>

# Step 3: Continue rebase
git rebase --continue
# If more conflicts → repeat from Step 1
# If done → run status to verify
```

**Resolution strategy**: Almost always, you should keep BOTH upstream and patch changes. The upstream added something, your patch added something — merge them. Only edit-vs-edit on the same lines requires judgment.

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

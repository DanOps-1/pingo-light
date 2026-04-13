# Fish completion for bingo-light
# Place in ~/.config/fish/completions/ or source directly.
#
# Usage:
#   cp bingo-light.fish ~/.config/fish/completions/

# ---- Helper: detect whether a specific command/subcommand is already on the line ----

# Returns true when no subcommand has been given yet (top-level completions).
function __bingo_light_needs_command
    set -l cmd (commandline -opc)
    if test (count $cmd) -eq 1
        return 0
    end
    return 1
end

# Returns true when the first positional argument matches any of the supplied values.
function __bingo_light_using_command
    set -l cmd (commandline -opc)
    if test (count $cmd) -lt 2
        return 1
    end
    for arg in $argv
        if test "$cmd[2]" = "$arg"
            return 0
        end
    end
    return 1
end

# Returns true when we are inside "patch" (or "p") and need a patch subcommand.
function __bingo_light_patch_needs_subcommand
    set -l cmd (commandline -opc)
    if test (count $cmd) -lt 2
        return 1
    end
    if test "$cmd[2]" != patch -a "$cmd[2]" != p
        return 1
    end
    if test (count $cmd) -eq 2
        return 0
    end
    return 1
end

# Returns true when the patch subcommand matches any of the supplied values.
function __bingo_light_patch_using_subcommand
    set -l cmd (commandline -opc)
    if test (count $cmd) -lt 3
        return 1
    end
    if test "$cmd[2]" != patch -a "$cmd[2]" != p
        return 1
    end
    for arg in $argv
        if test "$cmd[3]" = "$arg"
            return 0
        end
    end
    return 1
end

# ---- Disable file completions by default ----
complete -c bingo-light -f

# ---- Top-level commands ----
complete -c bingo-light -n __bingo_light_needs_command -a init    -d 'Initialize a new bingo-light project'
complete -c bingo-light -n __bingo_light_needs_command -a setup   -d 'Configure MCP for AI tools (interactive)'
complete -c bingo-light -n __bingo_light_needs_command -a patch   -d 'Manage patches'
complete -c bingo-light -n __bingo_light_needs_command -a sync    -d 'Synchronize changes with upstream'
complete -c bingo-light -n __bingo_light_needs_command -a status  -d 'Show current status'
complete -c bingo-light -n __bingo_light_needs_command -a doctor  -d 'Diagnose and fix common problems'
complete -c bingo-light -n __bingo_light_needs_command -a auto-sync -d 'Enable or configure automatic synchronization'
complete -c bingo-light -n __bingo_light_needs_command -a log     -d 'Show change log'
complete -c bingo-light -n __bingo_light_needs_command -a undo    -d 'Undo the last operation'
complete -c bingo-light -n __bingo_light_needs_command -a diff    -d 'Show differences between states'
complete -c bingo-light -n __bingo_light_needs_command -a version -d 'Print version information'
complete -c bingo-light -n __bingo_light_needs_command -a help    -d 'Show help for a command'
complete -c bingo-light -n __bingo_light_needs_command -a conflict-analyze -d 'Analyze conflicts during rebase'
complete -c bingo-light -n __bingo_light_needs_command -a conflict-resolve -d 'Resolve a conflict file and continue'
complete -c bingo-light -n __bingo_light_needs_command -a config  -d 'Get/set/list configuration'
complete -c bingo-light -n __bingo_light_needs_command -a history -d 'Show sync history with hash mappings'
complete -c bingo-light -n __bingo_light_needs_command -a test    -d 'Run configured test suite'
complete -c bingo-light -n __bingo_light_needs_command -a workspace -d 'Manage multiple forks'
complete -c bingo-light -n __bingo_light_needs_command -a smart-sync -d 'Smart sync with circuit breaker and partial state'
complete -c bingo-light -n __bingo_light_needs_command -a session -d 'Manage session memory'

# Short aliases
complete -c bingo-light -n __bingo_light_needs_command -a p  -d 'Alias for patch'
complete -c bingo-light -n __bingo_light_needs_command -a s  -d 'Alias for sync'
complete -c bingo-light -n __bingo_light_needs_command -a st -d 'Alias for status'
complete -c bingo-light -n __bingo_light_needs_command -a d  -d 'Alias for diff'
complete -c bingo-light -n __bingo_light_needs_command -a ws -d 'Alias for workspace'

# Global flags
complete -c bingo-light -n __bingo_light_needs_command -s h -l help    -d 'Show help'
complete -c bingo-light -n __bingo_light_needs_command      -l version -d 'Show version'
complete -c bingo-light                                    -l json    -d 'Output structured JSON'
complete -c bingo-light                                    -l yes     -d 'Non-interactive mode, auto-confirm prompts'
complete -c bingo-light                               -s y            -d 'Non-interactive mode (short for --yes)'

# ---- sync flags (also alias "s") ----
complete -c bingo-light -n '__bingo_light_using_command sync s' -s n -l dry-run -d 'Show what would be done without making changes'
complete -c bingo-light -n '__bingo_light_using_command sync s' -s f -l force   -d 'Force sync, overwriting conflicts'
complete -c bingo-light -n '__bingo_light_using_command sync s' -s t -l test    -d 'Run test suite after sync'
complete -c bingo-light -n '__bingo_light_using_command sync s' -s h -l help    -d 'Show help'

# ---- status flags (also alias "st") ----
complete -c bingo-light -n '__bingo_light_using_command status st' -s h -l help -d 'Show help'

# ---- diff flags (also alias "d") ----
complete -c bingo-light -n '__bingo_light_using_command diff d' -s h -l help -d 'Show help'

# ---- Simple commands (no subcommands, just --help) ----
complete -c bingo-light -n '__bingo_light_using_command init'      -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command doctor'    -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command auto-sync' -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command log'       -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command undo'      -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command version'   -s h -l help -d 'Show help'

# ---- conflict-resolve flags ----
complete -c bingo-light -n '__bingo_light_using_command conflict-resolve' -s h -l help -d 'Show help'

# ---- help: complete with command names ----
complete -c bingo-light -n '__bingo_light_using_command help' -a 'init setup patch sync status doctor auto-sync log undo diff version conflict-analyze conflict-resolve config history test workspace smart-sync session' -d 'Command'

# ---- patch subcommands (also alias "p") ----
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a new     -d 'Create a new patch'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a list    -d 'List all patches'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a show    -d 'Show details of a patch'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a edit    -d 'Edit an existing patch'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a drop    -d 'Remove a patch'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a export  -d 'Export patches to files'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a import  -d 'Import patches from files'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a reorder -d 'Reorder the patch stack'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a squash  -d 'Squash two patches into one'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a meta    -d 'Get/set patch metadata'

# Patch short aliases
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a ls     -d 'Alias for list'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a add    -d 'Alias for new'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a create -d 'Alias for new'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a rm     -d 'Alias for drop'
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -a remove -d 'Alias for drop'

# Help flag for patch itself
complete -c bingo-light -n __bingo_light_patch_needs_subcommand -s h -l help -d 'Show help'

# ---- patch list / ls flags ----
complete -c bingo-light -n '__bingo_light_patch_using_subcommand list ls' -s v -l verbose -d 'Show detailed patch information'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand list ls' -s h -l help    -d 'Show help'

# ---- patch subcommands that only take --help ----
complete -c bingo-light -n '__bingo_light_patch_using_subcommand new add create'    -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand show'              -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand edit'              -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand drop rm remove'    -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand export'            -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand import'            -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand reorder'           -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand squash'            -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_patch_using_subcommand meta'              -s h -l help -d 'Show help'

# ---- workspace subcommands (also alias "ws") ----

# Returns true when we are inside "workspace" (or "ws") and need a workspace subcommand.
function __bingo_light_workspace_needs_subcommand
    set -l cmd (commandline -opc)
    if test (count $cmd) -lt 2
        return 1
    end
    if test "$cmd[2]" != workspace -a "$cmd[2]" != ws
        return 1
    end
    if test (count $cmd) -eq 2
        return 0
    end
    return 1
end

complete -c bingo-light -n __bingo_light_workspace_needs_subcommand -a init   -d 'Initialize workspace'
complete -c bingo-light -n __bingo_light_workspace_needs_subcommand -a add    -d 'Add a repo to workspace'
complete -c bingo-light -n __bingo_light_workspace_needs_subcommand -a remove -d 'Remove a repo from workspace'
complete -c bingo-light -n __bingo_light_workspace_needs_subcommand -a list   -d 'List workspace repos'
complete -c bingo-light -n __bingo_light_workspace_needs_subcommand -a sync   -d 'Sync all workspace repos'
complete -c bingo-light -n __bingo_light_workspace_needs_subcommand -a status -d 'Show workspace status'

# ---- New top-level command flags ----
complete -c bingo-light -n '__bingo_light_using_command conflict-analyze' -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command config'           -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command history'          -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command test'             -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command workspace ws'     -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command smart-sync'      -s h -l help -d 'Show help'
complete -c bingo-light -n '__bingo_light_using_command session'         -s h -l help -d 'Show help'

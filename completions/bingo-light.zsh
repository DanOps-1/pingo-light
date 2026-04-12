#compdef bingo-light
# Zsh completion for bingo-light
# Place in a directory listed in $fpath, or source directly.
#
# Usage:
#   source bingo-light.zsh
#   # or
#   cp bingo-light.zsh /usr/local/share/zsh/site-functions/_bingo-light

_bingo-light() {
    local -a toplevel_commands=(
        'init:Initialize a new bingo-light project'
        'patch:Manage patches'
        'sync:Synchronize changes with upstream'
        'status:Show current status'
        'doctor:Diagnose and fix common problems'
        'auto-sync:Enable or configure automatic synchronization'
        'log:Show change log'
        'undo:Undo the last operation'
        'diff:Show differences between states'
        'version:Print version information'
        'help:Show help for a command'
        'conflict-analyze:Analyze conflicts during rebase'
        'config:Get/set/list configuration'
        'history:Show sync history with hash mappings'
        'test:Run configured test suite'
        'workspace:Manage multiple forks'
        'smart-sync:Smart sync with circuit breaker and partial state'
        'session:Manage session memory'
    )

    local -a toplevel_aliases=(
        'p:Alias for patch'
        's:Alias for sync'
        'st:Alias for status'
        'd:Alias for diff'
        'ws:Alias for workspace'
    )

    local -a patch_subcommands=(
        'new:Create a new patch'
        'list:List all patches'
        'show:Show details of a patch'
        'edit:Edit an existing patch'
        'drop:Remove a patch'
        'export:Export patches to files'
        'import:Import patches from files'
        'reorder:Reorder the patch stack'
        'squash:Squash two patches into one'
        'meta:Get/set patch metadata'
    )

    local -a patch_aliases=(
        'ls:Alias for list'
        'add:Alias for new'
        'create:Alias for new'
        'rm:Alias for drop'
        'remove:Alias for drop'
    )

    local -a sync_flags=(
        '(-f --force)'{-f,--force}'[Force sync, overwriting conflicts]'
        '(-n --dry-run)'{-n,--dry-run}'[Show what would be done without making changes]'
        '(-t --test)'{-t,--test}'[Run test suite after sync]'
        '(- *)'{-h,--help}'[Show help]'
    )

    local -a patch_list_flags=(
        '(-v --verbose)'{-v,--verbose}'[Show detailed patch information]'
        '(- *)'{-h,--help}'[Show help]'
    )

    local -a global_flags=(
        '(- *)'{-h,--help}'[Show help]'
        '(- *)--version[Show version]'
        '--json[Output structured JSON]'
        '(-y --yes)'{-y,--yes}'[Non-interactive mode, auto-confirm prompts]'
    )

    local -a help_flag=(
        '(- *)'{-h,--help}'[Show help]'
    )

    # Determine which command we are completing for.
    local curcontext="$curcontext" state line
    typeset -A opt_args

    _arguments -C \
        '(- *)'{-h,--help}'[Show help]' \
        '(- *)--version[Show version]' \
        '--json[Output structured JSON]' \
        '(-y --yes)'{-y,--yes}'[Non-interactive mode, auto-confirm prompts]' \
        '1:command:->command' \
        '*::arg:->args' && return

    case $state in
        command)
            _describe -t commands 'bingo-light command' toplevel_commands
            _describe -t aliases 'short alias' toplevel_aliases
            ;;
        args)
            local cmd="${line[1]}"
            case $cmd in
                patch|p)
                    _arguments -C \
                        '(- *)'{-h,--help}'[Show help]' \
                        '1:subcommand:->patch_subcmd' \
                        '*::arg:->patch_args' && return

                    case $state in
                        patch_subcmd)
                            _describe -t subcommands 'patch subcommand' patch_subcommands
                            _describe -t aliases 'short alias' patch_aliases
                            ;;
                        patch_args)
                            local subcmd="${line[1]}"
                            case $subcmd in
                                list|ls)
                                    _arguments $patch_list_flags
                                    ;;
                                new|add|create|show|edit|drop|rm|remove|export|import|reorder|squash|meta)
                                    _arguments $help_flag
                                    ;;
                            esac
                            ;;
                    esac
                    ;;
                sync|s)
                    _arguments $sync_flags
                    ;;
                status|st)
                    _arguments $help_flag
                    ;;
                diff|d)
                    _arguments $help_flag
                    ;;
                init|doctor|auto-sync|log|undo|version|conflict-analyze|config|history|test|workspace|ws|smart-sync|session)
                    _arguments $help_flag
                    ;;
                help)
                    _describe -t commands 'command' toplevel_commands
                    ;;
            esac
            ;;
    esac
}

_bingo-light "$@"

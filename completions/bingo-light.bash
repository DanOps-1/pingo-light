# Bash completion for bingo-light
# Source this file or place it in /etc/bash_completion.d/
#
# Usage:
#   source bingo-light.bash
#   # or
#   cp bingo-light.bash /etc/bash_completion.d/bingo-light

_bingo_light() {
    local cur prev words cword
    _init_completion || return

    local -r toplevel_commands="init setup patch sync status doctor auto-sync log undo diff version help conflict-analyze conflict-resolve config history test workspace smart-sync session"
    local -r toplevel_aliases="p s st d ws"
    local -r all_toplevel="${toplevel_commands} ${toplevel_aliases}"

    local -r patch_subcommands="new list show edit drop export import reorder squash meta"
    local -r patch_aliases="ls add create rm remove"
    local -r all_patch="${patch_subcommands} ${patch_aliases}"

    # Walk backward through the command line to find the active command context.
    local cmd=""
    local subcmd=""
    local i
    for (( i=1; i < cword; i++ )); do
        case "${words[i]}" in
            patch|p)
                cmd="patch"
                ;;
            sync|s)
                cmd="sync"
                ;;
            status|st)
                cmd="status"
                ;;
            diff|d)
                cmd="diff"
                ;;
            init|setup|doctor|auto-sync|log|undo|version|help|conflict-analyze|conflict-resolve|config|history|test|workspace|ws|smart-sync|session)
                cmd="${words[i]}"
                ;;
            *)
                # If we already have a command, this may be a subcommand.
                if [[ -n "$cmd" && -z "$subcmd" ]]; then
                    subcmd="${words[i]}"
                fi
                ;;
        esac
    done

    # ---- Completions based on context ----

    # Inside "patch" (or alias "p") -- complete subcommands and flags
    if [[ "$cmd" == "patch" ]]; then
        # If a subcommand is already chosen, offer its flags
        case "$subcmd" in
            list|ls)
                COMPREPLY=( $(compgen -W "-v --verbose --help -h" -- "$cur") )
                return
                ;;
            new|add|create|show|edit|drop|rm|remove|export|import|reorder)
                COMPREPLY=( $(compgen -W "--help -h" -- "$cur") )
                return
                ;;
        esac

        # No subcommand yet -- offer patch subcommands (including aliases)
        if [[ "$cur" == -* ]]; then
            COMPREPLY=( $(compgen -W "--help -h" -- "$cur") )
        else
            COMPREPLY=( $(compgen -W "${all_patch}" -- "$cur") )
        fi
        return
    fi

    # Inside "sync" (or alias "s") -- complete flags
    if [[ "$cmd" == "sync" ]]; then
        COMPREPLY=( $(compgen -W "--dry-run -n --force -f --help -h" -- "$cur") )
        return
    fi

    # Inside "status" (or alias "st")
    if [[ "$cmd" == "status" ]]; then
        COMPREPLY=( $(compgen -W "--help -h" -- "$cur") )
        return
    fi

    # Inside "diff" (or alias "d")
    if [[ "$cmd" == "diff" ]]; then
        COMPREPLY=( $(compgen -W "--help -h" -- "$cur") )
        return
    fi

    # Inside "workspace" (or alias "ws") -- complete subcommands
    if [[ "$cmd" == "workspace" || "$cmd" == "ws" ]]; then
        if [[ -z "$subcmd" ]]; then
            COMPREPLY=( $(compgen -W "init add remove list sync status" -- "$cur") )
        else
            COMPREPLY=( $(compgen -W "--help -h" -- "$cur") )
        fi
        return
    fi

    # Other known commands that take no further subcommands
    if [[ -n "$cmd" ]]; then
        COMPREPLY=( $(compgen -W "--help -h" -- "$cur") )
        return
    fi

    # Top-level: no command selected yet
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "--help -h --version --json --yes -y" -- "$cur") )
    else
        COMPREPLY=( $(compgen -W "${all_toplevel}" -- "$cur") )
    fi
}

complete -F _bingo_light bingo-light

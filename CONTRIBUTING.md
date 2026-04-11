# Contributing to bingo-light

Thanks for your interest in contributing! This guide covers everything you need.

## Quick setup

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make test    # run 71 tests
make lint    # shellcheck
```

## Reporting bugs

Open an issue using the **Bug Report** template. Include:
- bingo-light version (`bingo-light version`)
- OS and bash version (`bash --version`)
- Steps to reproduce and error output

## Submitting changes

1. Fork the repository and create a feature branch from `main`
2. Make your changes
3. Run `make test` and `make lint`
4. Add tests for new functionality (see `tests/test.sh`)
5. Open a pull request against `main`

## Project structure

```
bingo-light          # Main CLI (single bash script)
mcp-server.py        # MCP server (zero-dep Python 3)
agent.py             # Advisor agent
tui.py               # Terminal dashboard
install.sh           # Interactive installer
tests/test.sh        # Test suite (71 tests)
completions/         # bash/zsh/fish tab completion
contrib/hooks/       # Example notification hooks
docs/                # Additional documentation
```

## Code style

- **Single-file CLI**: `bingo-light` is one bash script. Keep it that way.
- **ShellCheck clean**: all code must pass `shellcheck` with zero warnings
- **snake_case** for variables and functions
- **No shell variable interpolation** in `python3 -c` calls -- pass data via stdin
- Prefer clarity over cleverness

## Commit messages

Use conventional-style messages:

```
feat: add patch squash command
fix: json_escape handling of newlines
docs: update MCP tool count in README
test: add conflict-analyze edge case
```

## Tests

Tests are in `tests/test.sh`. The pattern:

```bash
run patch list                    # capture output
has "test-feature"                # assert output contains string
pass "patch list shows patches"   # report result
```

## No CLA required

By submitting a pull request you agree that your contribution is licensed under the MIT License.

# Contributing to bingo-light

Thanks for your interest in contributing! This guide covers everything you need.

## Quick setup

```bash
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light
make test      # run core test suite
make test-all  # all 250 tests
make lint      # python syntax + flake8 + shellcheck
```

## Reporting bugs

Open an issue using the **Bug Report** template. Include:
- bingo-light version (`bingo-light version`)
- OS and Python version (`python3 --version`)
- Steps to reproduce and error output

## Submitting changes

1. Fork the repository and create a feature branch from `main`
2. Make your changes
3. Run `make test` and `make lint`
4. Add tests for new functionality (see `tests/test.sh`)
5. Open a pull request against `main`

## Project structure

```
bingo-light          # Python CLI (entry point)
bingo_core/          # Core library package (all business logic)
mcp-server.py        # MCP server (zero-dep Python 3, 29 tools)
contrib/agent.py     # Advisor agent
contrib/tui.py       # Terminal dashboard
install.sh           # Installer (POSIX sh, CI-friendly)
tests/               # Test suites (250 tests across 5 files)
completions/         # bash/zsh/fish tab completion
contrib/hooks/       # Example notification hooks
docs/                # Additional documentation
```

## Code style

- **CLI + core package**: `bingo-light` is the entry point, `bingo_core/` package has all logic. Keep the separation.
- **Flake8 clean**: all Python code must pass flake8
- **ShellCheck clean**: all bash code must pass shellcheck
- **snake_case** for variables and functions
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

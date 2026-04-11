# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

For **exploitable vulnerabilities**, please report privately via [GitHub Security Advisories](https://github.com/DanOps-1/bingo-light/security/advisories) or email the maintainer directly. Do not open a public issue.

For **non-exploitable security improvements**, a regular issue with the `security` label is fine.

We aim to acknowledge reports within 48 hours and release fixes within 7 days.

## Security Model

- **MCP server**: all file paths validated using `pathlib.Path.resolve().relative_to()` to prevent path traversal (including symlink bypass)
- **CLI**: no `eval` of user input. Config values are passed to git commands, never executed as shell code
- **Python calls**: all `python3 -c` invocations pass data via stdin, never through shell variable interpolation
- **Agent**: LLM responses are used for analysis and reporting only, never executed as code
- **Hooks**: user-installed executables in `.bingo/hooks/`. No hooks are shipped active by default
- **Config isolation**: `.bingolight` is excluded from git tracking via `.git/info/exclude`

## Known Considerations

- `BINGO_DESCRIPTION` environment variable is sanitized through git commit message handling
- The `auto-sync` GitHub Actions workflow requires a `GITHUB_TOKEN` with write permissions
- Patch export produces standard `.patch` files -- verify content before applying to untrusted repos

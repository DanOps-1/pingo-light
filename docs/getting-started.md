# Getting Started

## Install

### pip / pipx

```bash
pip install bingo-light
bingo-light setup          # interactive — choose which AI tools to configure
```

### npm / npx

```bash
npm install -g bingo-light && bingo-light setup
```

### Other quick methods

```bash
brew install DanOps-1/tap/bingo-light  # Homebrew
curl -fsSL https://raw.githubusercontent.com/DanOps-1/bingo-light/main/install.sh | sh  # Shell
```

### Other methods

```bash
# From source
git clone https://github.com/DanOps-1/bingo-light.git
cd bingo-light && make install

# Manual
sudo cp bingo-light /usr/local/bin/ && chmod +x /usr/local/bin/bingo-light

# Just use from the repo
./bingo-light --help
```

**Requirements:** Python 3.8+, git 2.20+

## 5-Minute Quickstart

```bash
# 1. You have a forked project
cd my-forked-project

# 2. Initialize (point to the original repo)
bingo-light init https://github.com/original/project.git

# 3. Make your customizations
vim src/feature.py

# 4. Save as a named patch
bingo-light patch new my-custom-feature

# 5. Check status anytime
bingo-light status

# 6. Sync with upstream when ready
bingo-light sync
```

## For AI Agents

```bash
# Non-interactive, structured output
bingo-light status --json --yes
bingo-light sync --json --yes
bingo-light conflict-analyze --json
BINGO_DESCRIPTION="add feature" bingo-light patch new feat --yes
```

## MCP Integration

Add to `~/.claude/settings.json` or `.mcp.json`:

```json
{
  "mcpServers": {
    "bingo-light": {
      "command": "python3",
      "args": ["/path/to/mcp-server.py"]
    }
  }
}
```

29 MCP tools are available. See the [README](../README.md#for-ai-agents) for the full list.

## Next steps

- [Concepts](concepts.md) -- branch model, patch stack, sync flow
- [Configuration](../README.md#configuration) -- hooks, test integration, workspace
- [FAQ](../README.md#faq) -- common questions

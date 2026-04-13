#!/usr/bin/env node
// bingo-light MCP server wrapper for npm distribution.
// Used by MCP clients: {"command": "npx", "args": ["-y", "bingo-light", "mcp"]}

"use strict";

const { execFileSync } = require("child_process");
const path = require("path");

const script = path.join(__dirname, "..", "mcp-server.py");

const pythons = ["python3", "python"];
let python = null;

for (const cmd of pythons) {
  try {
    const ver = execFileSync(cmd, ["--version"], {
      stdio: ["pipe", "pipe", "pipe"],
    }).toString().trim();
    const match = ver.match(/(\d+)\.(\d+)/);
    if (match && (parseInt(match[1]) > 3 || (parseInt(match[1]) === 3 && parseInt(match[2]) >= 8))) {
      python = cmd;
      break;
    }
  } catch (_) {
    // not found, try next
  }
}

if (!python) {
  process.stderr.write(
    "error: Python 3.8+ is required but not found.\n" +
    "Install Python from https://python.org and try again.\n"
  );
  process.exit(1);
}

try {
  execFileSync(python, [script, ...process.argv.slice(2)], {
    stdio: "inherit",
    env: process.env,
  });
} catch (e) {
  process.exit(e.status || 1);
}

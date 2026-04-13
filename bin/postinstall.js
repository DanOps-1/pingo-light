#!/usr/bin/env node
// Post-install hook: run `bingo-light setup` if in an interactive terminal.
// In CI / non-TTY environments, just print a hint.

"use strict";

const { execFileSync, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const isTTY = process.stdout.isTTY && process.stdin.isTTY;
const isCI = process.env.CI === "true" || process.env.NONINTERACTIVE === "1";

const script = path.join(__dirname, "..", "bingo-light");

// Find python3
function findPython() {
  for (const cmd of ["python3", "python"]) {
    try {
      const ver = execFileSync(cmd, ["--version"], {
        stdio: ["pipe", "pipe", "pipe"],
      }).toString().trim();
      const m = ver.match(/(\d+)\.(\d+)/);
      if (m && (parseInt(m[1]) > 3 || (parseInt(m[1]) === 3 && parseInt(m[2]) >= 8))) {
        return cmd;
      }
    } catch (_) {}
  }
  return null;
}

const python = findPython();

if (!python) {
  console.log("\n  \x1b[33m!\x1b[0m Python 3.8+ not found — run \x1b[1mbingo-light setup\x1b[0m after installing Python.\n");
  process.exit(0);
}

if (isTTY && !isCI) {
  // Interactive: run setup directly
  try {
    execFileSync(python, [script, "setup"], { stdio: "inherit" });
  } catch (e) {
    // setup failed or user cancelled — not fatal
    process.exit(0);
  }
} else {
  // Non-interactive: print hint
  console.log("\n  \x1b[32m✓\x1b[0m bingo-light installed");
  console.log("  Run \x1b[1mbingo-light setup\x1b[0m to configure MCP for your AI tools.\n");
}

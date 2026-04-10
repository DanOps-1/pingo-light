#!/usr/bin/env bash
# pingo-light installer
set -euo pipefail

INSTALL_DIR="${1:-/usr/local/bin}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -w "$INSTALL_DIR" ]]; then
    echo "Installing to $INSTALL_DIR (requires sudo)..."
    sudo cp "$SCRIPT_DIR/pingo-light" "$INSTALL_DIR/pingo-light"
    sudo chmod +x "$INSTALL_DIR/pingo-light"
else
    cp "$SCRIPT_DIR/pingo-light" "$INSTALL_DIR/pingo-light"
    chmod +x "$INSTALL_DIR/pingo-light"
fi

echo "pingo-light installed to $INSTALL_DIR/pingo-light"
echo "Run 'pingo-light --help' to get started."

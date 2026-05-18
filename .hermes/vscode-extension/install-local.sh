#!/usr/bin/env bash
set -euo pipefail

SRC="/Volumes/Satechi Hub/warbird-pro/.hermes/vscode-extension"
DST="/Users/zincdigital/.vscode/extensions/warbird-hermes-0.1.0"

mkdir -p "/Users/zincdigital/.vscode/extensions"
rm -rf "$DST"
cp -R "$SRC" "$DST"
printf 'Installed Warbird Hermes VS Code extension to %s\n' "$DST"
printf 'Reload VS Code, then click the Hermes activity-bar icon.\n'

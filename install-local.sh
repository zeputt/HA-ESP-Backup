#!/usr/bin/env bash
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/esphome_backup"
DEST="/addons/esphome_backup"
mkdir -p /addons
rm -rf "$DEST"
cp -a "$SRC" "$DEST"
echo "Installed ESPHome Backup to $DEST"
echo "Now run 'Check for updates' in Home Assistant App store."

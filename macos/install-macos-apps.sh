#!/bin/bash
# Radio Gremlin (optional, macOS) — build Gremlin Control Center and the helper apps from source
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
#
# Usage: macos/install-macos-apps.sh [--dir DIR] [--dest FOLDER] [--sleep-prevention]
#   --dir               Radio Gremlin install directory (default: ~/RadioGremlin)
#   --dest              where to put the apps (default: <dir>/apps)
#   --sleep-prevention  also install and load a LaunchAgent that runs /usr/bin/caffeinate -i -s
#
# Needs the Xcode Command Line Tools (swiftc) and osacompile (built into macOS).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/RadioGremlin"
DEST=""
SLEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --dest) DEST="$2"; shift 2 ;;
    --sleep-prevention) SLEEP=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
DIR="${DIR/#\~/$HOME}"
DEST="${DEST:-$DIR/apps}"
[ "$(uname)" = "Darwin" ] || { echo "macOS only" >&2; exit 1; }
[ -d "$DIR/scripts" ] || { echo "No Radio Gremlin install at $DIR (run ./install.sh first)" >&2; exit 1; }
command -v swiftc >/dev/null || { echo "swiftc not found: install the Xcode Command Line Tools (xcode-select --install)" >&2; exit 1; }
mkdir -p "$DEST"

# 1. Gremlin Control Center (native app bundle)
APP="$DEST/Gremlin Control Center.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
swiftc -O -o "$APP/Contents/MacOS/ControlCenter" "$HERE/control-center/ControlCenter.swift"
/usr/bin/python3 - "$APP/Contents/Info.plist" "$DIR" <<'PY'
import plistlib, sys
plistlib.dump({
    "CFBundleName": "Gremlin Control Center",
    "CFBundleIdentifier": "com.radiogremlin.controlcenter",
    "CFBundleExecutable": "ControlCenter",
    "CFBundlePackageType": "APPL",
    "CFBundleVersion": "1.0",
    "CFBundleShortVersionString": "1.0",
    "NSHighResolutionCapable": True,
    "RadioGremlinDir": sys.argv[2],
}, open(sys.argv[1], "wb"))
PY
codesign --force --sign - "$APP" >/dev/null 2>&1 || true   # ad-hoc signature for local use
echo "Built: $APP"

# 2. Helper apps (AppleScript applets) from the .applescript sources
for src in "$HERE"/helper-apps/*.applescript; do
  name="$(basename "$src" .applescript)"
  tmp="$(mktemp -t radiogremlin).applescript"
  sed "s|__RADIO_GREMLIN_DIR__|$DIR|g" "$src" > "$tmp"
  rm -rf "$DEST/$name.app"
  osacompile -o "$DEST/$name.app" "$tmp"
  rm -f "$tmp"
  echo "Built: $DEST/$name.app"
done

# 3. Optional sleep prevention
if [ "$SLEEP" -eq 1 ]; then
  AGENT="$HOME/Library/LaunchAgents/com.radiogremlin.caffeinate.plist"
  mkdir -p "$(dirname "$AGENT")"
  cp "$HERE/launchagent/com.radiogremlin.caffeinate.plist" "$AGENT"
  launchctl unload "$AGENT" 2>/dev/null || true
  launchctl load "$AGENT"
  echo "Sleep prevention installed and loaded: $AGENT"
fi

echo
echo "Done. Open \"$APP\" to control Radio Gremlin."
echo "macOS may ask you to allow the apps the first time (they are built and signed locally)."

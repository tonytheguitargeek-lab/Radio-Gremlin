#!/bin/bash
# Radio Gremlin V0.1 (Experimental Preview) — installer
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
#
# Builds a fresh Radio Gremlin install:
#   <dir>/meshing-around   Meshing Around at the pinned upstream commit + the Radio Gremlin patch + add-ons
#   <dir>/scripts          start / stop / status scripts
#
# Usage: ./install.sh [--dir DIR] [--radio HOST[:PORT]] [--upstream GIT_URL] [--skip-deps]
#   --dir        install location (default: ~/RadioGremlin). Must not already contain meshing-around/.
#   --radio      radio address for config.ini, e.g. 192.0.2.10 or 192.0.2.10:4403 (can be set later)
#   --upstream   Meshing Around git URL (default: the official GitHub repository)
#   --skip-deps  don't create the Python virtual environment (you must provide meshing-around/venv)
set -euo pipefail

UPSTREAM_URL="https://github.com/SpudGunMan/meshing-around.git"
UPSTREAM_COMMIT="897cc793e0dcc449464fe2a0f84619812948d90f"   # tested base (2026-11-22)
REPO="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/RadioGremlin"
RADIO=""
SKIP_DEPS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --radio) RADIO="$2"; shift 2 ;;
    --upstream) UPSTREAM_URL="$2"; shift 2 ;;
    --skip-deps) SKIP_DEPS=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 (3.9 or newer) is required" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "python3 3.9 or newer is required" >&2; exit 1; }

DIR="${DIR/#\~/$HOME}"
MA="$DIR/meshing-around"
if [ -e "$MA" ]; then
  echo "Refusing to continue: $MA already exists." >&2
  echo "This installer never modifies an existing install. Choose another --dir, or move the old one aside." >&2
  exit 1
fi
mkdir -p "$DIR"

say "Fetching Meshing Around ($UPSTREAM_URL) at ${UPSTREAM_COMMIT:0:7}"
git clone --quiet "$UPSTREAM_URL" "$MA"
git -C "$MA" -c advice.detachedHead=false checkout --quiet "$UPSTREAM_COMMIT"
[ "$(git -C "$MA" rev-parse HEAD)" = "$UPSTREAM_COMMIT" ] || { echo "Upstream commit check failed" >&2; exit 1; }

say "Applying the Radio Gremlin patch"
git -C "$MA" apply --check "$REPO/meshing-around-patch/radio-gremlin.patch"
git -C "$MA" apply "$REPO/meshing-around-patch/radio-gremlin.patch"

say "Adding Radio Gremlin components"
cp "$REPO"/gremlin/*.py "$MA/"
[ -f "$MA/gremlin.ini" ] || cp "$REPO/config/gremlin.example.ini" "$MA/gremlin.ini"
mkdir -p "$DIR/scripts"
cp "$REPO"/scripts/*.sh "$DIR/scripts/"
chmod +x "$DIR"/scripts/*.sh
chmod -x "$DIR/scripts/_common.sh"

if [ ! -f "$MA/config.ini" ]; then
  cp "$MA/config.template" "$MA/config.ini"
  echo "Created config.ini from Meshing Around's config.template"
fi
if [ -n "$RADIO" ]; then
  say "Setting the radio address in config.ini ([interface] type = tcp, hostname = $RADIO)"
  python3 - "$MA/config.ini" "$RADIO" <<'PY'
import re, sys
path, radio = sys.argv[1], sys.argv[2]
text = open(path).read()
m = re.search(r"(?ms)^\[interface\]\n(.*?)(?=^\[|\Z)", text)
if not m:
    sys.exit("No [interface] section found in config.ini")
section = m.group(1)
section = re.sub(r"(?m)^type\s*=.*$", "type = tcp", section, count=1)
if re.search(r"(?m)^#?\s*hostname\s*=", section):
    section = re.sub(r"(?m)^#?\s*hostname\s*=.*$", "hostname = " + radio, section, count=1)
else:
    section = "hostname = %s\n" % radio + section
open(path, "w").write(text[:m.start(1)] + section + text[m.end(1):])
PY
fi

if [ "$SKIP_DEPS" -eq 0 ]; then
  say "Creating the Python virtual environment and installing Meshing Around's requirements"
  python3 -m venv "$MA/venv"
  "$MA/venv/bin/python" -m pip install --quiet --upgrade pip
  "$MA/venv/bin/python" -m pip install --quiet -r "$MA/requirements.txt"
else
  say "Skipping Python dependencies (--skip-deps)"
fi

say "Done. Radio Gremlin is installed in $DIR"
cat <<EOF

Next steps:
  1. Edit $MA/config.ini: under [interface] set "type = tcp" and "hostname = <radio IP>[:port]"
     (already done if you used --radio), and set your bot name and features.
  2. Review $MA/gremlin.ini (API and Observatory stay on 127.0.0.1 unless you change them).
  3. Start:   $DIR/scripts/start-gremlin.sh   and   $DIR/scripts/start-observatory.sh
     Status:  $DIR/scripts/status.sh
     Stop:    $DIR/scripts/stop-gremlin.sh    and   $DIR/scripts/stop-observatory.sh
  4. Optional (macOS): ./macos/install-macos-apps.sh --dir "$DIR"

Only one program can hold the radio's TCP connection reliably. Close the Meshtastic app or any other
client that is connected to the same radio over Wi-Fi before starting Radio Gremlin.
EOF

#!/bin/bash
# Radio Gremlin — follow the Gremlin bot log
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
source "$(dirname "$0")/_common.sh"

log="$RG_DIR/gremlin-live.log"
touch "$log"
if [ "$(uname)" = "Darwin" ] && [ ! -t 1 ]; then
  # Started from the Control Center or a helper app: open the log in Terminal
  osascript -e "tell application \"Terminal\" to do script \"tail -n 50 -F \" & quoted form of \"$log\"" -e 'tell application "Terminal" to activate' >/dev/null
else
  exec tail -n 50 -F "$log"
fi

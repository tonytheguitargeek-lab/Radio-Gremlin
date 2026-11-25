#!/bin/bash
# Radio Gremlin — start the Gremlin Watchdog, which starts the bot once the radio is reachable
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
source "$(dirname "$0")/_common.sh"

if pid="$(rg_pid watchdog)"; then echo "Gremlin Watchdog is already running (PID $pid)."; exit 0; fi
if pid="$(rg_pid gremlin)"; then echo "A Gremlin bot from this install is still running (PID $pid). Run stop-gremlin.sh first."; exit 1; fi

cd "$RG_DIR"
nohup "$RG_PY" -u gremlin_watchdog.py >> watchdog-live.log 2>&1 < /dev/null &
echo "Gremlin Watchdog starting (PID $!). Logs: $RG_DIR/watchdog-live.log and gremlin-live.log"

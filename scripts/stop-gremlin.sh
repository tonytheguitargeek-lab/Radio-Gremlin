#!/bin/bash
# Radio Gremlin — stop the Gremlin Watchdog and the bot it started (this install only)
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
source "$(dirname "$0")/_common.sh"

if pid="$(rg_pid watchdog)"; then echo "Stopping Gremlin Watchdog (PID $pid)..."; rg_stop_pid "$pid" 20; fi
# The watchdog stops its bot on exit; this catches a bot left behind if the watchdog was killed
if pid="$(rg_pid gremlin)"; then echo "Stopping Gremlin bot (PID $pid)..."; rg_stop_pid "$pid" 15; fi
rm -f "$RG_DIR/gremlin.pid" "$RG_DIR/watchdog.pid"
echo "Radio Gremlin stopped."

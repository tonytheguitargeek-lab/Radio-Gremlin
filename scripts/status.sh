#!/bin/bash
# Radio Gremlin — show what is running in this install
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
set -uo pipefail
source "$(dirname "$0")/_common.sh"

show() { if pid="$(rg_pid "$1")"; then printf "%-18s RUNNING (PID %s)\n" "$2" "$pid"; else printf "%-18s stopped\n" "$2"; fi; }
show watchdog "Gremlin Watchdog"
show gremlin "Radio Gremlin bot"
show observatory "Mesh Observatory"

radio="$(cd "$RG_DIR" && "$RG_PY" -c 'import gremlin_settings as g; print(g.radio_description(g.load()))')"
api="$(rg_setting api_url 2>/dev/null)"

if (cd "$RG_DIR" && "$RG_PY" -c 'import gremlin_settings as g; raise SystemExit(0 if g.current_radio_connected() else 1)'); then
    printf "%-18s CONNECTED (%s)\n" "Radio Link" "$radio"
else
    printf "%-18s not connected (%s)\n" "Radio Link" "$radio"
fi

if curl -fsS -m 3 "$api/status" >/dev/null 2>&1; then printf "%-18s ONLINE (%s)\n" "Mesh Command API" "$api"; else printf "%-18s offline (%s)\n" "Mesh Command API" "$api"; fi

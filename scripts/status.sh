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

radio="$(rg_setting radio_host 2>/dev/null):$(rg_setting radio_port 2>/dev/null)"
api="$(rg_setting api_url 2>/dev/null)"
if pid="$(rg_pid gremlin)" && lsof -nP -a -p "$pid" -iTCP@"$radio" -sTCP:ESTABLISHED >/dev/null 2>&1; then
  printf "%-18s CONNECTED (%s)\n" "Radio TCP" "$radio"
else
  printf "%-18s not connected (%s)\n" "Radio TCP" "$radio"
fi
if curl -fsS -m 3 "$api/status" >/dev/null 2>&1; then printf "%-18s ONLINE (%s)\n" "Mesh Command API" "$api"; else printf "%-18s offline (%s)\n" "Mesh Command API" "$api"; fi

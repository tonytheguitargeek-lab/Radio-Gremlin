#!/bin/bash
# Radio Gremlin — stop Mesh Observatory (this install only)
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
source "$(dirname "$0")/_common.sh"

if pid="$(rg_pid observatory)"; then echo "Stopping Mesh Observatory (PID $pid)..."; rg_stop_pid "$pid" 10; else echo "Mesh Observatory is not running."; fi
rm -f "$RG_DIR/observatory.pid"

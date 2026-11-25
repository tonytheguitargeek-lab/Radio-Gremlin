#!/bin/bash
# Radio Gremlin — start Mesh Observatory
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
source "$(dirname "$0")/_common.sh"

if pid="$(rg_pid observatory)"; then echo "Mesh Observatory is already running (PID $pid)."; exit 0; fi
cd "$RG_DIR"
nohup "$RG_PY" -u mesh_observatory.py >> observatory-live.log 2>&1 < /dev/null &
echo "Mesh Observatory starting (PID $!): http://$(rg_setting obs_bind):$(rg_setting obs_port)"

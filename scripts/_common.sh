# Radio Gremlin — shared helpers for the scripts in this folder (sourced, not run directly)
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only

RG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RG_DIR="$RG_ROOT/meshing-around"
RG_PY="$RG_DIR/venv/bin/python"

# PID from <name>.pid if that process is still running (this installation only)
rg_pid() {
  local f="$RG_DIR/$1.pid" pid
  [ -f "$f" ] || return 1
  pid="$(cat "$f" 2>/dev/null)"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null && echo "$pid"
}

# Value from the Radio Gremlin settings, e.g. rg_setting obs_port
rg_setting() {
  (cd "$RG_DIR" && "$RG_PY" -c "import gremlin_settings as g; print(getattr(g.load(), '$1'))")
}

# Send SIGTERM to a pid and wait up to $2 seconds for it to exit
rg_stop_pid() {
  local pid="$1" wait="${2:-15}"
  kill -TERM "$pid" 2>/dev/null || return 0
  for _ in $(seq 1 "$wait"); do kill -0 "$pid" 2>/dev/null || return 0; sleep 1; done
  echo "PID $pid did not exit after ${wait}s; sending SIGKILL"
  kill -KILL "$pid" 2>/dev/null || true
}

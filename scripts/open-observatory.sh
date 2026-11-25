#!/bin/bash
# Radio Gremlin — open the Mesh Observatory dashboard
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
source "$(dirname "$0")/_common.sh"

host="$(rg_setting obs_bind)"; [ "$host" = "0.0.0.0" ] && host="127.0.0.1"
url="http://$host:$(rg_setting obs_port)"
if [ "$(uname)" = "Darwin" ]; then
  # A clean app-style window in Google Chrome if installed, otherwise the default browser
  if [ -d "/Applications/Google Chrome.app" ]; then open -na "Google Chrome" --args --app="$url"; else open "$url"; fi
else
  xdg-open "$url" >/dev/null 2>&1 || echo "Open $url in a browser"
fi

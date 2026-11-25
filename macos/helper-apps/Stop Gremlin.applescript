-- Radio Gremlin helper app (source). Built by macos/install-macos-apps.sh, which replaces __RADIO_GREMLIN_DIR__.
-- Copyright (C) 2026 Bad Audio Guy
-- SPDX-License-Identifier: GPL-3.0-only

set rgScript to "__RADIO_GREMLIN_DIR__/scripts/stop-gremlin.sh"
set msg to do shell script quoted form of rgScript
display notification msg with title "Stop Gremlin"

# Changelog

## V0.1, Experimental Preview (2026-11-25)

First public release, published after requests from the Meshtastic community on Reddit.

Components:

- **Meshing Around patch** against upstream commit `897cc79`:
  - MQTT text messages get no bot reply.
  - Starts the Mesh Command API.
  - Reconnect hardening.
- **Mesh Command API V1.4:** read-only HTTP API (`/status`, `/nodes`, `/traffic`, `/mapnodes`) that
  runs inside the bot. Local-only by default.
- **Mesh Command CYD firmware V1.4:** touchscreen monitor for the ESP32-2432S028R.
- **Mesh Observatory V1.7:** SQLite-backed dashboard with System Health, RF Watch, Mesh Radar,
  RF Signal Analysis and Node Directory.
- **Gremlin Watchdog V1.0:** monitors the radio TCP link and restarts the bot after failures.
- **Gremlin Control Center V1.0** (optional, macOS), plus helper app sources and an optional
  sleep-prevention LaunchAgent.

Changes from the author's private build:

- Network addresses moved into `gremlin.ini` and Meshing Around's `config.ini`. The API and
  Observatory default to `127.0.0.1`.
- CYD Wi-Fi credentials and the API address moved into a git-ignored `secrets.h`.
- Start and stop now use pid files, so they only affect their own install. Previously they stopped
  any matching process on the machine.
- Helper apps ship as AppleScript source and are built by `macos/install-macos-apps.sh`.
- Sleep-prevention LaunchAgent label changed to `com.radiogremlin.caffeinate`.

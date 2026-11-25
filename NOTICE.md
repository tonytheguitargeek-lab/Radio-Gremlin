# Notices and attribution

## Radio Gremlin

Copyright (C) 2026 Bad Audio Guy (https://badaudioguy.com).
Licensed under the **GNU General Public License version 3** (see `LICENSE`).

Developed by Bad Audio Guy with AI-assisted development using **ChatGPT ("Scout")** and **Claude
("the Nerd")**.

## Meshing Around (upstream)

Radio Gremlin is built on, and patches, **Meshing Around** by **Kelly Keeton, K7MHI
(SpudGunMan)**, and its contributors.

- Source: https://github.com/SpudGunMan/meshing-around
- License: GNU General Public License v3
- Base used by this release: commit `897cc793e0dcc449464fe2a0f84619812948d90f` (2026-11-22)

Meshing Around's own copyright and author notices are preserved unchanged. This repository does not
redistribute Meshing Around's code, apart from the context lines in the patch. `install.sh`
downloads it from the upstream repository and applies the patch.

### Modifications (GPLv3 section 5)

`meshing-around-patch/radio-gremlin.patch` modifies two upstream files. Each modified file carries a
notice ("Modified for Radio Gremlin by Bad Audio Guy, November 2026"), and each change is marked
"Radio Gremlin modification".

- **`mesh_bot.py`**
  - Text messages received via MQTT are logged and never answered.
  - Starts the Mesh Command API (`mesh_command.py`).
  - Imports `datetime` under an alias to avoid a name clash.
- **`modules/system.py`**
  - A disconnect flags the interface for retry instead of closing it.
  - Flagged interfaces are always retried, and retries continue instead of the bot exiting at the
    maximum retry count.
  - Imports `pickle`, which the leaderboard save/load code uses.

The Mesh Command API runs inside the Meshing Around process and is licensed GPLv3. So is everything
else in this repository.

## Third-party components (not included; installed or loaded separately)

| Component | Use | License |
|---|---|---|
| Meshtastic Python library and PyPubSub | Meshing Around dependencies (installed by pip) | GPL-3.0 / BSD-2-Clause |
| Other Meshing Around requirements (`requirements.txt`) | installed by pip | their own licenses |
| TFT_eSPI (Bodmer) | CYD display | MIT, with BSD-licensed Adafruit GFX portions |
| XPT2046_Touchscreen (Paul Stoffregen) | CYD touch | MIT-style |
| ArduinoJson (Benoît Blanchon) | CYD JSON parsing | MIT |
| ESP32 Arduino core (Espressif) | CYD board support | LGPL-2.1 / Apache-2.0 components |
| Leaflet 1.9.4 | Mesh Radar map (loaded from unpkg.com) | BSD-2-Clause |
| OpenStreetMap tiles | Mesh Radar map | data © OpenStreetMap contributors, ODbL; OSM tile usage policy applies |

## Trademarks

Meshtastic® is a registered trademark of Meshtastic LLC. Meshtastic software components are released
under various licenses; see their repositories. Radio Gremlin is an independent project and is not
affiliated with or endorsed by Meshtastic LLC, LilyGO or the Meshing Around project. Product names
are used only to describe compatibility.

## No warranty

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even
the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
License for more details. Use at your own risk; you are responsible for operating your radio within
your local regulations.

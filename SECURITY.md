# Security and privacy

Radio Gremlin V0.1 is an **experimental, single-user hobby project**. It is designed for a computer
on a home network you control. It has had no security review. Read this before exposing anything to
a network.

## The Mesh Command API has no authentication

The Mesh Command API (`gremlin/mesh_command.py`) runs inside the bot and serves:

| Endpoint | Contents |
|---|---|
| `/status` | packet counters, last RSSI/SNR, last sender's short name, uptime |
| `/nodes` | every node your radio knows: ID, short and long name, hardware, role, last heard, signal, battery |
| `/traffic` | the last 100 packets: sender, type, route and signal, **including the text of broadcast (channel) messages**. Direct messages are shown only as "[Private message]". |
| `/mapnodes` | node positions. **Only served to the computer itself**, even in LAN mode. |

The API is **read-only**. It has no endpoint that transmits on the mesh or changes anything.

**By default it listens on `127.0.0.1`**, which means only programs on the same computer can read
it.

**LAN mode** (`[api] bind = <your LAN address>` in `gremlin.ini`) is needed for the Mesh Command
CYD. In LAN mode, **any device on that network can read `/status`, `/nodes` and `/traffic` without a
password, token or encryption** (plain HTTP). Only enable it on a network you trust, never on public
or shared Wi-Fi, and never port-forward it to the internet. On macOS, the firewall may ask whether
Python may accept incoming connections. Allow it only if you want LAN mode.

## Mesh Observatory

- Listens on `127.0.0.1:8766` by default and has no authentication either. Keep it on localhost.
- Stores a history of other people's node IDs, names, signal reports, message metadata and
  **reported GPS positions** in `observatory.db`. Treat that file as private. It is git-ignored;
  never publish it.
- The map loads Leaflet from unpkg.com and map tiles from tile.openstreetmap.org, so opening the
  dashboard makes requests to those services.

## Secrets

- Wi-Fi credentials for the CYD go in `firmware/MeshCommand_CYD/secrets.h`, which is git-ignored.
  Only `secrets.example.h` (placeholders) is in the repository.
- Your Meshing Around `config.ini` and your `gremlin.ini` are git-ignored. They contain your radio's
  address and bot settings.
- Screenshots in `docs/images` were sanitized: other users' node IDs are hidden, and the map is
  zoomed out with the operator's station marker removed.

## Reporting a problem

Please open an issue for security problems that don't put anyone at risk. For anything sensitive,
contact the author through https://badaudioguy.com first.

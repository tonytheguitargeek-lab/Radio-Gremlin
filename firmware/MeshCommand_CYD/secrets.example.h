// Copy this file to secrets.h (same folder) and edit it. secrets.h is git-ignored: never commit it.
#pragma once

// Your 2.4 GHz Wi-Fi network (the ESP32 does not support 5 GHz)
#define WIFI_SSID     "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"

// Mesh Command API on the computer running Radio Gremlin, including the port.
// The API must be bound to a LAN address for the CYD to reach it (see README: "LAN access for the CYD").
#define MESH_COMMAND_URL "http://192.0.2.20:8765"

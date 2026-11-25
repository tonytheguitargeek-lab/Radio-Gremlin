# Mesh Command: CYD touchscreen firmware

Mesh Command turns an ESP32 "Cheap Yellow Display" into a small desk monitor for Radio Gremlin. It
polls the Mesh Command API over Wi-Fi and shows:

- **Monitor:** node count, direct and relayed packets, last RF RSSI and SNR with bar graphs, and the
  last RF sender
- **Directory:** nodes with RSSI, hops and age. Tap a node for its details.
- **Traffic:** a live packet list with ALL, TEXT and RF filters. Private messages show only as
  "[Private message]".
- **System:** Wi-Fi status, the CYD's IP, API uptime and packet totals, plus touch recalibration

It only reads from the API (HTTP GET). It never transmits on the mesh.

## Hardware

- **ESP32-2432S028R**, the common 2.8" 320×240 "Cheap Yellow Display" with an ILI9341 display and
  an XPT2046 resistive touch controller.
- A USB cable for flashing and power.

Some boards sold as "CYD" use a different display controller (for example ST7789), or are wired with
a different color order or inversion. The settings below are for the ILI9341 version Radio Gremlin was
built on. If your screen stays white, looks mirrored, or shows wrong colors, your board is probably
a different variant.

## Libraries (Arduino Library Manager)

| Library | Tested version | License |
|---|---|---|
| TFT_eSPI (Bodmer) | 2.5.43 | MIT / BSD (Adafruit GFX portions) |
| XPT2046_Touchscreen (Paul Stoffregen) | 1.4 | MIT-style |
| ArduinoJson (Benoît Blanchon) | 7.4.3 (v7 required) | MIT |
| ESP32 Arduino core (Espressif), board package | 3.3.12 | LGPL-2.1 / Apache-2.0 components |

`WiFi`, `HTTPClient`, `SPI` and `Preferences` come with the ESP32 board package.

## TFT_eSPI configuration for the CYD (required)

TFT_eSPI is configured by editing **its own** `User_Setup.h`, in the library folder
(`Documents/Arduino/libraries/TFT_eSPI/User_Setup.h`), not in this sketch. Replace that file's
contents with the following settings. These are the exact settings Mesh Command was tested with.

```cpp
#define USER_SETUP_INFO "CYD ESP32-2432S028"

#define ILI9341_2_DRIVER          // ILI9341 variant used on the ESP32-2432S028R

#define TFT_WIDTH  240
#define TFT_HEIGHT 320

#define TFT_MISO 12
#define TFT_MOSI 13
#define TFT_SCLK 14
#define TFT_CS   15
#define TFT_DC    2
#define TFT_RST  -1               // display reset is tied to the board's reset

#define TFT_BL 21                 // backlight
#define TFT_BACKLIGHT_ON HIGH

#define LOAD_GLCD
#define LOAD_FONT2
#define LOAD_FONT4
#define LOAD_FONT6
#define LOAD_FONT7
#define LOAD_FONT8
#define LOAD_GFXFF
#define SMOOTH_FONT

#define SPI_FREQUENCY      27000000
#define SPI_READ_FREQUENCY 20000000
```

Also make sure `User_Setup_Select.h` (same folder) includes `User_Setup.h`, which is the default,
and that no other `#include <User_Setups/...>` line is active.

Notes:

- Updating TFT_eSPI overwrites `User_Setup.h`. Keep a copy of these settings.
- The touch controller has its own SPI bus, set up in the sketch: SCK 25, MISO 39, MOSI 32, CS 33,
  IRQ 36. No library configuration is needed for it.
- The sketch calls `tft.invertDisplay(true)` and `setRotation(1)` (landscape). If your colors look
  inverted, your board needs `invertDisplay(false)`.

## Build and flash

1. Install the **ESP32 board package** by Espressif (Boards Manager, "esp32") and the three
   libraries above.
2. Configure TFT_eSPI as described above.
3. In this folder, copy `secrets.example.h` to **`secrets.h`** and edit it:

   ```cpp
   #define WIFI_SSID        "your-wifi-name"       // 2.4 GHz network
   #define WIFI_PASSWORD    "your-wifi-password"
   #define MESH_COMMAND_URL "http://192.0.2.20:8765"  // the Radio Gremlin computer's LAN address
   ```

   `secrets.h` is listed in `.gitignore`. **Never commit it or share it.**
4. Open `MeshCommand_CYD.ino`, select the board **ESP32 Dev Module**, choose the port and upload.
5. On first boot the CYD asks you to touch four targets to calibrate touch. Calibration is stored
   on the device. You can redo it from the System page ("CALIBRATE TOUCH").

## The CYD needs LAN access to the API

By default the Mesh Command API listens only on `127.0.0.1`, so the CYD **cannot** reach it. To use
Mesh Command, set `[api] bind` in `meshing-around/gremlin.ini` to the Radio Gremlin computer's LAN
address, restart Radio Gremlin, and put that address in `MESH_COMMAND_URL`. Read the warning in the
main README first: **the LAN API has no authentication.**

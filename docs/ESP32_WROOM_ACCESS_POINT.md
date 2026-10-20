# Freenove ESP32-WROOM access point

The Freenove ESP32-WROOM is used as a local, project-controlled Wi-Fi access point and UDP echo host. This avoids managed Wi-Fi policies and makes range results easier to reproduce.

## PlatformIO target

```ini
[env:freenove_esp32_wroom_ap]
platform = espressif32
board = esp32dev
framework = arduino
```

`esp32dev` targets the classic ESP32-WROOM module used by this board.

## Local configuration

Edit `include/esp32_hotspot_secrets.h`:

```cpp
#define ESP_AP_SSID "PICO_RANGE_LAB"
#define ESP_AP_PASSWORD "use-a-unique-password"
#define ESP_AP_CHANNEL 6
#define ESP_ECHO_PORT 3333
```

Use the exact SSID/password in the Pico `include/secrets.h`, and configure its echo destination as:

```cpp
#define ECHO_SERVER_IP 192, 168, 4, 1
#define ECHO_SERVER_PORT 3333
```

These files are local and Git-ignored.

## Expected serial events

At startup:

```json
{"event":"ap_state","status":"ready","ip":"192.168.4.1","channel":6}
```

Once the Pico joins, periodic `echo_stats` events show a nonzero station count and increasing packet count. The ESP serial monitor is optional during collection; Pico telemetry is the canonical source for trial metrics.

## Upload

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -e freenove_esp32_wroom_ap -t upload
```

If auto-upload fails, confirm the device COM port in Device Manager. Some ESP32 boards require holding **BOOT** only while starting an upload.

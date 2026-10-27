# Wireless Range Lab

Wireless Range Lab is a reproducible test bench for comparing Wi-Fi and, later, BLE links across a Raspberry Pi Pico 2 W, ESP32 boards, and a host computer. It combines PlatformIO firmware with a PyQt desktop application that records test setup, stores raw telemetry, and displays derived results.

The current working configuration is a self-contained Wi-Fi range test:

```text
Pico 2 W (station and packet-test agent)
        <---- 2.4 GHz Wi-Fi ---->
Freenove ESP32-WROOM (WPA2 access point and UDP echo host)
        |
USB serial NDJSON -> laptop collector -> saved trial data -> PyQt summary view
```

No school or public Wi-Fi network is required.

![Current test topology: the laptop collects serial telemetry, the ESP32-WROOM hosts the private Wi-Fi network and UDP echo service, and the Raspberry Pi Pico 2 W acts as the Wi-Fi test client.](media/Wireless%20Range%20Lab.png)

## Planned topology experiments

The current firmware exercises one private ESP32 hotspot. A later experiment will compare its coverage with deliberately placed, overlapping hotspots while retaining the same test area and measurement workflow. This is a test concept only; multi-hotspot orchestration and roaming measurement are not implemented yet.

![Conceptual comparison of one hotspot's coverage with overlapping coverage areas from multiple hotspots in the same test area.](media/Wireless%20Range%20Lab%20%281%29.png)

## Documentation

- [Experiment workflow](docs/EXPERIMENT_WORKFLOW.md): configure, flash, collect, and compare trials.
- [Experiment 1.0 write-up](docs/EXPERIMENT_1_0_WRITEUP.md): what was built, what happened during setup, and the recorded Wi-Fi results.
- [Architecture and metrics](docs/ARCHITECTURE.md): components, data contracts, calculations, and limitations.
- [Wireless Range Lab application](docs/WIRELESS_RANGE_LAB.md): desktop UI, files, and commands.
- [ESP32-WROOM access point](docs/ESP32_WROOM_ACCESS_POINT.md): hardware-specific setup and troubleshooting.

## Prerequisites

- VS Code with the PlatformIO extension.
- Python 3.11+ and the project virtual environment.
- A data-capable USB cable for each board.
- Raspberry Pi Pico 2 W and Freenove ESP32-WROOM.

Install the desktop application dependencies once:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\wireless_range_lab\requirements.txt
```

## PlatformIO environments

| Environment | Board | Role |
| --- | --- | --- |
| `pico2_w` | Raspberry Pi Pico 2 W (RP2350) | Wi-Fi station, UDP test client, serial telemetry source |
| `freenove_esp32_wroom_ap` | Freenove ESP32-WROOM | Private WPA2 AP and UDP echo host |

The project currently pins `upload_port` to `COM11` for the Pico and `COM12` for the ESP32. Update those values in [platformio.ini](platformio.ini) if Windows assigns different ports.

## Quick start: private ESP32 Wi-Fi test

1. Configure local credentials. These files are intentionally ignored by Git:

   - `include/esp32_hotspot_secrets.h`: ESP32 AP SSID, WPA2 password, and channel.
   - `include/secrets.h`: Pico station SSID/password, plus `ECHO_SERVER_IP` set to `192, 168, 4, 1` and port `3333`.

   The Pico and ESP32 SSID/password must match. Never commit or share these files.

2. Flash the ESP32 AP first:

   ```powershell
   & "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -e freenove_esp32_wroom_ap -t upload
   ```

   Its serial output should show `ap_state` with status `ready` and IP `192.168.4.1`.

3. Flash the Pico. For BOOTSEL upload, hold **BOOTSEL** while connecting USB, then release it:

   ```powershell
   & "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -e pico2_w -t upload
   ```

4. Start the desktop app and save a trial setup:

   ```powershell
   cd .\wireless_range_lab
   ..\.venv\Scripts\python.exe app.py
   ```

   Use **Copy trial ID** after saving.

   The app records the board identities, link configuration, geometry, environment, and notes needed to reproduce a trial. After collection, its saved-summary panel shows that metadata together with the calculated link metrics.

   ![Wireless Range Lab desktop application showing endpoint, link, environment, and saved-summary controls.](media/Screenshot%202026-10-20%20202408.png)

5. Start collection on the Pico COM port. Do not keep a serial monitor open on the same port:

   ```powershell
   ..\.venv\Scripts\python.exe tools\collect_serial.py --port COM11 --trial-id <trial-id>
   ```

6. Let the test run for the planned duration, then press `Ctrl+C`. The collector saves the raw events and summary automatically. Return to the app and select **Refresh summaries**.

## Verification

Run the Python tests from the application directory:

```powershell
cd .\wireless_range_lab
..\.venv\Scripts\python.exe -m pytest
```

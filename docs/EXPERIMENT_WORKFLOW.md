# Experiment workflow

## Before each test session

1. Use the private ESP32 access point, not the school or public Wi-Fi network.
2. Ensure the Pico and ESP32 credentials match in the two ignored local secrets files.
3. Flash the ESP32 AP and verify `ap_state: ready`.
4. Flash the Pico and verify `wifi_state: connected` plus `packet_result: echoed` in a serial monitor.
5. Close the serial monitor before launching the collector; one process can open a COM port at a time.

## Run one trial

1. Fix the ESP32 in one location and set its orientation. Keep it unchanged throughout the comparison.
2. Place the Pico at a measured distance and orientation.
3. In the desktop application, record endpoints, antenna setup, communication mode, environment, line-of-sight, obstacles, channel/PHY, transmit power, and notes.
4. Save the setup, then use **Copy trial ID**.
5. Start the collector using the Pico serial port and trial ID.
6. Replug/reset the Pico if needed so the collector records connection events.
7. Run for a fixed duration. Start with 60 seconds; use the same duration for comparable trials.
8. Stop with `Ctrl+C`. The collector writes raw events and a summary.
9. In the desktop app, choose **Refresh summaries** and inspect the stored metrics.

## Suggested baseline sequence

Run each condition separately, creating a new trial for every material change:

1. 1 m, line of sight, fixed orientation.
2. 5 m, same setup.
3. 10 m, same setup.
4. Continue until delivery ratio, RSSI, or latency degrades.
5. Repeat selected distances with a wall, body blockage, antenna rotation, or different AP channel.

Do not move both boards at once. Record the actual distance, not an estimate.

## Interpretation checklist

- Compare packet delivery ratio before interpreting an RTT average.
- Compare p95 RTT and max RTT, not just median RTT.
- Treat a single high maximum as an outlier until it repeats across trials.
- Compare RSSI trends across controlled distances; absolute RSSI varies by device and orientation.
- Preserve the raw NDJSON file whenever reporting a result.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Pico reports `configured_ssid_not_seen` | ESP32 AP is powered/flashed; Pico secrets match; keep boards close for first test. |
| Pico reports `connect_timeout` | SSID/password mismatch, ESP AP did not reach `ready`, or the board is not using the latest firmware. |
| Pico has no COM port | Reconnect with a data cable; use BOOTSEL only for upload; check Device Manager for `USB Serial Device`. |
| ESP32 upload fails | Verify its current COM port; hold **BOOT** during upload only if the board requests it. |
| No collector output | Confirm Pico COM port, 115200 baud, and that a serial monitor is closed. |
| Collector has events but no UI summary | Stop collector with `Ctrl+C`, then select **Refresh summaries** in the app. |

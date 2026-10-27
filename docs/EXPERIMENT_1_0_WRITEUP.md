# Wi-Fi Range-Test Write-up

## Purpose

This project established a repeatable way to characterize short-range wireless communication before applying the hardware to larger robotics and mechatronics work. The immediate question was whether a Raspberry Pi Pico 2 W could reliably exchange application data with an ESP32-WROOM over Wi-Fi, while preserving enough context to compare trials later.

This document records what was built, what went wrong during setup, what ultimately worked, and what the saved data does—and does not—show.

## System that was built

The working test bench uses a private Wi-Fi network instead of the managed school network:

```text
Raspberry Pi Pico 2 W              Freenove ESP32-WROOM
Wi-Fi station and test client  <-> WPA2 access point and UDP echo host
           |
           +-- USB serial NDJSON --> laptop collector --> trial files and PyQt viewer
```

The Pico firmware sends a 128-byte UDP packet every 200 ms. Each packet contains a magic value, a sequence number, and the Pico's monotonic send timestamp. The ESP32 returns the exact datagram. When the Pico receives the echo—or reaches its timeout—it emits a terminal JSON event on USB serial. The laptop collector writes those events unchanged to an NDJSON file, then derives a summary when stopped with `Ctrl+C`.

The PyQt application records the experimental context before collection: boards and firmware versions, antenna type, radio technology, communication mode, distance, environment, visibility, obstacles, and notes. The summary JSON stores a snapshot of that metadata next to the calculated metrics, so one trial can be understood from one file.

![Current laptop, ESP32, and Pico test topology.](../media/Wireless%20Range%20Lab.png)

## Setup and troubleshooting chronology

1. **PlatformIO and desktop tooling were prepared.** The repository was set up with PlatformIO environments for the Pico 2 W and the Freenove ESP32-WROOM, plus a Python virtual environment and a PyQt desktop application.
2. **The first Pico Wi-Fi attempt used a Windows mobile hotspot.** The Pico reported `connect_timeout` and then `configured_ssid_not_seen` in its scan telemetry. That means the configured network name was not visible to the Pico; it was not merely a password failure.
3. **The managed-network and hotspot route was abandoned for the test bench.** Windows reported that the hotspot was being shared in the 5 GHz band. The Pico 2 W's Wi-Fi is 2.4 GHz, so a 5 GHz-only hotspot cannot be used by it. Even after checking the hotspot configuration, the observed scans did not show the configured SSID.
4. **USB serial availability was also resolved.** At one point the Pico's COM port disappeared because the computer USB ports were not functioning. Restarting the computer restored the connection, and the Pico appeared as `USB Serial Device (COM11)`. The ESP32 appeared as `USB-SERIAL CH340 (COM12)`.
5. **The ESP32-WROOM was changed into the network host.** It was flashed with firmware that creates a private WPA2 access point on `192.168.4.1` and echoes UDP datagrams on port `3333`. The Pico credentials were updated to match that AP. This removed the dependency on school Wi-Fi and on Windows hotspot behavior.
6. **End-to-end communication was verified.** With the ESP32 acting as AP/echo host and the Pico acting as station/client, the Pico emitted successful `packet_result` events. The collector then captured those serial events under a trial ID and produced a summary automatically.

The early diagnostic trial, `trial-20261020-004547-7106c5`, has a metadata file and raw events but no usable measurement summary because the Pico never joined the Windows hotspot. Four later metadata-only IDs were created without collected telemetry; they are setup records, not completed measurements.

## How a completed trial works

1. Flash and power the ESP32 first; it publishes the private 2.4 GHz WPA2 network.
2. Flash/reset the Pico; it joins that network and begins the periodic UDP echo test.
3. Save the test setup in the desktop app and copy its generated trial ID.
4. Run the serial collector against the Pico COM port using that ID. A serial monitor must be closed first because only one process can use the port.
5. Keep the board positions and environmental condition fixed for the planned duration.
6. Stop the collector with `Ctrl+C`. It creates the raw `*.events.ndjson` file and the self-contained `*.summary.json` file.
7. Refresh the summary selector in the app to review the saved metadata and results.

The raw event file is the authoritative record. A summary can be regenerated if the metric calculations change; raw telemetry should not be edited.

## Baseline result

The first successful baseline was conducted indoors at 0.5 m with a clear line of sight:

| Item | Recorded value |
| --- | --- |
| Trial ID | `trial-20261020-021221-64968f` |
| Endpoints | Raspberry Pi Pico 2 W (`v0.0.2`) and Freenove ESP32-WROOM (`v0.0.1`) |
| Communication mode | ESP32 Wi-Fi hotspot / UDP echo |
| Environment | Indoor office |
| Attempts / echoed | 503 / 503 |
| Packet delivery ratio | 100% |
| Test duration | 106.4 s |
| Goodput | 605.2 bytes/s |
| RTT (min / median / p95 / max) | 4.480 / 6.570 / 13.484 / 30.700 ms |
| RSSI (min / median / max) | -51 / -38 / -29 dBm |

This establishes that the complete firmware-to-collector-to-summary pipeline works under a favorable, nearby condition. The reported goodput is intentionally low because the test sends one 128-byte payload every 200 ms; it is a reliability baseline, not a maximum Wi-Fi throughput test.

## Indoor distance campaign

![Photographic record of the indoor Wi-Fi test bench at nominal 0.5 m, 1.0 m, 1.5 m, and 2.4 m endpoint separations. The ESP32 access point is fixed at the left side of the bench and the Raspberry Pi Pico 2 W is moved along the measured tape line.](../media/Wireless%20lab%20experiments.jpg)

After the baseline, 29 additional completed summaries were saved. The campaign used the same high-level ESP32-hotspot topology, integrated antennas, and an indoor-office environment. Recorded endpoint separation ranged from **0.33 m to 2.44 m**. Most of these later trials are marked as not having clear line of sight; exact conditions for each run are preserved in its corresponding summary JSON.

| Aggregate over 30 completed summaries | Result |
| --- | --- |
| Total active collection time | 3,477.7 s (about 58.0 min) |
| Total terminal attempts | 14,491 |
| Successful echoes | 14,212 |
| Combined end-to-end delivery ratio | 98.07% |
| Per-trial delivery-ratio range | 0% to 100% |
| Median RTT range across successful trials | 6.570 to 9.488 ms |

The data shows many high-delivery runs in this short indoor range, but it should not yet be treated as a formal range limit. The campaign includes varying test durations, changing distance, and mostly non-line-of-sight conditions. In addition, channel, transmit power, board orientation, and obstacle descriptions were not consistently populated in the metadata.

One run—`trial-20261021-003201-20d30a` at a recorded 2.0 m—had 106 attempts and zero echoes. The telemetry establishes an end-to-end failure for that run, but it cannot identify the cause by itself. Possible causes include temporary Wi-Fi disconnection, reset/reconfiguration, a changed obstruction/orientation, or loss in either direction of the echoed path. It must be repeated under controlled conditions before being interpreted as a distance threshold.

## Meaning of the measurements

- **Packet delivery ratio (PDR)** is echoed packets divided by attempted packets. It measures successful application-level round trips, not only one radio direction.
- **RTT** is the Pico's time from sending a packet until receiving its echo. It includes Wi-Fi contention, queueing, ESP32 handling, and the return trip; it is not one-way latency.
- **RSSI** is measured by the Pico and is useful for trends, but it depends on orientation, placement, bodies, walls, and the surrounding RF environment.
- **Goodput** is delivered payload bytes divided by active duration. It does not represent PHY data rate or the maximum possible throughput of either board.
- **Timeouts** establish that no acceptable echo arrived before the configured deadline, but they cannot say whether the forward or return leg failed.

## Data location and reproducibility

Each completed trial is stored under `wireless_range_lab/data/trials/`:

| File suffix | Contents |
| --- | --- |
| `.json` | Canonical trial metadata entered in the UI. |
| `.events.ndjson` | One raw serial telemetry event per line. |
| `.summary.json` | Metadata snapshot plus derived metrics for convenient review and reporting. |

For a defensible comparison, future trials should use a fixed duration (for example, 60 or 120 seconds), one deliberately changed variable at a time, measured board separation, fixed board orientation, AP channel, transmit-power setting, line-of-sight state, and a clear obstacle description. Repeating each condition three or more times will allow comparison of variation rather than relying on a single run.

## Next experiments

1. Repeat the 0.5 m, 1.0 m, 1.5 m, 2.0 m, and 2.5 m conditions with fixed duration and complete metadata.
2. Run dedicated line-of-sight and obstructed-path series, keeping orientation and AP location fixed.
3. Repeat the 2.0 m zero-delivery condition to determine whether it is reproducible.
4. Sweep one AP channel at a time and log the channel in every trial.
5. Add a higher-rate/payload-size experiment only after preserving the present low-rate reliability baseline.
6. Add BLE as a separate transport adapter with the same metadata and raw-event contract, then compare it fairly against Wi-Fi.
7. Explore multi-hotspot and roaming experiments only after defining association, handoff, and coverage metrics.

![Future concept: a controlled comparison between one hotspot and multiple overlapping hotspots. Multi-hotspot support is not implemented in the current firmware.](../media/Wireless%20Range%20Lab%20%281%29.png)

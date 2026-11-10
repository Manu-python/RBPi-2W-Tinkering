# Wireless Range Lab V2: UDP telemetry and diagnostics

V2 keeps the original architecture—Pico 2 W sends UDP to the ESP32-WROOM access point, which echoes it unchanged—but instruments both ends. It is a measurement system, not a reliable transport, robot-control protocol, or failsafe.

```mermaid
sequenceDiagram
    participant P as Pico 2 W
    participant E as ESP32-WROOM
    participant H as Dual serial collector
    P->>H: packet_tx(sequence, local API outcome)
    P->>E: UDP V2 datagram
    E->>H: packet_rx(validation) before echo
    E->>H: echo_attempt / echo_result(local API outcome)
    E->>P: unchanged UDP datagram
    P->>H: packet_rx(on-time, late, duplicate, unexpected, or invalid)
    Note over P: Deadline passes; retain pending sequence during grace window
    P->>H: packet_deadline then packet_finalized(unobserved), if no valid echo arrives
    H->>H: correlate by trial ID + session ID + sequence
```

## V2 packet contract

The default remains a fixed **128-byte UDP datagram**, including a 28-byte header and a deterministic 100-byte payload. All multibyte fields are big-endian.

| Offset | Bytes | Field |
| --- | --- | --- |
| 0 | 4 | Magic `RLB2` (`0x524C4232`) |
| 4 | 1 | Protocol version (`2`) |
| 5 | 1 | Header size (`28`) |
| 6 | 2 | Reserved flags (`0`) |
| 8 | 4 | FNV-1a 32-bit hash of the full trial ID (correlation key, not a secret) |
| 12 | 4 | Sequence number |
| 16 | 4 | Pico monotonic send timestamp, microseconds |
| 20 | 2 | Total UDP datagram bytes |
| 22 | 2 | Payload bytes |
| 24 | 4 | IEEE CRC-32 of the whole datagram with these four bytes zeroed |
| 28 | remainder | Deterministic payload: `(session_id + sequence + byte_offset) & 0xff` |

Wi-Fi and UDP already detect corrupted frames. The CRC is additional experiment instrumentation: a bad CRC is an observed application-level validation failure, not proof that normally corrupted RF frames reach UDP.

## Event meaning

Both boards emit newline-delimited JSON at 115200 baud. The collector adds `collector_source` (`pico` or `esp32`) and `collector_received_at` without replacing device timestamps.

- Pico `packet_tx`: local `beginPacket`, write, and `endPacket` outcomes. A `sent` status means its local API accepted the datagram, not that ESP32 received it.
- ESP32 `packet_rx`: emitted **before** echoing; `received` with `validation: valid` is an ESP32 telemetry observation.
- ESP32 `echo_result`: `api_success` means only local `endPacket()` success. It is not evidence that Pico received the echo.
- Pico `packet_rx`: `echo_on_time`, `echo_late`, `duplicate`, `unexpected`, or `invalid`.
- Pico `packet_deadline`: the configured deadline passed, but the sequence stays pending during the grace window.
- Pico `packet_finalized` / `unobserved`: no valid matching echo arrived before deadline plus grace; this is the final V2 no-echo observation.
- `wifi_state` events are separate from packet events and expose connect/reconnect state.

Device clocks are not synchronized. RTT is measured only by Pico's monotonic clock. Host ingestion timestamps help visualize order but must not be used as precise radio timing.

## Automatic trial and condition IDs

The desktop app now generates V2 IDs from saved metadata. Its format is:

```text
YYYYMMDD_D###cm_R±###_A##_T####
20261029_D150cm_R-090_A02_T1000
```

- `YYYYMMDD`: local experiment date.
- `D###cm`: endpoint separation in whole centimeters. The UI records up to 0.01 m, which maps exactly to centimeters.
- `R±###`: net rotation in degrees.
- `A##`: the next unused attempt for that equivalent condition.
- `T####`: configured echo timeout in milliseconds.

The separate condition ID omits only the attempt: `20261029_D150cm_R-090_T1000`. It groups repeats at the same date, distance, rotation, and timeout. Board identity, orientation details, channel, obstacles, payload, interval, notes, and every other factor remain structured metadata; do not infer them from the ID.

The repository checks existing files before saving setup or opening a V2 collector. It assigns the lowest unused attempt from `A01` to `A99` and refuses collisions rather than overwriting data. Older V1/V2 IDs such as `trial-20261020-…` remain readable but cannot start a new automatic V2 collection.

## Configure and flash a V2 run

Copy the two ignored secret templates if needed. In local `include/secrets.h`, set the AP credentials and destination as before, then set these V2 values before flashing the Pico:

```cpp
#define FIRMWARE_REVISION "v2-20261029"
#define TEST_PACKET_BYTES 128
#define TEST_INTERVAL_MS 200
#define ECHO_TIMEOUT_MS 1000       // compare with a separate 3000 ms run
#define LATE_REPLY_GRACE_MS 1000
#define TARGET_PACKET_COUNT 300    // or 0 for no count limit
#define TEST_DURATION_MS 0         // or a positive duration; either limit can stop sending
```

`TRIAL_ID` is no longer a per-trial firmware setting. Flash this V2 firmware once. When collection begins, the host sends `RLAB_SESSION <automatic-trial-id>` over the Pico USB serial connection; the Pico resets its sequence counter and derives the packet session hash. The ESP32 does not need a command or reflash because it reads that hash from every UDP datagram. This command is local serial setup, not a new wireless transport.

Timeout, packet size, interval, count/duration, and grace period remain firmware configuration in this small design, so reflash the Pico when changing them. For a fair 1,000 ms vs. 3,000 ms comparison, save a new app setup for each timeout, retain the same interval, packet size, physical layout, AP channel, duration/count, and grace policy, and record all values in metadata.

Flash the ESP32, then the Pico:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -e freenove_esp32_wroom_ap -t upload
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -e pico2_w -t upload
```

The expected Windows ports in the present project are ESP32 `COM12` (CH340) and Pico `COM11`; check Device Manager and update `platformio.ini` or commands if Windows assigns different values.

## Collect, summarize, report, and plot

Save trial metadata in the desktop UI first. Set the rotation and echo timeout fields; the app shows and copies the generated ID. Close any serial monitor on both ports, then run from `wireless_range_lab`:

```powershell
..\.venv\Scripts\python.exe tools\collect_dual_serial.py `
  --trial-id 20261029_D150cm_R-090_A02_T1000 --pico-port COM11 --esp32-port COM12 `
  --label "1 m line of sight, 1000 ms timeout" `
  --expected-packet-interval-ms 200 --expected-echo-timeout-ms 1000 `
  --expected-packet-bytes 128 --grace-period-ms 1000
```

Press `Ctrl+C` once after the intended collection window. Every newly created V2 attempt has its own folder, `wireless_range_lab/data/trials/<trial-id>/`, without touching V1 files:

| File | Purpose |
| --- | --- |
| `metadata.json` | Saved experimental setup and automatic trial/condition identifiers. |
| `events.ndjson` | Combined raw Pico, ESP32, and collector-state events. |
| `malformed.ndjson` | Raw malformed serial lines with source and host timestamp. |
| `config.json` | Requested collection settings and observed Pico firmware configuration. |
| `summary.json` | Self-contained V2 metrics, configuration, and metadata snapshot. |
| `report.md`, `timeline.png`, `live_timeline.png` | Regenerable human report and saved visualizations. |

Create a readable report and optional plot:

```powershell
..\.venv\Scripts\python.exe tools\report_v2_trial.py --trial-id 20261029_D150cm_R-090_A02_T1000
..\.venv\Scripts\python.exe tools\plot_v2_trial.py --trial-id 20261029_D150cm_R-090_A02_T1000
```

The static plot contains RTT by sequence, RSSI by sequence, and valid-echo/deadline events. Install the updated requirements once for plotting: `..\.venv\Scripts\python.exe -m pip install -r requirements.txt`.

## Reading V2 metrics responsibly

The V2 summary reports explicit denominators. For example, `packets_received_observed_by_esp32 / packets_transmitted_observed_by_pico` is an **ESP32 telemetry observation ratio**, not a guaranteed one-way radio delivery ratio. If the ESP32 serial stream was unavailable or has a collection error, that ratio is `null` and `metrics_reliability` is `incomplete_telemetry`.

Likewise, a final `unobserved` packet is an application-level no-matching-echo observation after the deadline and grace period. It cannot locate failure to Pico transmit, ESP32 receive, ESP32 echo, or Pico receive without the corresponding device telemetry. Late echoes are successful returns after the deadline and are not counted as irrecoverably lost.

RTT jitter is the mean absolute difference between adjacent valid RTT samples ordered by sequence. Goodput is valid echoed application payload bytes divided by Pico active duration; it is not Wi-Fi PHY throughput.

## V1 comparability and limitations

V1 files (`.events.ndjson` and `.summary.json`) are preserved and still parsed by the original V1 tools. V1 used a blocking one-packet wait, a 12-byte header, and a default 1,000 ms timeout; its `echoed / attempts` measure should not be mixed directly with V2's on-time, late, and finalized counts.

V2 changes scheduling, header size, serial logging volume, and late-reply accounting. Extra serial output can affect timing, especially at short packet intervals. Report the firmware revision, interval, datagram size, timeout, grace period, AP channel, orientation, distance, obstacles, and duration/count whenever comparing results. Hardware has not yet been verified with this V2 firmware.

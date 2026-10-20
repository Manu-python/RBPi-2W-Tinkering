# Architecture and metrics

## Separation of responsibilities

```text
Pico firmware -> USB serial NDJSON -> collector -> immutable raw events
ESP32 firmware -> UDP echo host              -> summary JSON -> desktop UI
desktop UI -> trial metadata JSON / CSV index
```

- **Pico firmware** (`src/main.cpp`) joins the configured AP, sends a sequenced UDP packet, waits for an echo, and reports a terminal result per sequence.
- **ESP32 firmware** (`src/esp32_ap.cpp`) starts a private WPA2 access point and transparently echoes UDP datagrams.
- **Collector** (`wireless_range_lab/tools/collect_serial.py`) timestamps Pico serial events, attaches a trial ID, appends NDJSON, and saves a derived summary on a clean stop.
- **Domain logic** (`range_lab/telemetry.py`) calculates metrics from raw event data without depending on PyQt or serial hardware.
- **Repository** (`range_lab/storage.py`) atomically persists metadata and summaries.
- **PyQt UI** records configuration, copies trial IDs, and loads saved summaries. It does not parse serial data or own radio protocol logic.

## Data files

For trial ID `trial-...`:

| File | Purpose |
| --- | --- |
| `data/trials/trial-....json` | Canonical metadata: hardware, environment, layout, antenna, protocol settings, and notes. |
| `data/trials/trial-....events.ndjson` | Canonical raw telemetry; one JSON event per line. |
| `data/trials/trial-....summary.json` | A self-contained report: a snapshot of trial metadata plus regenerable derived metrics, saved when collection ends. |
| `data/trial_index.csv` | Flat cross-trial metadata index for spreadsheets and plotting. |

Raw events are authoritative. Delete or regenerate summaries when calculation logic changes; do not alter raw telemetry.

## Current protocol

Each Pico packet contains a magic value, sequence number, and Pico monotonic send timestamp. The ESP32 echoes the datagram unchanged. The Pico emits one `packet_result` event for each sequence:

```json
{
  "schema_version": 1,
  "event": "packet_result",
  "device_id": "pico2w-01",
  "status": "echoed",
  "sequence": 417,
  "payload_bytes": 128,
  "sent_monotonic_us": 918273645,
  "observed_monotonic_us": 918281902,
  "rtt_us": 8257,
  "rssi_dbm": -68
}
```

Possible terminal statuses are `echoed`, `timeout`, and `send_error`.

## Metric definitions

| Metric | Definition |
| --- | --- |
| Attempts | Unique sequence numbers with a terminal result. |
| Echoed | Unique sequences with status `echoed`. |
| Packet delivery ratio | `echoed / attempts`. It is end-to-end echo success. |
| Timeouts | Attempts without a valid echo before the configured timeout. |
| Goodput | Unique echoed payload bytes divided by active test duration. It is not PHY rate. |
| RTT | Pico send-to-echo-receive time. Summary reports min, median, p95, and max. |
| RSSI | Pico-reported received signal strength. Summary reports min, median, and max. |
| Duplicates | Repeated terminal events with an already-seen sequence number. |

## Measurement limitations

- An echo timeout cannot identify whether loss occurred on the Pico-to-ESP forward path or ESP-to-Pico return path.
- RTT includes queueing and processing on both boards; it is not one-way latency.
- One-way latency requires synchronized clocks and a documented synchronization error budget.
- Current goodput is limited by the configured 128-byte payload and 200 ms interval; it is intentionally a reliability baseline, not a saturation-throughput benchmark.
- RSSI is one board's observation and varies with orientation, body blockage, antenna placement, and the radio environment.

## Next extensions

1. Add explicit trial start/stop control from the UI instead of a CLI collector.
2. Record packet interval, payload size, AP channel, firmware build ID, and reconnection events in trial metadata/events.
3. Add directional two-board accounting to separate forward and return loss.
4. Add BLE GATT transport as an adapter using the same raw-event contract.
5. Add plots, confidence intervals, and exported reports.

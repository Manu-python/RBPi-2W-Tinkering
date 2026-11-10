#pragma once

// Copy this file to secrets.h. Do not commit secrets.h.
#define WIFI_SSID "YOUR_2_4_GHZ_HOTSPOT_NAME"
#define WIFI_PASSWORD "YOUR_HOTSPOT_PASSWORD"
#define ECHO_SERVER_IP 192, 168, 4, 1
#define ECHO_SERVER_PORT 3333
#define LOCAL_UDP_PORT 3334
#define DEVICE_ID "pico2w-01"
// Kept only as a fallback for older host tools. Collection supplies each session ID over USB.
#define TRIAL_ID "host-configured-session"
#define FIRMWARE_REVISION "development"
#define TEST_PACKET_BYTES 128
#define TEST_INTERVAL_MS 200
#define ECHO_TIMEOUT_MS 1000
// Set either limit to 0 for an open-ended run. Reflash after changing firmware settings.
#define TARGET_PACKET_COUNT 0
#define TEST_DURATION_MS 0
// Retain timed-out packets for this long so late replies are observable.
#define LATE_REPLY_GRACE_MS 1000

// Wi-Fi UDP echo test agent for Raspberry Pi Pico 2 W.
// Emits newline-delimited JSON on USB serial at 115200 baud.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "secrets.h"

namespace {

constexpr uint32_t kMagic = 0x524C4142;  // "RLAB"
constexpr size_t kHeaderBytes = 12;
constexpr size_t kMaxPacketBytes = 512;

struct __attribute__((packed)) TestPacketHeader {
  uint32_t magic;
  uint32_t sequence;
  uint32_t sent_us;
};

static_assert(sizeof(TestPacketHeader) == kHeaderBytes, "Unexpected packet header size");
static_assert(TEST_PACKET_BYTES >= kHeaderBytes, "TEST_PACKET_BYTES is too small");
static_assert(TEST_PACKET_BYTES <= kMaxPacketBytes, "TEST_PACKET_BYTES exceeds local buffer");

WiFiUDP udp;
IPAddress echo_server_ip(ECHO_SERVER_IP);
uint32_t sequence_number = 0;
uint8_t packet_buffer[kMaxPacketBytes];

void emit_event(const char* event, const char* status, uint32_t sequence,
                uint32_t sent_us, uint32_t rtt_us, int rssi_dbm) {
  Serial.printf(
      "{\"schema_version\":1,\"event\":\"%s\",\"device_id\":\"%s\","
      "\"status\":\"%s\",\"sequence\":%lu,\"payload_bytes\":%u,"
      "\"sent_monotonic_us\":%lu,\"observed_monotonic_us\":%lu,"
      "\"rtt_us\":%lu,\"rssi_dbm\":%d}\n",
      event, DEVICE_ID, status, static_cast<unsigned long>(sequence),
      static_cast<unsigned>(TEST_PACKET_BYTES), static_cast<unsigned long>(sent_us),
      static_cast<unsigned long>(micros()), static_cast<unsigned long>(rtt_us), rssi_dbm);
}

void emit_hotspot_visibility() {
  const int network_count = WiFi.scanNetworks();
  int hotspot_rssi_dbm = 0;
  for (int index = 0; index < network_count; ++index) {
    if (WiFi.SSID(index) == WIFI_SSID) {
      hotspot_rssi_dbm = WiFi.RSSI(index);
      break;
    }
  }
  Serial.printf(
      "{\"schema_version\":1,\"event\":\"wifi_scan\",\"device_id\":\"%s\","
      "\"status\":\"%s\",\"networks_seen\":%d,\"configured_ssid_rssi_dbm\":%d}\n",
      DEVICE_ID, hotspot_rssi_dbm == 0 ? "configured_ssid_not_seen" : "configured_ssid_seen",
      network_count, hotspot_rssi_dbm);
}

bool connect_wifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(DEVICE_ID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  const uint32_t started_ms = millis();

  while (WiFi.status() != WL_CONNECTED && millis() - started_ms < 30000) {
    emit_event("wifi_state", "connecting", 0, 0, 0, 0);
    delay(1000);
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf(
        "{\"schema_version\":1,\"event\":\"wifi_state\",\"device_id\":\"%s\","
        "\"status\":\"connect_timeout\",\"wifi_status_code\":%d}\n",
        DEVICE_ID, WiFi.status());
    emit_hotspot_visibility();
    return false;
  }
  Serial.printf(
      "{\"schema_version\":1,\"event\":\"wifi_state\",\"device_id\":\"%s\","
      "\"status\":\"connected\",\"ip\":\"%s\",\"rssi_dbm\":%d}\n",
      DEVICE_ID, WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

void run_echo_attempt() {
  const uint32_t sent_us = micros();
  TestPacketHeader header{kMagic, sequence_number, sent_us};
  memcpy(packet_buffer, &header, sizeof(header));
  for (size_t index = sizeof(header); index < TEST_PACKET_BYTES; ++index) {
    packet_buffer[index] = static_cast<uint8_t>(sequence_number + index);
  }

  if (!udp.beginPacket(echo_server_ip, ECHO_SERVER_PORT) ||
      udp.write(packet_buffer, TEST_PACKET_BYTES) != TEST_PACKET_BYTES || !udp.endPacket()) {
    emit_event("packet_result", "send_error", sequence_number++, sent_us, 0, WiFi.RSSI());
    return;
  }

  const uint32_t deadline_us = micros() + ECHO_TIMEOUT_MS * 1000UL;
  while (static_cast<int32_t>(micros() - deadline_us) < 0) {
    const int received_bytes = udp.parsePacket();
    if (received_bytes < static_cast<int>(sizeof(TestPacketHeader))) {
      delay(1);
      continue;
    }
    const int bytes_read = udp.read(packet_buffer, min(received_bytes, static_cast<int>(kMaxPacketBytes)));
    TestPacketHeader received_header{};
    memcpy(&received_header, packet_buffer, sizeof(received_header));
    if (bytes_read >= static_cast<int>(sizeof(received_header)) &&
        received_header.magic == kMagic && received_header.sequence == sequence_number) {
      emit_event("packet_result", "echoed", sequence_number++, sent_us, micros() - sent_us, WiFi.RSSI());
      return;
    }
  }
  emit_event("packet_result", "timeout", sequence_number++, sent_us, 0, WiFi.RSSI());
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(LED_BUILTIN, OUTPUT);
  udp.begin(LOCAL_UDP_PORT);
  connect_wifi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connect_wifi();
    delay(1000);
    return;
  }

  digitalWrite(LED_BUILTIN, HIGH);
  run_echo_attempt();
  digitalWrite(LED_BUILTIN, LOW);
  delay(TEST_INTERVAL_MS);
}

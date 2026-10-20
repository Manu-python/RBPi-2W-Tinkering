// Private 2.4 GHz WPA2 access point and UDP echo host for range testing.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "esp32_hotspot_secrets.h"

namespace {

WiFiUDP udp;
uint8_t packet_buffer[1472];
uint32_t echoed_packets = 0;
uint32_t echoed_bytes = 0;
uint32_t last_stats_ms = 0;

void emit_state(const char* status) {
  Serial.printf(
      "{\"schema_version\":1,\"event\":\"ap_state\",\"device_id\":\"%s\","
      "\"status\":\"%s\",\"ip\":\"%s\",\"channel\":%d}\n",
      ESP_AP_DEVICE_ID, status, WiFi.softAPIP().toString().c_str(), ESP_AP_CHANNEL);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(500);
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(ESP_AP_SSID, ESP_AP_PASSWORD, ESP_AP_CHANNEL)) {
    emit_state("start_failed");
    return;
  }
  udp.begin(ESP_ECHO_PORT);
  emit_state("ready");
}

void loop() {
  const int received_bytes = udp.parsePacket();
  if (received_bytes > 0) {
    const int bytes_to_read = min(received_bytes, static_cast<int>(sizeof(packet_buffer)));
    const int bytes_read = udp.read(packet_buffer, bytes_to_read);
    udp.beginPacket(udp.remoteIP(), udp.remotePort());
    udp.write(packet_buffer, bytes_read);
    udp.endPacket();
    echoed_packets++;
    echoed_bytes += bytes_read;
  }

  if (millis() - last_stats_ms >= 1000) {
    last_stats_ms = millis();
    Serial.printf(
        "{\"schema_version\":1,\"event\":\"echo_stats\",\"device_id\":\"%s\","
        "\"echoed_packets\":%lu,\"echoed_bytes\":%lu,\"stations\":%d}\n",
        ESP_AP_DEVICE_ID, static_cast<unsigned long>(echoed_packets),
        static_cast<unsigned long>(echoed_bytes), WiFi.softAPgetStationNum());
  }
}

// Wireless Range Lab ESP32-S3 access point and transparent UDP echo server.
#include <Arduino.h>
#include <HWCDC.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp32_hotspot_secrets.h"
#include "range_lab_protocol.h"

#ifndef ESP_FIRMWARE_REVISION
#define ESP_FIRMWARE_REVISION "unknown"
#endif

namespace {
constexpr size_t kMaxPacketBytes=512;
WiFiUDP udp; uint8_t buffer[kMaxPacketBytes]; uint32_t packets=0, bytes=0, last_stats_ms=0;
// COM17 is the ESP32-S3's built-in USB Serial/JTAG interface.  Use it
// explicitly instead of depending on the board profile's Serial routing.
#define RANGE_LAB_SERIAL HWCDCSerial
void prefix(const char* event,const char* status,uint32_t session=0) {
  RANGE_LAB_SERIAL.printf("{\"schema_version\":2,\"event\":\"%s\",\"status\":\"%s\",\"device_id\":\"%s\",\"device_role\":\"esp32_s3\",\"session_id\":%lu,\"monotonic_us\":%lu",event,status,ESP_AP_DEVICE_ID,(unsigned long)session,(unsigned long)micros());
}
void ap_state(const char* status) { prefix("ap_state",status); RANGE_LAB_SERIAL.printf(",\"ip\":\"%s\",\"channel\":%d,\"stations\":%d,\"firmware_revision\":\"%s\"}\n",WiFi.softAPIP().toString().c_str(),ESP_AP_CHANNEL,WiFi.softAPgetStationNum(),ESP_FIRMWARE_REVISION); }
void packet_rx(const char* status,const range_lab::PacketFields& f,int length,const char* validation,IPAddress ip,uint16_t port) {
  prefix("packet_rx",status,f.session_id); RANGE_LAB_SERIAL.printf(",\"sequence\":%lu,\"sent_monotonic_us\":%lu,\"source_ip\":\"%s\",\"source_port\":%u,\"received_bytes\":%d,\"validation\":\"%s\"}\n",(unsigned long)f.sequence,(unsigned long)f.sent_monotonic_us,ip.toString().c_str(),(unsigned)port,length,validation);
}
void echo_event(const char* event,const char* status,const range_lab::PacketFields& f,int length,IPAddress ip,uint16_t port,bool begin,bool write,bool end) {
  prefix(event,status,f.session_id); RANGE_LAB_SERIAL.printf(",\"sequence\":%lu,\"source_ip\":\"%s\",\"source_port\":%u,\"datagram_bytes\":%d,\"begin_packet_ok\":%s,\"write_ok\":%s,\"end_packet_ok\":%s}\n",(unsigned long)f.sequence,ip.toString().c_str(),(unsigned)port,length,begin?"true":"false",write?"true":"false",end?"true":"false");
}
}
void setup() { RANGE_LAB_SERIAL.begin(115200); delay(500); WiFi.mode(WIFI_AP); if(!WiFi.softAP(ESP_AP_SSID,ESP_AP_PASSWORD,ESP_AP_CHANNEL)) { ap_state("start_failed"); return; } udp.begin(ESP_ECHO_PORT); ap_state("ready"); }
void loop() {
  const int advertised=udp.parsePacket();
  if(advertised>0) {
    const IPAddress ip=udp.remoteIP(); const uint16_t port=udp.remotePort(); const int read=udp.read(buffer,min(advertised,(int)kMaxPacketBytes));
    range_lab::PacketFields fields{}; const auto validation=range_lab::validate_packet(buffer,read,&fields);
    const bool valid=advertised<=(int)kMaxPacketBytes && validation==range_lab::ValidationError::kValid;
    // This observation is deliberately emitted before attempting the echo.
    packet_rx(valid?"received":"invalid",fields,advertised,range_lab::validation_error_name(validation),ip,port);
    if(valid) {
      echo_event("echo_attempt","attempted",fields,read,ip,port,false,false,false);
      const bool begin=udp.beginPacket(ip,port); const size_t written=begin?udp.write(buffer,read):0; const bool write=written==(size_t)read; const bool end=begin&&write&&udp.endPacket();
      // endPacket() is only a local API result, not evidence of Pico receipt.
      echo_event("echo_result",end?"api_success":"api_failure",fields,read,ip,port,begin,write,end);
      ++packets; bytes+=read;
    }
  }
  if(millis()-last_stats_ms>=1000) { last_stats_ms=millis(); prefix("echo_stats","active"); RANGE_LAB_SERIAL.printf(",\"echoed_packets\":%lu,\"echoed_bytes\":%lu,\"stations\":%d}\n",(unsigned long)packets,(unsigned long)bytes,WiFi.softAPgetStationNum()); }
}

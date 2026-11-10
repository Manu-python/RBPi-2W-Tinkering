// Wireless Range Lab Pico agent: non-blocking UDP echo diagnostics.
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <cstring>
#include "range_lab_protocol.h"
#include "secrets.h"

// Defaults keep an existing local secrets.h buildable. Configure new runs from the host.
#ifndef TRIAL_ID
#define TRIAL_ID "unconfigured-session"
#endif
#ifndef TARGET_PACKET_COUNT
#define TARGET_PACKET_COUNT 0
#endif
#ifndef TEST_DURATION_MS
#define TEST_DURATION_MS 0
#endif
#ifndef LATE_REPLY_GRACE_MS
#define LATE_REPLY_GRACE_MS 1000
#endif
#ifndef FIRMWARE_REVISION
#define FIRMWARE_REVISION "unknown"
#endif

namespace {
constexpr size_t kMaxPacketBytes = 512, kPendingSlots = 16, kRecentSlots = 32;
static_assert(TEST_PACKET_BYTES >= range_lab::kHeaderBytes, "packet too small");
static_assert(TEST_PACKET_BYTES <= kMaxPacketBytes, "packet too large");
struct Pending { bool used=false, deadline=false; uint32_t seq=0, sent=0, due=0, finalize=0; };
WiFiUDP udp; IPAddress server(ECHO_SERVER_IP); uint8_t buffer[kMaxPacketBytes];
Pending pending[kPendingSlots]; uint32_t recent[kRecentSlots]{};
uint8_t recent_at=0; uint32_t session=0, next_seq=0, started_ms=0, last_send_ms=0;
bool connected_once=false, complete_emitted=false, session_active=false;
char active_trial_id[80] = "unconfigured";

bool reached(uint32_t now, uint32_t then) { return static_cast<int32_t>(now - then) >= 0; }
void prefix(const char* event, const char* status) {
  Serial.printf("{\"schema_version\":2,\"event\":\"%s\",\"status\":\"%s\",\"device_id\":\"%s\",\"device_role\":\"pico\",\"trial_id\":\"%s\",\"session_id\":%lu,\"monotonic_us\":%lu", event,status,DEVICE_ID,active_trial_id,(unsigned long)session,(unsigned long)micros());
}
void config_event() {
  prefix("session_config",session_active?"active":"awaiting_host");
  Serial.printf(",\"packet_bytes\":%u,\"packet_interval_ms\":%u,\"echo_timeout_ms\":%u,\"late_reply_grace_ms\":%u,\"target_packet_count\":%lu,\"test_duration_ms\":%lu,\"firmware_revision\":\"%s\"}\n",(unsigned)TEST_PACKET_BYTES,(unsigned)TEST_INTERVAL_MS,(unsigned)ECHO_TIMEOUT_MS,(unsigned)LATE_REPLY_GRACE_MS,(unsigned long)TARGET_PACKET_COUNT,(unsigned long)TEST_DURATION_MS,FIRMWARE_REVISION);
}
void wifi_event(const char* status) {
  prefix("wifi_state",status);
  Serial.printf(",\"wifi_status_code\":%d,\"ip\":\"%s\",\"rssi_dbm\":%d}\n",WiFi.status(),WiFi.localIP().toString().c_str(),WiFi.status()==WL_CONNECTED?WiFi.RSSI():0);
}
void tx_event(const char* status,uint32_t seq,uint32_t sent,bool begin,size_t written,bool end) {
  prefix("packet_tx",status);
  Serial.printf(",\"sequence\":%lu,\"sent_monotonic_us\":%lu,\"destination_ip\":\"%s\",\"destination_port\":%u,\"datagram_bytes\":%u,\"begin_packet_ok\":%s,\"bytes_written\":%u,\"end_packet_ok\":%s,\"wifi_status_code\":%d,\"rssi_dbm\":%d}\n",(unsigned long)seq,(unsigned long)sent,server.toString().c_str(),(unsigned)ECHO_SERVER_PORT,(unsigned)TEST_PACKET_BYTES,begin?"true":"false",(unsigned)written,end?"true":"false",WiFi.status(),WiFi.RSSI());
}
void rx_event(const char* status,uint32_t seq,uint32_t sent,int length,const char* validation,IPAddress ip,uint16_t port,uint32_t rtt) {
  prefix("packet_rx",status);
  Serial.printf(",\"sequence\":%lu,\"sent_monotonic_us\":%lu,\"source_ip\":\"%s\",\"source_port\":%u,\"received_bytes\":%d,\"validation\":\"%s\",\"rtt_us\":%lu,\"wifi_status_code\":%d,\"rssi_dbm\":%d}\n",(unsigned long)seq,(unsigned long)sent,ip.toString().c_str(),(unsigned)port,length,validation,(unsigned long)rtt,WiFi.status(),WiFi.RSSI());
}
void pending_event(const char* event,const Pending& p) {
  prefix(event,event[7]=='d'?"deadline_expired":"unobserved");
  Serial.printf(",\"sequence\":%lu,\"sent_monotonic_us\":%lu,\"echo_timeout_ms\":%u,\"late_reply_grace_ms\":%u,\"rssi_dbm\":%d}\n",(unsigned long)p.seq,(unsigned long)p.sent,(unsigned)ECHO_TIMEOUT_MS,(unsigned)LATE_REPLY_GRACE_MS,WiFi.RSSI());
}
int pending_for(uint32_t seq) { for(size_t i=0;i<kPendingSlots;++i) if(pending[i].used&&pending[i].seq==seq) return i; return -1; }
int free_pending() { for(size_t i=0;i<kPendingSlots;++i) if(!pending[i].used) return i; return -1; }
bool recent_has(uint32_t seq) { for(uint32_t value:recent) if(value==seq) return true; return false; }
void remember(uint32_t seq) { recent[recent_at++%kRecentSlots]=seq; }
bool any_pending() { for(const Pending& p:pending) if(p.used) return true; return false; }
bool valid_trial_id(const char* value) {
  if(!*value) return false;
  for(;*value;++value) if(!((*value>='A'&&*value<='Z')||(*value>='a'&&*value<='z')||(*value>='0'&&*value<='9')||*value=='_'||*value=='-'||*value=='+')) return false;
  return true;
}
void start_session(const char* trial_id) {
  if(!valid_trial_id(trial_id) || strlen(trial_id)>=sizeof(active_trial_id)) { prefix("session_config","invalid_session_command"); Serial.println("}"); return; }
  strncpy(active_trial_id,trial_id,sizeof(active_trial_id)); active_trial_id[sizeof(active_trial_id)-1]='\0';
  session=range_lab::session_id_for(active_trial_id); next_seq=0; recent_at=0; memset(recent,0,sizeof(recent));
  for(Pending& p:pending) p.used=false;
  started_ms=millis(); last_send_ms=0; complete_emitted=false; session_active=true; config_event();
}
void poll_control() {
  static char command[96]; static size_t length=0;
  while(Serial.available()>0) {
    const char value=static_cast<char>(Serial.read());
    if(value=='\n' || value=='\r') {
      command[length]='\0';
      constexpr const char* kPrefix="RLAB_SESSION ";
      if(strncmp(command,kPrefix,strlen(kPrefix))==0) start_session(command+strlen(kPrefix));
      else if(length>0) { prefix("session_config","unknown_command"); Serial.println("}"); }
      length=0;
    } else if(length<sizeof(command)-1) command[length++]=value;
    else length=0;
  }
}

bool connect_wifi() {
  wifi_event(connected_once?"reconnecting":"connecting"); WiFi.mode(WIFI_STA); WiFi.setHostname(DEVICE_ID); WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  const uint32_t began=millis(); while(WiFi.status()!=WL_CONNECTED && millis()-began<30000) delay(100);
  if(WiFi.status()!=WL_CONNECTED) { wifi_event("connect_timeout"); return false; }
  wifi_event(connected_once?"reconnected":"connected"); connected_once=true; return true;
}
void poll_udp() {
  const int advertised=udp.parsePacket(); if(advertised<=0) return;
  IPAddress ip=udp.remoteIP(); uint16_t port=udp.remotePort(); const int read=udp.read(buffer,min(advertised,(int)kMaxPacketBytes));
  range_lab::PacketFields fields{}; const auto error=range_lab::validate_packet(buffer,read,&fields);
  if(advertised>(int)kMaxPacketBytes || error!=range_lab::ValidationError::kValid) { rx_event("invalid",0,0,advertised,range_lab::validation_error_name(error),ip,port,0); return; }
  if(fields.session_id!=session) { rx_event("unexpected",fields.sequence,fields.sent_monotonic_us,advertised,"wrong_session",ip,port,0); return; }
  const int slot=pending_for(fields.sequence);
  if(slot<0) { rx_event(recent_has(fields.sequence)?"duplicate":"unexpected",fields.sequence,fields.sent_monotonic_us,advertised,"valid",ip,port,0); return; }
  const uint32_t now=micros(); const bool late=reached(now,pending[slot].due);
  rx_event(late?"echo_late":"echo_on_time",fields.sequence,pending[slot].sent,advertised,"valid",ip,port,now-pending[slot].sent);
  remember(fields.sequence); pending[slot].used=false;
}
void update_pending() {
  const uint32_t now=micros(); for(Pending& p:pending) { if(!p.used) continue;
    if(!p.deadline && reached(now,p.due)) { p.deadline=true; pending_event("packet_deadline",p); }
    if(reached(now,p.finalize)) { pending_event("packet_finalized",p); remember(p.seq); p.used=false; }
  }
}
bool may_send() { return session_active && (TARGET_PACKET_COUNT==0||next_seq<TARGET_PACKET_COUNT) && (TEST_DURATION_MS==0||millis()-started_ms<TEST_DURATION_MS); }
void send_if_due() {
  if(!may_send() || millis()-last_send_ms<TEST_INTERVAL_MS) return; last_send_ms=millis(); const uint32_t sent=micros(),seq=next_seq++; const int slot=free_pending();
  if(slot<0) { tx_event("pending_table_full",seq,sent,false,0,false); return; }
  range_lab::build_packet(buffer,TEST_PACKET_BYTES,{session,seq,sent,(uint16_t)TEST_PACKET_BYTES,(uint16_t)(TEST_PACKET_BYTES-range_lab::kHeaderBytes)});
  const bool begin=udp.beginPacket(server,ECHO_SERVER_PORT); const size_t written=begin?udp.write(buffer,TEST_PACKET_BYTES):0; const bool end=begin&&written==TEST_PACKET_BYTES&&udp.endPacket();
  tx_event(end?"sent":"send_error",seq,sent,begin,written,end); if(end) pending[slot]={true,false,seq,sent,sent+ECHO_TIMEOUT_MS*1000UL,sent+(ECHO_TIMEOUT_MS+LATE_REPLY_GRACE_MS)*1000UL};
}
}

void setup() { Serial.begin(115200); delay(500); pinMode(LED_BUILTIN,OUTPUT); started_ms=millis(); udp.begin(LOCAL_UDP_PORT); config_event(); connect_wifi(); }
void loop() {
  poll_control();
  if(WiFi.status()!=WL_CONNECTED) { digitalWrite(LED_BUILTIN,LOW); connect_wifi(); delay(250); return; }
  poll_udp(); update_pending();
  if(may_send()) { digitalWrite(LED_BUILTIN,HIGH); send_if_due(); }
  else { digitalWrite(LED_BUILTIN,LOW); if(session_active&&!complete_emitted&&!any_pending()) { prefix("trial_complete","collection_window_complete"); Serial.println("}"); complete_emitted=true; } }
}

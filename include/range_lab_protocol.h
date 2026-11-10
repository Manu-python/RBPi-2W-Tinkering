#pragma once

// Shared, allocation-free UDP packet codec. All multi-byte fields are big-endian.

#include <Arduino.h>

namespace range_lab {

constexpr uint32_t kMagic = 0x524C4232UL;  // ASCII "RLB2"
constexpr uint8_t kVersion = 2;
constexpr size_t kHeaderBytes = 28;
constexpr size_t kCrcOffset = 24;

struct PacketFields {
  uint32_t session_id;
  uint32_t sequence;
  uint32_t sent_monotonic_us;
  uint16_t datagram_bytes;
  uint16_t payload_bytes;
};

enum class ValidationError : uint8_t {
  kValid,
  kTooShort,
  kBadMagic,
  kUnsupportedVersion,
  kBadHeaderLength,
  kLengthMismatch,
  kBadCrc,
};

inline void write_u16_be(uint8_t* bytes, uint16_t value) {
  bytes[0] = static_cast<uint8_t>(value >> 8);
  bytes[1] = static_cast<uint8_t>(value);
}

inline void write_u32_be(uint8_t* bytes, uint32_t value) {
  bytes[0] = static_cast<uint8_t>(value >> 24);
  bytes[1] = static_cast<uint8_t>(value >> 16);
  bytes[2] = static_cast<uint8_t>(value >> 8);
  bytes[3] = static_cast<uint8_t>(value);
}

inline uint16_t read_u16_be(const uint8_t* bytes) {
  return (static_cast<uint16_t>(bytes[0]) << 8) | bytes[1];
}

inline uint32_t read_u32_be(const uint8_t* bytes) {
  return (static_cast<uint32_t>(bytes[0]) << 24) |
         (static_cast<uint32_t>(bytes[1]) << 16) |
         (static_cast<uint32_t>(bytes[2]) << 8) | bytes[3];
}

// IEEE CRC-32 (polynomial 0xEDB88320), with the CRC field treated as zero.
inline uint32_t crc32_with_zeroed_field(const uint8_t* bytes, size_t length) {
  uint32_t crc = 0xFFFFFFFFUL;
  for (size_t index = 0; index < length; ++index) {
    uint8_t value = (index >= kCrcOffset && index < kCrcOffset + 4) ? 0 : bytes[index];
    crc ^= value;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc >> 1) ^ ((crc & 1U) ? 0xEDB88320UL : 0);
    }
  }
  return ~crc;
}

inline uint32_t session_id_for(const char* trial_id) {
  // FNV-1a 32-bit. This is a correlation key, not a secret or cryptographic hash.
  uint32_t hash = 2166136261UL;
  while (*trial_id) {
    hash ^= static_cast<uint8_t>(*trial_id++);
    hash *= 16777619UL;
  }
  return hash;
}

inline void build_packet(uint8_t* bytes, size_t datagram_bytes, const PacketFields& fields) {
  write_u32_be(bytes, kMagic);
  bytes[4] = kVersion;
  bytes[5] = kHeaderBytes;
  write_u16_be(bytes + 6, 0);  // Flags reserved for future experiments.
  write_u32_be(bytes + 8, fields.session_id);
  write_u32_be(bytes + 12, fields.sequence);
  write_u32_be(bytes + 16, fields.sent_monotonic_us);
  write_u16_be(bytes + 20, static_cast<uint16_t>(datagram_bytes));
  write_u16_be(bytes + 22, static_cast<uint16_t>(datagram_bytes - kHeaderBytes));
  write_u32_be(bytes + kCrcOffset, 0);
  for (size_t index = kHeaderBytes; index < datagram_bytes; ++index) {
    bytes[index] = static_cast<uint8_t>((fields.session_id + fields.sequence + index) & 0xFFU);
  }
  write_u32_be(bytes + kCrcOffset, crc32_with_zeroed_field(bytes, datagram_bytes));
}

inline ValidationError validate_packet(const uint8_t* bytes, size_t received_bytes,
                                       PacketFields* fields) {
  if (received_bytes < kHeaderBytes) return ValidationError::kTooShort;
  if (read_u32_be(bytes) != kMagic) return ValidationError::kBadMagic;
  if (bytes[4] != kVersion) return ValidationError::kUnsupportedVersion;
  if (bytes[5] != kHeaderBytes) return ValidationError::kBadHeaderLength;
  const uint16_t datagram_bytes = read_u16_be(bytes + 20);
  const uint16_t payload_bytes = read_u16_be(bytes + 22);
  if (datagram_bytes != received_bytes || payload_bytes != datagram_bytes - kHeaderBytes)
    return ValidationError::kLengthMismatch;
  if (read_u32_be(bytes + kCrcOffset) != crc32_with_zeroed_field(bytes, received_bytes))
    return ValidationError::kBadCrc;
  if (fields != nullptr) {
    fields->session_id = read_u32_be(bytes + 8);
    fields->sequence = read_u32_be(bytes + 12);
    fields->sent_monotonic_us = read_u32_be(bytes + 16);
    fields->datagram_bytes = datagram_bytes;
    fields->payload_bytes = payload_bytes;
  }
  return ValidationError::kValid;
}

inline const char* validation_error_name(ValidationError error) {
  switch (error) {
    case ValidationError::kValid: return "valid";
    case ValidationError::kTooShort: return "too_short";
    case ValidationError::kBadMagic: return "bad_magic";
    case ValidationError::kUnsupportedVersion: return "unsupported_version";
    case ValidationError::kBadHeaderLength: return "bad_header_length";
    case ValidationError::kLengthMismatch: return "length_mismatch";
    case ValidationError::kBadCrc: return "crc_failed";
  }
  return "unknown";
}

}  // namespace range_lab

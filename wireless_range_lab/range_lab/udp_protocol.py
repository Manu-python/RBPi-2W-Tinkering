"""Host-side reference codec for the UDP packet layout.

The firmware implementation is allocation-free C++; this module exists for
fixtures and validation tests, not for transmitting test traffic from the host.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib

MAGIC = 0x524C4232  # RLB2
VERSION = 2
HEADER_BYTES = 28
_HEADER = struct.Struct("!IBBHIIIHHI")


class PacketValidationError(ValueError):
    """A datagram did not satisfy the application-level contract."""


@dataclass(frozen=True)
class Packet:
    session_id: int
    sequence: int
    sent_monotonic_us: int
    payload: bytes


def session_id_for(trial_id: str) -> int:
    """FNV-1a 32-bit, matching the firmware correlation key."""
    value = 2166136261
    for byte in trial_id.encode("utf-8"):
        value = (value ^ byte) * 16777619 & 0xFFFFFFFF
    return value


def _crc_with_zeroed_field(datagram: bytes) -> int:
    mutable = bytearray(datagram)
    mutable[24:28] = b"\0\0\0\0"
    return zlib.crc32(mutable) & 0xFFFFFFFF


def encode_packet(packet: Packet, datagram_bytes: int = 128) -> bytes:
    if datagram_bytes < HEADER_BYTES:
        raise ValueError("datagram_bytes must fit the protocol header")
    expected_payload = datagram_bytes - HEADER_BYTES
    if len(packet.payload) != expected_payload:
        raise ValueError("payload must fill the requested fixed-size datagram")
    header = _HEADER.pack(
        MAGIC, VERSION, HEADER_BYTES, 0, packet.session_id, packet.sequence,
        packet.sent_monotonic_us, datagram_bytes, expected_payload, 0,
    )
    datagram = header + packet.payload
    return datagram[:24] + struct.pack("!I", _crc_with_zeroed_field(datagram)) + datagram[28:]


def deterministic_payload(session_id: int, sequence: int, datagram_bytes: int = 128) -> bytes:
    return bytes((session_id + sequence + index) & 0xFF for index in range(HEADER_BYTES, datagram_bytes))


def decode_packet(datagram: bytes) -> Packet:
    if len(datagram) < HEADER_BYTES:
        raise PacketValidationError("too_short")
    magic, version, header_bytes, _flags, session_id, sequence, sent_us, total, payload_bytes, crc = _HEADER.unpack_from(datagram)
    if magic != MAGIC:
        raise PacketValidationError("bad_magic")
    if version != VERSION:
        raise PacketValidationError("unsupported_version")
    if header_bytes != HEADER_BYTES:
        raise PacketValidationError("bad_header_length")
    if total != len(datagram) or payload_bytes != total - HEADER_BYTES:
        raise PacketValidationError("length_mismatch")
    if crc != _crc_with_zeroed_field(datagram):
        raise PacketValidationError("crc_failed")
    return Packet(session_id, sequence, sent_us, datagram[HEADER_BYTES:])

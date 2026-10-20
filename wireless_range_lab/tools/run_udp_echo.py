"""Run a transparent UDP echo service on the laptop during a Wi-Fi trial."""

from __future__ import annotations

import argparse
import socket
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="UDP echo service for Wireless Range Lab")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3333)
    arguments = parser.parse_args()
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((arguments.host, arguments.port))
    server.settimeout(1.0)
    packets = 0
    payload_bytes = 0
    print(f"UDP echo listening on {arguments.host}:{arguments.port}. Press Ctrl+C to stop.")
    try:
        while True:
            try:
                payload, address = server.recvfrom(2048)
            except TimeoutError:
                continue
            server.sendto(payload, address)
            packets += 1
            payload_bytes += len(payload)
            print(f"{time.strftime('%H:%M:%S')} echoed {len(payload)} bytes from {address[0]}:{address[1]} (packets={packets}, bytes={payload_bytes})")
    except KeyboardInterrupt:
        print(f"Stopped. Echoed {packets} packets / {payload_bytes} bytes.")
    finally:
        server.close()


if __name__ == "__main__":
    main()

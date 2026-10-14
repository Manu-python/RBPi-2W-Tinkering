# Raspberry Pi Pico 2 W — PlatformIO playground

This project targets the Raspberry Pi **Pico 2 W** (RP2350) using PlatformIO and the Arduino-Pico framework.

## Open and build

1. Open this folder in VS Code.
2. Use the PlatformIO alien-head button in the left sidebar, then run **Project Tasks → pico2_w → Build**.
3. PlatformIO downloads its toolchain and board support on the first build, so that one can take a few minutes.

## Upload the starter blink sketch

1. Connect the Pico 2 W with a data-capable USB cable.
2. For the first upload, hold **BOOTSEL** while plugging it in, then release it. Windows should show an `RPI-RP2` USB drive.
3. Run **Upload** in PlatformIO. The built-in LED will blink twice per second and the serial monitor will print `blink` at 115200 baud.

The Pico 2 W's onboard LED is attached through its wireless chip. `LED_BUILTIN` handles that detail in Arduino-Pico; do not replace it with a numbered GPIO.

## Useful commands

Run these from PlatformIO's integrated terminal after installing its shell commands:

```powershell
pio run
pio run -t upload
pio device monitor -b 115200
```

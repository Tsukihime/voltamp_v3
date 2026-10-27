# VoltAmp — Digital Bench Power Supply

Firmware for a DIY digitally controlled laboratory power supply based on the **ATmega32** microcontroller.

The project provides adjustable voltage and current regulation, real-time measurements, a color LCD interface, and remote control via Bluetooth using SCPI commands.

## Features

- Adjustable output voltage: 0–30 V
- Adjustable current limit: 0–3 A
- Constant Voltage (CV) and Constant Current (CC) operation
- Real-time voltage, current, power, and energy measurements
- 1.8" ST7735 color LCD
- Rotary encoders for voltage and current adjustment
- Automatic voltage and current offset correction to compensate for thermal drift
- ADC and DAC calibration
- Bluetooth remote control with SCPI command support
- EEPROM storage for user settings

## Hardware

- **MCU:** ATmega32
- **Display:** ST7735 TFT LCD (160×128)
- **Controls:** Rotary encoders, buttons, and output switch
- **Communication:** UART / Bluetooth (9600 baud)
- **Analog circuitry:** External ADC/DAC and analog CV/CC regulation

## Firmware

Written in C++ using AVR-GCC.

The project file `voltamp_v3.cppproj` is provided for Microchip Studio (Atmel Studio).

## SCPI Interface

The firmware supports remote commands for:

- Setting and reading voltage and current limits
- Enabling and disabling the output
- Reading measured voltage, current, power, and energy
- Reading the active CV/CC mode
- Querying device information and SCPI errors

Example commands:

```text
*IDN?
SOUR:VOLT?
SOUR:CURR?
MEAS:VOLT?
MEAS:CURR?
MEAS:POW?
OUTP?
```

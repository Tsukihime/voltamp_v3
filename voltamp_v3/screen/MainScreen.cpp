#include "MainScreen.h"

#include "../fonts/Font16x24.h"
#include "../fonts/Font11x16.h"
#include "../fonts/Font4x14.h"
#include "../fonts/Font6x8.h"
#include "../ST7735Lcd.h"
#include "../utils.h"

#define SAT0(x)  ((x) > 0 ? (x) : 0)

uint8_t m_voltage[5] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
uint8_t m_voltageLimit[5] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
uint8_t m_current[5] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
uint8_t m_currentLimit[5] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
uint8_t m_power[5] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
uint8_t m_energy[5] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF };

AdjustmentLevel voltageOldAdjustment = AdjustmentLevel::END;
AdjustmentLevel currentOldAdjustment = AdjustmentLevel::END;

namespace ScreenColors {
    const uint16_t BACKGROUND = ST7735::Colors::BLACK;
    const uint16_t GREEN = ST7735Lcd::rgbTo16BitColor(99, 186, 99);
    const uint16_t YELLOW = ST7735Lcd::rgbTo16BitColor(230, 235, 189);
    const uint16_t LOCK = ST7735Lcd::rgbTo16BitColor(230, 235, 189);
    const uint16_t VOLTAGE = ST7735Lcd::rgbTo16BitColor(147, 233, 140);
    const uint16_t VOLTAGE_LIMIT = ST7735Lcd::rgbTo16BitColor(178, 212, 241);
    const uint16_t CURRENT = ST7735Lcd::rgbTo16BitColor(212, 236, 142);
    const uint16_t CURRENT_LIMIT = ST7735Lcd::rgbTo16BitColor(178, 212, 241);
    const uint16_t TEXT = ST7735Lcd::rgbTo16BitColor(178, 212, 241);
    const uint16_t WATT = ST7735Lcd::rgbTo16BitColor(234, 157, 140);
    const uint16_t ENERGY = ST7735Lcd::rgbTo16BitColor(232, 232, 232);
    const uint16_t AJUSTMENT = VOLTAGE_LIMIT;
}

void MainScreen::DrawBorders() {
    ST7735Lcd::FillRectangle(2, 0, 156, 2, ScreenColors::GREEN); // ----
    ST7735Lcd::FillRectangle(2, 39, 156, 2, ScreenColors::GREEN); // ----
    ST7735Lcd::FillRectangle(2, 77, 156, 1, ScreenColors::GREEN); // ----

    ST7735Lcd::FillRectangle(0, 0, 2, 78, ScreenColors::GREEN); // |
    ST7735Lcd::FillRectangle(158, 0, 2, 78, ScreenColors::GREEN); // |

    ST7735Lcd::FillRectangle(2, 78, 156, 1, ScreenColors::YELLOW); // ----
    ST7735Lcd::FillRectangle(2, 101, 156, 2, ScreenColors::YELLOW); // ----
    ST7735Lcd::FillRectangle(2, 126, 156, 2, ScreenColors::YELLOW); // ----

    ST7735Lcd::FillRectangle(0, 78, 2, 75, ScreenColors::YELLOW); // |
    ST7735Lcd::FillRectangle(158, 78, 2, 75, ScreenColors::YELLOW); // |
}

void MainScreen::DrawDots() {
    ST7735Lcd::DrawChar(2, 7 + 22, 47 + 10,  ScreenColors::CURRENT, ScreenColors::BACKGROUND, Font4x14);
    ST7735Lcd::DrawChar(2, 86 + 22, 47 + 10,  ScreenColors::CURRENT_LIMIT, ScreenColors::BACKGROUND, Font4x14);
    ST7735Lcd::DrawChar(2, 7 + 36, 9 + 10, ScreenColors::VOLTAGE, ScreenColors::BACKGROUND, Font4x14);
    ST7735Lcd::DrawChar(2, 86 + 36, 9 + 10, ScreenColors::VOLTAGE_LIMIT, ScreenColors::BACKGROUND, Font4x14);
    ST7735Lcd::DrawChar(0, 40 + 28, 106 + 2, ScreenColors::WATT, ScreenColors::BACKGROUND, Font4x14);
    ST7735Lcd::DrawChar(0, 40 + 28, 81 + 2, ScreenColors::ENERGY, ScreenColors::BACKGROUND, Font4x14);
}

void MainScreen::drawString(const char* string, uint8_t x, uint8_t y, uint16_t FgColor, uint16_t BgColor) {
    uint8_t offset = 0;
    while(*string) {
        ST7735Lcd::DrawChar(*string - 0x20 /* skip escape chars */, x + offset, y, FgColor, BgColor, Font6x8);
        string++;
        offset += Font6x8.getWidth();
    }
}

void MainScreen::drawBackground() {
    ST7735Lcd::FillRectangle(0, 0, 160, 128, ScreenColors::BACKGROUND);
    DrawBorders();
    DrawDots();
    drawString("VOLTS", 46, 6, ScreenColors::TEXT, ScreenColors::BACKGROUND);
    drawString("AMPERES", 34, 45, ScreenColors::TEXT, ScreenColors::BACKGROUND);
    drawString("LIMIT", 125, 6, ScreenColors::TEXT, ScreenColors::BACKGROUND);
    drawString("LIMIT", 125, 45, ScreenColors::TEXT, ScreenColors::BACKGROUND);
    drawString("WATT", 125, 111, ScreenColors::TEXT, ScreenColors::BACKGROUND);
    drawString("W*H", 131, 86, ScreenColors::TEXT, ScreenColors::BACKGROUND);
}

void drawCurrentLabel(uint8_t chars[5], uint8_t old_chars[5], uint8_t x, uint8_t y, uint16_t FgColor, uint16_t BgColor) {
    if(chars[1] != old_chars[1]) {
        ST7735Lcd::DrawChar(chars[1], x + 4, y, FgColor, BgColor, Font16x24);
    }
    if(chars[2] != old_chars[2]) {
        ST7735Lcd::DrawChar(chars[2], x + 29, y + 8, FgColor, BgColor, Font11x16);
    }
    if(chars[3] != old_chars[3]) {
        ST7735Lcd::DrawChar(chars[3], x + 43, y + 8, FgColor, BgColor, Font11x16);
    }
    if(chars[4] != old_chars[4]) {
        ST7735Lcd::DrawChar(chars[4], x + 57, y + 8, FgColor, BgColor, Font11x16);
    }
}

void drawVoltageLabel(uint8_t chars[5], uint8_t old_chars[5], uint8_t x, uint8_t y, uint16_t FgColor, uint16_t BgColor) {
    if(chars[0] != old_chars[0]) {
        if(chars[0] == 0) {
            ST7735Lcd::FillRectangle(x, y, 16, 24, BgColor);
        } else {
            ST7735Lcd::DrawChar(chars[0], x, y, FgColor, BgColor, Font16x24);
        }
    }
    if(chars[1] != old_chars[1]) {
        ST7735Lcd::DrawChar(chars[1], x + 18, y, FgColor, BgColor, Font16x24);
    }
    if(chars[2] != old_chars[2]) {
        ST7735Lcd::DrawChar(chars[2], x + 43, y + 8, FgColor, BgColor, Font11x16);
    }
    if(chars[3] != old_chars[3]) {
        ST7735Lcd::DrawChar(chars[3], x + 57, y + 8, FgColor, BgColor, Font11x16);
    }
}

void drawPowerLabel(uint8_t chars[5], uint8_t old_chars[5], uint8_t x, uint8_t y, uint16_t FgColor, uint16_t BgColor) {
    if(chars[0] != old_chars[0]) {
        if(chars[0] == 0) {
            ST7735Lcd::FillRectangle(x, y, 11, 16, BgColor);
        } else {
            ST7735Lcd::DrawChar(chars[0], x, y, FgColor, BgColor, Font11x16);
        }
    }
    if(chars[1] != old_chars[1]) {
        ST7735Lcd::DrawChar(chars[1], x + 14, y, FgColor, BgColor, Font11x16);
    }
    if(chars[2] != old_chars[2]) {
        ST7735Lcd::DrawChar(chars[2], x + 35, y, FgColor, BgColor, Font11x16);
    }
    if(chars[3] != old_chars[3]) {
        ST7735Lcd::DrawChar(chars[3], x + 49, y, FgColor, BgColor, Font11x16);
    }
    if(chars[4] != old_chars[4]) {
        ST7735Lcd::DrawChar(chars[4], x + 63, y, FgColor, BgColor, Font11x16);
    }
}

void MainScreen::setVoltage(int16_t voltage) {
    voltage = SAT0(voltage);
    uint8_t chars[5];
    bin2bcd5(voltage, chars);
    drawVoltageLabel(chars, m_voltage, 7, 9, ScreenColors::VOLTAGE, ScreenColors::BACKGROUND);
    memcpy(m_voltage, chars, 5);
}

void MainScreen::setCurrent(int16_t current) {
    current = SAT0(current);
    uint8_t chars[5];
    bin2bcd5(current, chars);
    drawCurrentLabel(chars, m_current, 7, 47, ScreenColors::CURRENT, ScreenColors::BACKGROUND);
    memcpy(m_current, chars, 5);
}

void MainScreen::setPower(int32_t power) {
    power = SAT0(power);
    uint8_t chars[10];
    bin2bcd10(power, chars);
    drawPowerLabel(&chars[5], m_power, 40, 106, ScreenColors::WATT, ScreenColors::BACKGROUND);
    memcpy(m_power, &chars[5], 5);
}

void MainScreen::setEnergy(int32_t energy) {
    energy = SAT0(energy);
    uint8_t chars[10];
    bin2bcd10(energy, chars);
    drawPowerLabel(&chars[5], m_energy, 40, 81, ScreenColors::ENERGY, ScreenColors::BACKGROUND);
    memcpy(m_energy, &chars[5], 5);
}

void MainScreen::setVoltageLimit(int16_t voltageLimit) {
    voltageLimit = SAT0(voltageLimit);
    uint8_t chars[5];
    bin2bcd5(voltageLimit, chars);
    drawVoltageLabel(chars, m_voltageLimit, 86, 9, ScreenColors::VOLTAGE_LIMIT, ScreenColors::BACKGROUND);
    memcpy(m_voltageLimit, chars, 5);
}

void MainScreen::setCurrentLimit(int16_t currentLimit) {
    currentLimit = SAT0(currentLimit);
    uint8_t chars[5];
    bin2bcd5(currentLimit, chars);
    drawCurrentLabel(chars, m_currentLimit, 86, 47, ScreenColors::CURRENT_LIMIT, ScreenColors::BACKGROUND);
    memcpy(m_currentLimit, chars, 5);
}

void MainScreen::setAdjustmentLevel(AdjustmentLevel voltageAdjustment, AdjustmentLevel currentAdjustment) {
    if(voltageOldAdjustment != voltageAdjustment) {
        switch(voltageAdjustment) {
            case AdjustmentLevel::COARSE:
                ST7735Lcd::FillRectangle(143, 35, 11, 2, ScreenColors::BACKGROUND);
                ST7735Lcd::FillRectangle(129, 35, 11, 2, ScreenColors::AJUSTMENT);
                drawString("LIMIT", 125, 6, ScreenColors::TEXT, ScreenColors::BACKGROUND);
                break;
            case AdjustmentLevel::FINE:
                ST7735Lcd::FillRectangle(143, 35, 11, 2, ScreenColors::AJUSTMENT);
                ST7735Lcd::FillRectangle(129, 35, 11, 2, ScreenColors::BACKGROUND);
                drawString("LIMIT", 125, 6, ScreenColors::TEXT, ScreenColors::BACKGROUND);
                break;
            case AdjustmentLevel::LOCK:
                ST7735Lcd::FillRectangle(129, 35, 25, 2, ScreenColors::BACKGROUND);
                drawString("LOCK  ", 125, 6, ScreenColors::LOCK, ScreenColors::BACKGROUND);
                break;
            default:
                break;
        }
    }

    if(currentOldAdjustment != currentAdjustment) {
        switch(currentAdjustment) {
            case AdjustmentLevel::COARSE:
                ST7735Lcd::FillRectangle(143, 73, 11, 2, ScreenColors::BACKGROUND);
                ST7735Lcd::FillRectangle(115, 73, 11, 2, ScreenColors::AJUSTMENT);
                drawString("LIMIT", 125, 45, ScreenColors::TEXT, ScreenColors::BACKGROUND);
                break;
            case AdjustmentLevel::FINE:
                ST7735Lcd::FillRectangle(143, 73, 11, 2, ScreenColors::AJUSTMENT);
                ST7735Lcd::FillRectangle(115, 73, 11, 2, ScreenColors::BACKGROUND);
                drawString("LIMIT", 125, 45, ScreenColors::TEXT, ScreenColors::BACKGROUND);
                break;
            case AdjustmentLevel::LOCK:
                ST7735Lcd::FillRectangle(115, 73, 39, 2, ScreenColors::BACKGROUND);
                drawString("LOCK   ", 125, 45, ScreenColors::LOCK, ScreenColors::BACKGROUND);
                break;
            default:
                break;
        }
    }

    voltageOldAdjustment = voltageAdjustment;
    currentOldAdjustment = currentAdjustment;
}

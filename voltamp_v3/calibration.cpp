#include <avr/io.h>
#include <stdlib.h>

#include "calibration.h"
#include "Dac.h"
#include "ST7735Lcd.h"
#include "Settings.h"
#include "Multimeter.h"
#include "Buttons.h"
#include "PowerSupplier.h"
#include "lib/Scheduler.h"
#include "VoltageSelector.h"
#include "utils.h"
#include "lib/AVRPin.hpp"

using OUT_EN = Pc3;

uint16_t swapbytes(uint16_t value) {
    return (value >> 8) | (value << 8);
}

void initScreen() {
    ST7735Lcd::FillScreen(ST7735::Colors::BLACK);
    MainScreen::drawString("CALIBRATION:", 8, 8, swapbytes(ST7735::Colors::GREEN), ST7735::Colors::BLACK);
    MainScreen::drawString("< FINE          COARSE >", 8, 80, swapbytes(ST7735::Colors::GREEN), ST7735::Colors::BLACK);
    MainScreen::drawString("< PREVIOUS        NEXT >", 8, 88, swapbytes(ST7735::Colors::GREEN), ST7735::Colors::BLACK);
}

void drawHeader(const char* str) {
    MainScreen::drawString(str, 8, 32, swapbytes(ST7735::Colors::GREEN), ST7735::Colors::BLACK);
}

void drawValue(uint16_t value) {
    uint8_t chars[7];
    bin2bcd5(value, &chars[0]);
    bcd2ascii(chars);
    chars[0] = '[';
    chars[5] = ']';
    chars[6] = 0;
    MainScreen::drawString((const char*)chars, 118, 32, swapbytes(ST7735::Colors::GREEN), ST7735::Colors::BLACK);           
}

void calcMinMax(int16_t one, int16_t seventeen, int16_t& zero, int16_t& max) {
    int16_t sexteen_sz = seventeen - one;
    int16_t one_sz = sexteen_sz / 16;
    zero = one - one_sz;
    max = zero + sexteen_sz * 2 - one_sz * 2;
}

void calibrate() {
    const int16_t DAC_MAX = 4095;
    static bool voltageDown = false;
    static bool currentDown = false;
    static uint8_t state = 0;
    static int16_t value;
    static int16_t adc1V;
    static int16_t adc17V;
    static int16_t dac1V;
    static int16_t dac17V;

    static int16_t adc01A;
    static int16_t adc17A;
    static int16_t dac01A;
    static int16_t dac17A;

    int8_t coarse_clicks = Buttons::voltageEncoderPopDelta();
    int8_t fine_clicks = Buttons::currentEncoderPopDelta();
    value += fine_clicks + coarse_clicks * 100;
    value = (value < 0) ? 0 : (DAC_MAX < value) ? DAC_MAX : value;

    bool voltage_click = (voltageDown & !Buttons::isVoltageEncoderPressed());
    bool current_click = (currentDown & !Buttons::isCurrentEncoderPressed());

    switch (state) {
        case 0:
            value = 100;
            initScreen();
            drawHeader("SET 1.00 VOLT     ");
            OUT_EN::SetDirWrite();
            OUT_EN::Set();
            VoltageSelector::setVoltageLevel(0);
            state = 1;
            break;
        case 1:
            drawValue(value);
            Dac::setValues(value, DAC_MAX);
            if(voltage_click) {
                Multimeter::updateValues();
                dac1V = value;
                adc1V = Multimeter::getRawVoltage();
                state = 2;
            } else if(current_click) {
                state = 0;
            }
            break;
        case 2:
            value = 2300;
            drawHeader("SET 17.00 VOLTS   ");
            VoltageSelector::setVoltageLevel(2);
            state = 3;
            break;
        case 3:
            drawValue(value);
            Dac::setValues(value, DAC_MAX);
            if(voltage_click) {
                Multimeter::updateValues();
                dac17V = value;
                adc17V = Multimeter::getRawVoltage();
                state = 4;
            } else if(current_click) {
                state = 0;
            }
            break;
        case 4:
            value = 100;
            VoltageSelector::setVoltageLevel(0);
            drawHeader("SET 0.100 AMPERES ");
            state = 5;
            break;
        case 5:
            drawValue(value);
            Dac::setValues(DAC_MAX, value);
            if(voltage_click) {
                Multimeter::updateValues();
                dac01A = value;
                adc01A = Multimeter::getRawCurrent();
                state = 6;
                } else if(current_click) {
                state = 2;
            }
            break;
        case 6:
            value = 2300;
            drawHeader("SET 1.700 AMPERES ");
            state = 7;
            break;
        case 7:
            drawValue(value);
            Dac::setValues(DAC_MAX, value);
            if(voltage_click) {
                Multimeter::updateValues();
                dac17A = value;
                adc17A = Multimeter::getRawCurrent();
                state = 8;
            } else if(current_click) {
                state = 4;
            }
            break;
        case 8:
            int16_t adcZeroV;
            int16_t adcMaxV;
            calcMinMax(adc1V, adc17V, adcZeroV, adcMaxV);

            int16_t dacZeroV;
            int16_t dacMaxV;
            calcMinMax(dac1V, dac17V, dacZeroV, dacMaxV);

            Settings::setVoltageCalibration(adcZeroV, adcMaxV, dacZeroV, dacMaxV);

            int16_t adcZeroA;
            int16_t adcMaxA;
            calcMinMax(adc01A, adc17A, adcZeroA, adcMaxA);

            int16_t dacZeroA;
            int16_t dacMaxA;
            calcMinMax(dac01A, dac17A, dacZeroA, dacMaxA);

            Settings::setCurrentCalibration(adcZeroA, adcMaxA, dacZeroA, dacMaxA);

            Settings::save();

            static void (*jump_to_app)(void) = 0x0000;
            jump_to_app();
            break;
    }

    voltageDown = Buttons::isVoltageEncoderPressed();
    currentDown = Buttons::isCurrentEncoderPressed();
    Scheduler::setTimer(calibrate, 10);
}

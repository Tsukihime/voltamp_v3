#ifndef MAINSCREEN_H_
#define MAINSCREEN_H_

#include <stdint.h>

enum AdjustmentLevel {COARSE, FINE, LOCK, END};

class MainScreen {
    private:
        static void DrawBorders();
        static void DrawDots();
    public:
        static void drawBackground();
        static void setVoltage(int16_t voltage);
        static void setCurrent(int16_t current);
        static void setPower(int32_t power);
        static void setEnergy(int32_t energy);
        static void setVoltageLimit(int16_t voltageLimit);
        static void setCurrentLimit(int16_t currentLimit);
        static void setAdjustmentLevel(AdjustmentLevel voltage, AdjustmentLevel current);
        static void drawString(const char* string, uint8_t x, uint8_t y, uint16_t FgColor, uint16_t BgColor);
};

#endif /* MAINSCREEN_H_ */

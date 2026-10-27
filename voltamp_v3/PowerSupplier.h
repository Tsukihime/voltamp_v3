#ifndef POWERSUPPLIER_H_
#define POWERSUPPLIER_H_

#include <stdint.h>

class PowerSupplier {
    private:
        static uint16_t voltage_mv;
        static uint16_t current_ma;
        static int16_t current_correction_ma;
        static int16_t voltage_correction_mv;
        static uint16_t voltageDacValue;
        static uint16_t currentDacValue;
        static bool enabled;
        static void setDacValues();
    public:
        static void initialize(void);
        static void setVoltage(uint16_t voltage_mv);
        static void setCurrent(uint16_t current_ma);
        static void setCurrentCorrection(int16_t correction_ma);
        static void setVoltageCorrection(int16_t correction_mv);
        static uint16_t getVoltage();
        static uint16_t getCurrent();
        static int16_t getCurrentCorrection();
        static int16_t getVoltageCorrection();
        static uint16_t getRawVoltage();
        static uint16_t getRawCurrent();
        static void enable();
        static void disable();
};

#endif /* POWERSUPPLIER_H_ */

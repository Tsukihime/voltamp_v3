#ifndef CALIBRATOR_H_
#define CALIBRATOR_H_

#include "screen/MainScreen.h"

class Settings {
    public:
    static void initialize();
    static void save();
    static int16_t normalizeMultimeterVoltage(uint16_t voltage);
    static int16_t normalizeMultimeterCurrent(uint16_t current);
    static int16_t normalizePowerSupplierVoltage(uint16_t voltage);
    static int16_t normalizePowerSupplierCurrent(uint16_t current);

    static uint16_t getCurrent();
    static void setCurrent(uint16_t current);
    static uint16_t getVoltage();
    static void setVoltage(uint16_t voltage);
    static AdjustmentLevel getCurrentAdjustment();
    static void setCurrentAdjustment(AdjustmentLevel currentAdjustment);
    static AdjustmentLevel getVoltageAdjustment();
    static void setVoltageAdjustment(AdjustmentLevel voltageAdjustment);

    static void setVoltageCalibration(int16_t adc_vzero, int16_t adc_vmax, int16_t dac_vzero, int16_t dac_vmax);
    static void setCurrentCalibration(int16_t adc_azero, int16_t adc_amax, int16_t dac_azero, int16_t dac_amax);
};

#endif /* CALIBRATOR_H_ */

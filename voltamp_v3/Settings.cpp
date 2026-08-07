#include <avr/eeprom.h>

#include "Settings.h"

const uint16_t MAGIC = 0xC0DE + 1;

struct CalibrationData {
    uint16_t sign;
    struct {
        uint16_t VZero;
        uint16_t AZero;
        uint16_t VMax;
        uint16_t AMax;
    } PowerSupplier;
    struct {
        int16_t VZero;
        int16_t AZero;
        int16_t VMax;
        int16_t AMax;
    } Multimeter;
    struct {
        uint16_t voltage;
        uint16_t current;
        AdjustmentLevel currentAdjustment;
        AdjustmentLevel voltageAdjustment;
    } State;
} calibrationData;

void Settings::initialize() {
    eeprom_read_block(&calibrationData, nullptr, sizeof(CalibrationData));
    if(calibrationData.sign == MAGIC) {
        return;
    }
    calibrationData.sign = MAGIC;
    calibrationData.Multimeter.AZero = 240;
    calibrationData.Multimeter.AMax = 31776;
    calibrationData.Multimeter.VZero = -5;
    calibrationData.Multimeter.VMax = 30662;
    calibrationData.PowerSupplier.AZero = 15;
    calibrationData.PowerSupplier.AMax = 4030;
    calibrationData.PowerSupplier.VZero = 9;
    calibrationData.PowerSupplier.VMax = 3853;
    calibrationData.State.current = 200;
    calibrationData.State.voltage = 1000;
    calibrationData.State.currentAdjustment = AdjustmentLevel::COARSE;
    calibrationData.State.voltageAdjustment = AdjustmentLevel::COARSE;
}

void Settings::save() {
    eeprom_update_block(&calibrationData, nullptr, sizeof(CalibrationData));
}

int16_t remap(int16_t value, int16_t oldMin, int16_t oldMax, int16_t newMin, int16_t newMax) {
    uint16_t oldRange = oldMax - oldMin;
    uint16_t newRange = newMax - newMin;
    return (static_cast<int32_t>(value - oldMin) * newRange) / oldRange + newMin;
}

int16_t Settings::normalizeMultimeterVoltage(uint16_t voltage) {
    return remap(voltage, calibrationData.Multimeter.VZero, calibrationData.Multimeter.VMax, 0, 30000);
}

int16_t Settings::normalizeMultimeterCurrent(uint16_t current) {
    return remap(current, calibrationData.Multimeter.AZero, calibrationData.Multimeter.AMax, 0, 3000);
}

int16_t Settings::normalizePowerSupplierVoltage(uint16_t voltage) {
    return remap(voltage, 0, 30000, calibrationData.PowerSupplier.VZero, calibrationData.PowerSupplier.VMax);
}

int16_t Settings::normalizePowerSupplierCurrent(uint16_t current) {
    return remap(current, 0, 3000, calibrationData.PowerSupplier.AZero, calibrationData.PowerSupplier.AMax);
}

uint16_t Settings::getCurrent() {
    return calibrationData.State.current;
}

void Settings::setCurrent(uint16_t current) {
    calibrationData.State.current = current;
}

uint16_t Settings::getVoltage() {
    return calibrationData.State.voltage;
}

void Settings::setVoltage(uint16_t voltage) {
    calibrationData.State.voltage = voltage;
}

AdjustmentLevel Settings::getCurrentAdjustment() {
    return calibrationData.State.currentAdjustment;
}

void Settings::setCurrentAdjustment(AdjustmentLevel currentAdjustment) {
    calibrationData.State.currentAdjustment = currentAdjustment;
}

AdjustmentLevel Settings::getVoltageAdjustment() {
    return calibrationData.State.voltageAdjustment;
}

void Settings::setVoltageAdjustment(AdjustmentLevel voltageAdjustment) {
    calibrationData.State.voltageAdjustment = voltageAdjustment;
}

void Settings::setVoltageCalibration(int16_t adc_vzero, int16_t adc_vmax, int16_t dac_vzero, int16_t dac_vmax) {
    calibrationData.Multimeter.VZero = adc_vzero;
    calibrationData.Multimeter.VMax = adc_vmax;
    calibrationData.PowerSupplier.VZero = dac_vzero;
    calibrationData.PowerSupplier.VMax = dac_vmax;
}

void Settings::setCurrentCalibration(int16_t adc_azero, int16_t adc_amax, int16_t dac_azero, int16_t dac_amax) {
    calibrationData.Multimeter.AZero = adc_azero;
    calibrationData.Multimeter.AMax = adc_amax;
    calibrationData.PowerSupplier.AZero = dac_azero;
    calibrationData.PowerSupplier.AMax = dac_amax;
}

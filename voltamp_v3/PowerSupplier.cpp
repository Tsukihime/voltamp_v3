#include "PowerSupplier.h"

#include "VoltageSelector.h"
#include "Dac.h"
#include "Settings.h"
#include "lib/AVRPin.hpp"
#include "Bluetooth.h"

uint16_t PowerSupplier::voltage_mv = 0;
uint16_t PowerSupplier::current_ma = 0;
int16_t PowerSupplier::current_correction_ma = 0;
int16_t PowerSupplier::voltage_correction_mv = 0;
uint16_t PowerSupplier::voltageDacValue;
uint16_t PowerSupplier::currentDacValue;

using OUT_EN = Pc3;

bool PowerSupplier::enabled;

void PowerSupplier::initialize() {
    OUT_EN::SetDirWrite();
    OUT_EN::Clear();
    Dac::initialize();
    Dac::setValues(0, 0);
}

void PowerSupplier::enable() {
    if(enabled) {
        return;
    }
    OUT_EN::Set();
    enabled = true;
    setDacValues();
}

void PowerSupplier::disable() {
    if(!enabled) {
        return;
    }
    OUT_EN::Clear();
    enabled = false;
    Dac::setValues(0, 0);
    VoltageSelector::setVoltageLevel(0);
}

void PowerSupplier::setDacValues() {
    if(!enabled) {
        return;
    }

    if(voltage_mv <= 7500) {
        VoltageSelector::setVoltageLevel(0);
    } else if(voltage_mv <= 15000) {
        VoltageSelector::setVoltageLevel(1);
    } else if(voltage_mv <= 22500) {
        VoltageSelector::setVoltageLevel(2);
    } else {
        VoltageSelector::setVoltageLevel(3);
    }

    voltageDacValue = Settings::normalizePowerSupplierVoltage(voltage_mv + voltage_correction_mv);
    currentDacValue = Settings::normalizePowerSupplierCurrent(current_ma + current_correction_ma);

    Dac::setValues(voltageDacValue, currentDacValue);
}

uint16_t PowerSupplier::getRawVoltage() {
    return voltageDacValue;
}

uint16_t PowerSupplier::getRawCurrent() {
    return currentDacValue;
}

void PowerSupplier::setVoltage(uint16_t voltage_mv) {
    PowerSupplier::voltage_mv = voltage_mv;
    setDacValues();
}

void PowerSupplier::setCurrent(uint16_t current_ma) {
    PowerSupplier::current_ma = current_ma;
    setDacValues();
}

void PowerSupplier::setCurrentCorrection(int16_t correction_ma) {
    current_correction_ma = correction_ma;
    setDacValues();
}

void PowerSupplier::setVoltageCorrection(int16_t correction_mv) {
    voltage_correction_mv = correction_mv;
    setDacValues();
}

uint16_t PowerSupplier::getVoltage() {
    return voltage_mv;
}

uint16_t PowerSupplier::getCurrent() {
    return current_ma;
}

int16_t PowerSupplier::getCurrentCorrection() {
    return current_correction_ma;
}

int16_t PowerSupplier::getVoltageCorrection() {
    return voltage_correction_mv;
}

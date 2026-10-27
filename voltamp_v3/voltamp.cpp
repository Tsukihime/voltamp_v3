#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/power.h>
#include <stdlib.h>

#include "utils.h"
#include "Bluetooth.h"
#include "Buttons.h"
#include "VoltageSelector.h"
#include "PowerSupplier.h"
#include "Multimeter.h"
#include "lib/Scheduler.h"
#include "Timer2.h"
#include "ST7735Lcd.h"
#include "screen/MainScreen.h"
#include "Settings.h"
#include "calibration.h"

extern "C" {
    #include "lib/i2cmaster.h"
}

uint32_t energyMicroWattHour = 0;
void updateEnergyCounter() {
    int32_t voltage = Multimeter::getVoltage();
    int32_t current = Multimeter::getCurrent();
    voltage = voltage < 0 ? 0 : voltage;
    current = current < 0 ? 0 : current;
    energyMicroWattHour += (voltage * current) / 3600;
}

static AdjustmentLevel voltageAdjustment = AdjustmentLevel::COARSE;
static AdjustmentLevel currentAdjustment = AdjustmentLevel::COARSE;

void updateState() {
    static bool firstrun = true;
    if(firstrun) {
        MainScreen::drawBackground();
        firstrun = false;
    }

    bool cc = Buttons::isConstantCurrentMode();
    VoltageSelector::setCCLedState(cc);
    VoltageSelector::setCVLedState(!cc);

    if(Buttons::isOutputSwitchOn()) {
        PowerSupplier::enable();
    } else {
        PowerSupplier::disable();
    }

    Multimeter::updateValues();

    int32_t voltage = Multimeter::getVoltage();
    int32_t current = Multimeter::getCurrent();
    int32_t power = voltage * current / 1000;
	int32_t energyMilliWattHour = energyMicroWattHour / 1000;
    
    MainScreen::setAdjustmentLevel(voltageAdjustment, currentAdjustment);
    MainScreen::setVoltage(voltage);
    MainScreen::setCurrent(current);
    MainScreen::setPower(power);
    MainScreen::setEnergy(energyMilliWattHour);
    MainScreen::setVoltageLimit(PowerSupplier::getVoltage());
    MainScreen::setCurrentLimit(PowerSupplier::getCurrent());

    Scheduler::setTimer(updateState, 8);
}

void correctOutput() {
    bool cc = Buttons::isConstantCurrentMode();

    if (!cc) {
        // Disable current correction outside CC mode.
        // The op-amp temperature and its resulting input offset drift
        // are unknown, so applying a correction could increase the error.
        PowerSupplier::setCurrentCorrection(0);

        // Compensate for the difference between the measured output voltage
        // and the voltage setpoint, accounting for the existing correction.
        int16_t voltage = Multimeter::getVoltage();
        int16_t voltageLimit = PowerSupplier::getVoltage();
        int16_t error = voltageLimit - voltage;
        
        // Ignore deviations within +/-1 mV to prevent DAC hunting.
        if (abs(error) <= 1) return;
        
        int16_t correction = error + PowerSupplier::getVoltageCorrection();
        
        // Limit the total voltage correction to +/-100 mV.
        correction = clamp(correction, -100, 100);

        PowerSupplier::setVoltageCorrection(correction);
    } else {
        // Disable voltage correction while operating in CC mode.
        PowerSupplier::setVoltageCorrection(0);

        // In CC mode, the difference between the measured current and
        // the setpoint is used to compensate for thermal offset drift.
        // This function runs every 2 seconds to reduce oscillations.
        int16_t current = Multimeter::getCurrent();
        int16_t currentLimit = PowerSupplier::getCurrent();
        int16_t error = currentLimit - current;
        
        // Ignore deviations within +/-1 mA to prevent DAC hunting.
        if (abs(error) <= 1) return;
        
        int16_t correction = error + PowerSupplier::getCurrentCorrection();
        // Limit the total current correction to +/-100 mA.
        correction = clamp(correction, -100, 100);

        PowerSupplier::setCurrentCorrection(correction);
    }
}

void updateEncoderButtons() {
    static bool voltageDown = false;
    static bool currentDown = false;

    if(voltageDown & !Buttons::isVoltageEncoderPressed()) { // voltage click
        voltageAdjustment = (AdjustmentLevel)(voltageAdjustment + 1);
        if(voltageAdjustment >= AdjustmentLevel::END) {
            voltageAdjustment = AdjustmentLevel::COARSE;
        }
        Settings::setVoltageAdjustment(voltageAdjustment);
    }

    if(currentDown & !Buttons::isCurrentEncoderPressed()) { // current click
        currentAdjustment = (AdjustmentLevel)(currentAdjustment + 1);
        if(currentAdjustment >= AdjustmentLevel::END) {
            currentAdjustment = AdjustmentLevel::COARSE;
        }
        Settings::setCurrentAdjustment(currentAdjustment);
    }

    voltageDown = Buttons::isVoltageEncoderPressed();
    currentDown = Buttons::isCurrentEncoderPressed();
}

void updateEncoders() {
    updateEncoderButtons();
    int8_t voltage_clicks = Buttons::voltageEncoderPopDelta();
    int8_t current_clicks = Buttons::currentEncoderPopDelta();

    if(voltage_clicks == 0 && current_clicks == 0) {
        return;
    }

    const uint8_t DV[3] = {200, 10, 0};
    const uint8_t DA[3] = {100, 1, 0};

    int32_t voltage_delta = voltage_clicks * DV[voltageAdjustment]; // mv per click
    int32_t current_delta = current_clicks * DA[currentAdjustment]; // ma per click
    
    int32_t new_voltage = PowerSupplier::getVoltage() + voltage_delta;
    int32_t new_current = PowerSupplier::getCurrent() + current_delta;

    new_voltage = clamp(new_voltage, 0L, 30000L);
    new_current = clamp(new_current, 0L, 3000L);

    PowerSupplier::setCurrent(new_current);
    PowerSupplier::setVoltage(new_voltage);
    Settings::setCurrent(new_current);
    Settings::setVoltage(new_voltage);
}

void updateSettings() {
    Settings::save();
}

void initI2cDev() {
    const uint8_t I2C_RESET = 0x06;
    const uint8_t GENERAL_CALL_ADDR = 0x00;
    i2c_init();
    i2c_start(I2C_WRITE + GENERAL_CALL_ADDR);
    i2c_write(I2C_RESET);
    i2c_stop();
}

void initAll() {
    initI2cDev();
    Bluetooth::initialize();
    Buttons::initialize();
    VoltageSelector::initialize();
    PowerSupplier::initialize();
    Settings::initialize();
    ST7735Lcd::initialize();
    Timer2::initialize();
    VoltageSelector::setBluetoothATState(false);
    sei();
}

int main(void) {
    initAll();
    
    if(Buttons::isCurrentEncoderPressed() && Buttons::isOutputSwitchOn()) {
        Scheduler::setTimer(calibrate, 1);
    } else {
        Scheduler::setTimer(updateEnergyCounter, 100, true);
        Scheduler::setTimer(updateEncoders, 10, true);
        Scheduler::setTimer(updateState, 1);
        Scheduler::setTimer(updateSettings, 1000, true);
        Scheduler::setTimer(correctOutput, 200, true);

        PowerSupplier::setCurrent(Settings::getCurrent());
        PowerSupplier::setVoltage(Settings::getVoltage());
        currentAdjustment = Settings::getCurrentAdjustment();
        voltageAdjustment = Settings::getVoltageAdjustment();
    }

    Timer2::poolTasksRun();
}

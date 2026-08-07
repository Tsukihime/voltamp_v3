#include <avr/io.h>
#include <avr/sleep.h>
#include <avr/interrupt.h>
#include <util/delay.h>

#include "Multimeter.h"
#include "utils.h"
#include "Settings.h"

extern "C" {
    #include "lib/ads1115.h"
}

const uint8_t VOLTAGE_CH = 0;
const uint8_t CURRENT_CH = 1;

int16_t voltage;
int16_t current;

void Multimeter::updateValues() {
    voltage = ads1115_readADC_SingleEnded(ADS1115_ADDR_GND, VOLTAGE_CH, DATARATE_128SPS, FSR_2_048);
    current = ads1115_readADC_SingleEnded(ADS1115_ADDR_GND, CURRENT_CH, DATARATE_128SPS, FSR_2_048);
}

int16_t Multimeter::getRawVoltage() {
    return voltage;
}

int16_t Multimeter::getVoltage() {
   return Settings::normalizeMultimeterVoltage(voltage);
}

int16_t Multimeter::getRawCurrent() {
    return current;
}

int16_t Multimeter::getCurrent() {
    return Settings::normalizeMultimeterCurrent(current);
}

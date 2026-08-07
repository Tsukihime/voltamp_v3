#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>

#include "Dac.h"
#include "lib/AVRPin.hpp"

extern "C" {
    #include "lib/i2cmaster.h"
}

const uint8_t MCP4725_BASEADDRESS = 0xC0; //device base address
const uint8_t MCP4725_WRITEDACEEPROM = 0x60;
const uint8_t MCP4725_WRITEDAC = 0x40;

const uint8_t CURRENT_ADDR = 0x00;
const uint8_t VOLTAGE_ADDR = 0x02;

bool MCP4725_ready(uint8_t AddressA0) {
    i2c_start(I2C_READ + MCP4725_BASEADDRESS + AddressA0);
    uint8_t status = i2c_readNak();
    i2c_stop();
    return ((status & 0x80) > 0);
}

uint16_t MCP4725_ReadEEPROM(uint8_t AddressA0) {
    while(!MCP4725_ready(AddressA0));
    i2c_start(I2C_READ + MCP4725_BASEADDRESS + AddressA0);
    i2c_readAck();
    uint16_t b1 = i2c_readAck();
    uint8_t b2 = i2c_readNak();
    i2c_stop();
    return (b1 << 4) | (b2 >> 4);
}

void MCP4725_WriteEEPROM(uint8_t AddressA0, uint16_t value) {
    i2c_start_wait(I2C_WRITE + MCP4725_BASEADDRESS + AddressA0);
    i2c_write(MCP4725_WRITEDACEEPROM);
    i2c_write(value >> 4);
    i2c_write(value << 4);
    i2c_stop();
}


void MCP4725_init(uint8_t AddressA0) {
    if(MCP4725_ReadEEPROM(AddressA0) != 0) {
        MCP4725_WriteEEPROM(AddressA0, 0);
    }
}

void MCP4725_setValue(uint8_t AddressA0, uint16_t value) {
    while(!MCP4725_ready(AddressA0));
    i2c_start(I2C_WRITE + MCP4725_BASEADDRESS + AddressA0);
    i2c_write(MCP4725_WRITEDAC);
	i2c_write(value >> 4);
	i2c_write(value << 4);
	i2c_stop();
}

void Dac::initialize(void) {
    MCP4725_init(VOLTAGE_ADDR);
    MCP4725_init(CURRENT_ADDR);
}

void Dac::setValues(uint16_t voltage_ch, uint16_t current_ch) {
    MCP4725_setValue(VOLTAGE_ADDR, voltage_ch);
    MCP4725_setValue(CURRENT_ADDR, current_ch);
}

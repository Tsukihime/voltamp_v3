#include "ScpiParser.h"
#include "Bluetooth.h"
#include "PowerSupplier.h"
#include "Multimeter.h"
#include "Buttons.h"
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

char ScpiParser::rxBuffer[32];
uint8_t ScpiParser::rxIndex = 0;

extern uint32_t energyMicroWattHour;

void ScpiParser::handleByte(uint8_t byte) {
    if (byte == '\r' || byte == '\n') {
        if (rxIndex > 0) {
            rxBuffer[rxIndex] = '\0';
            processCommand(rxBuffer);
            rxIndex = 0;
        }
    } else if (rxIndex < sizeof(rxBuffer) - 1) {
        rxBuffer[rxIndex++] = toupper(byte);
    }
}

bool ScpiParser::compareCmd(const char* input, const char* shortForm, const char* longForm) {
    return (strcmp(input, shortForm) == 0) || (strcmp(input, longForm) == 0);
}

void missingParameterError() {
    Bluetooth::sendString("ERR: -109, \"Missing parameter\"\n");
}

void ScpiParser::processCommand(char* cmd) {
    char* arg = strchr(cmd, ' ');
    if (arg != nullptr) {
        *arg = '\0';
        arg++;
    }

    char responseBuffer[16];

    // --- MANDATORY IEEE 488.2 COMMANDS ---
    if (strcmp(cmd, "*IDN?") == 0) {
        Bluetooth::sendString("Tsukihime,LabPS-303,SN001,v1.0\n");
        return;
    }
    
    if (strcmp(cmd, "*RST") == 0) {
        PowerSupplier::disable();
        PowerSupplier::setVoltage(0);
        PowerSupplier::setCurrent(0);
        energyMicroWattHour = 0;
        return;
    }
    
    if (strcmp(cmd, "*CLS") == 0) {
        // Clear status/error flags logic goes here
        return;
    }
    
    // --- SOURCE SECTION ---
    if (compareCmd(cmd, "SOUR:VOLT", "SOURCE:VOLTAGE")) {
        if (arg != nullptr) {
            uint16_t mv = strtoul(arg, nullptr, 10);
            PowerSupplier::setVoltage(mv);
        } else {
            missingParameterError();
        }
        return;
    }
    
    if (compareCmd(cmd, "SOUR:VOLT?", "SOURCE:VOLTAGE?")) {
        utoa(PowerSupplier::getVoltage(), responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "SOUR:VOLT:RAW?", "SOURCE:VOLTAGE:RAW?")) {
        utoa(PowerSupplier::getRawVoltage(), responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "SOUR:CURR", "SOURCE:CURRENT")) {
        if (arg != nullptr) {
            uint16_t ma = strtoul(arg, nullptr, 10);
            PowerSupplier::setCurrent(ma);
        } else {
            missingParameterError();
        }
        return;
    }
    
    if (compareCmd(cmd, "SOUR:CURR?", "SOURCE:CURRENT?")) {
        utoa(PowerSupplier::getCurrent(), responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "SOUR:CURR:RAW?", "SOURCE:CURRENT:RAW?")) {
        utoa(PowerSupplier::getRawCurrent(), responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }    
    
    if (compareCmd(cmd, "OUTP", "OUTPUT")) {
        if (arg != nullptr) {
            if (strcmp(arg, "1") == 0 || strcmp(arg, "ON") == 0) {
                PowerSupplier::enable();
            } else if (strcmp(arg, "0") == 0 || strcmp(arg, "OFF") == 0) {
                PowerSupplier::disable();
            }
        } else {
            missingParameterError();
        }
        return;
    }
    
    if (compareCmd(cmd, "OUTP?", "OUTPUT?")) {
        utoa(Buttons::isOutputSwitchOn() ? 1 : 0, responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    // --- MEASURE SECTION ---
    if (compareCmd(cmd, "MEAS:VOLT?", "MEASURE:VOLTAGE?")) {
        itoa(Multimeter::getVoltage(), responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:VOLT:RAW?", "MEASURE:VOLTAGE:RAW?")) {
        itoa(Multimeter::getRawVoltage(), responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:CURR?", "MEASURE:CURRENT?")) {
        itoa(Multimeter::getCurrent(), responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:CURR:RAW?", "MEASURE:CURRENT:RAW?")) {
        itoa(Multimeter::getRawCurrent(), responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:POW?", "MEASURE:POWER?")) {
        int32_t mw = (int32_t)Multimeter::getVoltage() * Multimeter::getCurrent() / 1000;
        ltoa(mw, responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:ENER?", "MEASURE:ENERGY?")) {
        int32_t mwh = energyMicroWattHour / 1000;        
        ltoa(mwh, responseBuffer, 10);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\n");
        return;
    }
    
    if (compareCmd(cmd, "SOUR:ENER:RES", "SOURCE:ENERGY:RESET")) {
        energyMicroWattHour = 0;
        return;
    }
    
    // Query operation mode (CC or CV)
    if (compareCmd(cmd, "MEAS:MODE?", "MEASURE:MODE?")) {
        if (Buttons::isConstantCurrentMode()) {
            Bluetooth::sendString("CC\n");
        } else {
            Bluetooth::sendString("CV\n");
        }
        return;
    }

    // --- ERROR HANDLING ---
    // Executed only if no previous matching condition triggered a return
    Bluetooth::sendString("ERR: -113, \"Undefined header\"\n");
}

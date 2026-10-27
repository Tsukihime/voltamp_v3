#include "ScpiParser.h"
#include "PowerSupplier.h"
#include "Multimeter.h"
#include "Buttons.h"
#include "lib/Scheduler.h"
#include "utils.h"
#include <util/atomic.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

char ScpiParser::rxBuffer[32];
uint8_t ScpiParser::rxIndex = 0;
bool ScpiParser::isProcessing = false;
RingBuffer<UART_BUFFER_SIZE> ScpiParser::recievedBuffer;
RingBuffer<SCPI_ERROR_BUFFER_SIZE, int16_t> ScpiParser::errorQueue;

extern uint32_t energyMicroWattHour;

void ScpiParser::reportError(int16_t code) {    
    if (!errorQueue.push(code)) {
        int16_t dummy;
        errorQueue.pop(dummy);
        errorQueue.push(ScpiErrorCodes::QUEUE_OVERFLOW);
    }
}

void ScpiParser::ISRReceivedByte(uint8_t byte) {    
    bool push_success = recievedBuffer.push(byte);
    
    if (!push_success) {
        Scheduler::setTask([](){reportError(ScpiErrorCodes::QUEUE_OVERFLOW);});
        return;
    }
    
    if(!isProcessing) {
        isProcessing = true;
        Scheduler::setTask(onBufferUpdated);
    }
}

void ScpiParser::onBufferUpdated() {
    uint8_t byte;
    
    while (true) {
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
            if (!recievedBuffer.pop(byte)) {
                isProcessing = false;
                return;
            } 
        }

        if (byte == '\r' || byte == '\n' || byte == ';') {
            if (rxIndex > 0) {
                rxBuffer[rxIndex] = '\0';
                processCommand(rxBuffer);
                rxIndex = 0;
            }
        } else if (rxIndex < sizeof(rxBuffer) - 1) {
            if (rxIndex == 0 && byte == ' ') {
                // skip start spaces
            } else {
                rxBuffer[rxIndex++] = toupper(byte);
            }
        } else {
            rxIndex = 0;
            return reportError(ScpiErrorCodes::MESSAGE_TOO_LONG);
        }
    }
}

bool ScpiParser::compareCmd(const char* input, const char* shortForm, const char* longForm) {
    return (strcmp(input, shortForm) == 0) || (strcmp(input, longForm) == 0);
}

bool is_scpi_number(const char *s) {
    if (!s || !*s) return false;

    while (*s) {
        char c = *s++;
        
        if (!((c >= '0' && c <= '9') || c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-')) {
            return false;
        }
    }
    return true;
}

void ScpiParser::processCommand(char* cmd) {
    char* arg = strchr(cmd, ' ');
    if (arg != nullptr) {
        *arg = '\0';
        arg++;
                
        while (*arg == ' ') arg++;
        if (*arg == '\0') arg = nullptr;
    }

    char responseBuffer[16];

    // --- MANDATORY IEEE 488.2 COMMANDS ---
    if (strcmp(cmd, "*IDN?") == 0) {
        Bluetooth::sendString("Tsukihime,LabPS-303,SN001,v1.0\r\n");
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
        errorQueue.clear();
        return;
    }
            
    if (strcmp(cmd, "*OPC") == 0) {
        return;
    }
    
    if (strcmp(cmd, "*OPC?") == 0) {
        Bluetooth::sendString("1\r\n");
        return;
    }

    if (compareCmd(cmd, "SYST:ERR?", "SYSTEM:ERROR?")) {
        int16_t err;         
        if (errorQueue.pop(err)) {
            switch (err) {
                case ScpiErrorCodes::SYNTAX_ERROR:
                    Bluetooth::sendString("-102,\"Syntax error\"");
                    break;
                 
                case ScpiErrorCodes::MISSING_PARAMETER:
                    Bluetooth::sendString("-109,\"Missing parameter\"");
                    break;
                 
                case ScpiErrorCodes::PARAM_NOT_ALLOWED:
                    Bluetooth::sendString("-108,\"Parameter not allowed\"");
                    break;
                 
                case ScpiErrorCodes::UNDEFINED_HEADER:
                    Bluetooth::sendString("-113,\"Undefined header\"");
                    break;
                 
                case ScpiErrorCodes::DATA_OUT_OF_RANGE:
                    Bluetooth::sendString("-222,\"Data out of range\"");
                    break;
                     
                case ScpiErrorCodes::MESSAGE_TOO_LONG:
                    Bluetooth::sendString("-256,\"Program message too long\"");
                    break;
                    
                case ScpiErrorCodes::QUEUE_OVERFLOW:
                    Bluetooth::sendString("-350,\"Queue overflow\"");
                    break;
                 
                default:
                    Bluetooth::sendString("-999,\"Undefined error\"");
                    break;
            }
            Bluetooth::sendString("\r\n");
        } else {
            Bluetooth::sendString("0,\"No error\"\r\n");
        }
        return;
     }
    
    // --- SOURCE SECTION ---
    if (compareCmd(cmd, "SOUR:VOLT", "SOURCE:VOLTAGE")) {
        if (arg != nullptr) {
            if(!is_scpi_number(arg)) {
                return reportError(ScpiErrorCodes::SYNTAX_ERROR);
            }
            int32_t mv = str_to_fixedpoint(arg, 3);
            if(mv < 0 || mv > 30000) {
                return reportError(ScpiErrorCodes::DATA_OUT_OF_RANGE);
            }
            PowerSupplier::setVoltage(mv);
        } else {
            reportError(ScpiErrorCodes::MISSING_PARAMETER);
        }
        return;
    }
    
    if (compareCmd(cmd, "SOUR:VOLT?", "SOURCE:VOLTAGE?")) {
        int32ToStrFixedPoint(PowerSupplier::getVoltage(), responseBuffer, 3);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "SOUR:VOLT:RAW?", "SOURCE:VOLTAGE:RAW?")) {
        int32ToStrFixedPoint(PowerSupplier::getRawVoltage(), responseBuffer);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "SOUR:CURR", "SOURCE:CURRENT")) {
        if (arg != nullptr) {
            if(!is_scpi_number(arg)) {
                return reportError(ScpiErrorCodes::SYNTAX_ERROR);
            }
            int32_t ma = str_to_fixedpoint(arg, 3);
            if(ma < 0 || ma > 3000) {
                return reportError(ScpiErrorCodes::DATA_OUT_OF_RANGE);
            }
            PowerSupplier::setCurrent(ma);
        } else {
            reportError(ScpiErrorCodes::MISSING_PARAMETER);
        }
        return;
    }
    
    if (compareCmd(cmd, "SOUR:CURR?", "SOURCE:CURRENT?")) {
        int32ToStrFixedPoint(PowerSupplier::getCurrent(), responseBuffer, 3);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "SOUR:CURR:RAW?", "SOURCE:CURRENT:RAW?")) {
        int32ToStrFixedPoint(PowerSupplier::getRawCurrent(), responseBuffer);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "OUTP", "OUTPUT")) {
        if (arg != nullptr) {
            if (strcmp(arg, "1") == 0 || strcmp(arg, "ON") == 0) {
                PowerSupplier::enable();
            } else if (strcmp(arg, "0") == 0 || strcmp(arg, "OFF") == 0) {
                PowerSupplier::disable();
            } else {
                reportError(ScpiErrorCodes::PARAM_NOT_ALLOWED);
            }
        } else {
            reportError(ScpiErrorCodes::MISSING_PARAMETER);
        }
        return;
    }
    
    if (compareCmd(cmd, "OUTP?", "OUTPUT?")) {
        if(Buttons::isOutputSwitchOn()) {
            Bluetooth::sendString("1\r\n");
        } else {
            Bluetooth::sendString("0\r\n");
        }
        return;
    }
    
    // --- MEASURE SECTION ---
    if (compareCmd(cmd, "MEAS:VOLT?", "MEASURE:VOLTAGE?")) {
        int32ToStrFixedPoint(Multimeter::getVoltage(), responseBuffer, 3);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:VOLT:RAW?", "MEASURE:VOLTAGE:RAW?")) {
        int32ToStrFixedPoint(Multimeter::getRawVoltage(), responseBuffer);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:CURR?", "MEASURE:CURRENT?")) {
        int32ToStrFixedPoint(Multimeter::getCurrent(), responseBuffer, 3);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:CURR:RAW?", "MEASURE:CURRENT:RAW?")) {
        int32ToStrFixedPoint(Multimeter::getRawCurrent(), responseBuffer);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:POW?", "MEASURE:POWER?")) {
        int32_t mw = (int32_t)Multimeter::getVoltage() * Multimeter::getCurrent() / 1000;
        int32ToStrFixedPoint(mw, responseBuffer, 3);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "MEAS:ENER?", "MEASURE:ENERGY?")) {
        int32_t mwh = energyMicroWattHour / 1000;
        int32ToStrFixedPoint(mwh, responseBuffer, 3);
        Bluetooth::sendString(responseBuffer);
        Bluetooth::sendString("\r\n");
        return;
    }
    
    if (compareCmd(cmd, "SOUR:ENER:RES", "SOURCE:ENERGY:RESET")) {
        energyMicroWattHour = 0;
        return;
    }

    // Query operation mode (CC or CV)
    if (compareCmd(cmd, "MEAS:MODE?", "MEASURE:MODE?")) {
        if (Buttons::isConstantCurrentMode()) {
            Bluetooth::sendString("CC\r\n");
        } else {
            Bluetooth::sendString("CV\r\n");
        }
        return;
    }

    // --- ERROR HANDLING ---
    reportError(ScpiErrorCodes::UNDEFINED_HEADER);
}

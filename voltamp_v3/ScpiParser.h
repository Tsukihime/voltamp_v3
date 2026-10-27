#ifndef SCPIPARSER_H_
#define SCPIPARSER_H_

#include <stdint.h>
#include "Bluetooth.h"

constexpr uint8_t SCPI_ERROR_BUFFER_SIZE = 20;

namespace ScpiErrorCodes {
    constexpr int16_t NO_ERROR          = 0;
    constexpr int16_t SYNTAX_ERROR      = -102;
    constexpr int16_t MISSING_PARAMETER = -109;
    constexpr int16_t PARAM_NOT_ALLOWED = -108;
    constexpr int16_t UNDEFINED_HEADER  = -113;
    constexpr int16_t DATA_OUT_OF_RANGE = -222;
    constexpr int16_t MESSAGE_TOO_LONG  = -256;
    constexpr int16_t QUEUE_OVERFLOW    = -350;
}

class ScpiParser {
    private:
        static char rxBuffer[32];
        static uint8_t rxIndex;
        static bool isProcessing;
        static RingBuffer<UART_BUFFER_SIZE> recievedBuffer;
        static RingBuffer<SCPI_ERROR_BUFFER_SIZE, int16_t> errorQueue;
    
        static void onBufferUpdated();
        static void processCommand(char* cmd);
        static bool compareCmd(const char* input, const char* shortForm, const char* longForm);
        static void reportError(int16_t code);
    public:
        static void ISRReceivedByte(uint8_t byte);
};

#endif /* SCPIPARSER_H_ */
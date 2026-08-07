#ifndef SCPIPARSER_H_
#define SCPIPARSER_H_

#include <stdint.h>

class ScpiParser {
    private:
        static char rxBuffer[32];
        static uint8_t rxIndex;
    
        static void processCommand(char* cmd);
        static bool compareCmd(const char* input, const char* shortForm, const char* longForm);
    public:
        static void handleByte(uint8_t byte);
};

#endif /* SCPIPARSER_H_ */
#ifndef BUTTONS_H_
#define BUTTONS_H_

#include <stdint.h>

class Buttons {
    public:
        static void poolISR();
        static void initialize();
        static int8_t voltageEncoderPopDelta();
        static int8_t currentEncoderPopDelta();
        static bool isVoltageEncoderPressed();
        static bool isCurrentEncoderPressed();
        static bool isOutputSwitchOn();
        static bool isConstantCurrentMode();
};

#endif /* BUTTONS_H_ */

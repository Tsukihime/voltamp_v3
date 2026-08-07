#ifndef VOLTAGESELECTOR_H_
#define VOLTAGESELECTOR_H_

#include <stdint.h>

class VoltageSelector {
    public:
        static void initialize();
        static void setBluetoothATState(bool state);
        static void setCVLedState(bool state);
        static void setCCLedState(bool state);
        static void setVoltageLevel(uint8_t level);
};

#endif /* VOLTAGESELECTOR_H_ */

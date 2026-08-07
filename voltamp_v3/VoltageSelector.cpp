#include <avr/io.h>

#include "VoltageSelector.h"
#include "lib\AVRPin.hpp"

using LV3_LED = Pb0;
using LV2_LED = Pa0;
using LV1_LED = Pa1;
using CV_Led = Pd4;
using CC_Led = Pa5;
using BT_EN = Pd3;

void VoltageSelector::initialize() {
    LV3_LED::SetDirWrite();
    LV2_LED::SetDirWrite();
    LV1_LED::SetDirWrite();
    CV_Led::SetDirWrite();
    CC_Led::SetDirWrite();
    BT_EN::SetDirWrite();
}

void VoltageSelector::setBluetoothATState(bool state){
    BT_EN::Set(state);
}

void VoltageSelector::setCVLedState(bool state) {
    CV_Led::Set(state);
}

void VoltageSelector::setCCLedState(bool state) {
    CC_Led::Set(state);
}

void VoltageSelector::setVoltageLevel(uint8_t level) {
    LV3_LED::Clear();
    LV2_LED::Clear();
    LV1_LED::Clear();
    switch(level) {
        case 1:
            LV1_LED::Set();
            break;
        case 2:
            LV2_LED::Set();
            break;
        case 3:
            LV3_LED::Set();
            break;
        case 0: ;
        default: ;
    }
}

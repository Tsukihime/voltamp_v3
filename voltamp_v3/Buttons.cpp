#include <avr/io.h>
#include <util/atomic.h>

#include "lib/AVRPin.hpp"
#include "Buttons.h"
#include "PowerSupplier.h"
#include "Bluetooth.h"

using ENABLEBTN = Pa6;
using ENC1BTN = Pd7;
using ENC2BTN = Pa4;
using CC = Pa7;
using ENC1A = Pd6;
using ENC1B = Pd5;
using ENC2A = Pa2;
using ENC2B = Pa3;

static int16_t encoder1Delta = 0;
static int16_t encoder2Delta = 0;

void Buttons::initialize() {
    CC::SetDirRead();
    ENABLEBTN::SetDirRead();
    ENABLEBTN::Set(); // pullup
    ENC1BTN::SetDirRead();
    ENC1BTN::Set();
    ENC2BTN::SetDirRead();
    ENC2BTN::Set();
    ENC1A::SetDirRead();
    ENC1A::Set();
    ENC1B::SetDirRead();
    ENC1B::Set();
    ENC2A::SetDirRead();
    ENC2A::Set();
    ENC2B::SetDirRead();
    ENC2B::Set();
}

bool Buttons::isVoltageEncoderPressed() {
    return !ENC1BTN::IsSet();
}

bool Buttons::isCurrentEncoderPressed() {
    return !ENC2BTN::IsSet();
}

bool Buttons::isOutputSwitchOn() {
    return !ENABLEBTN::IsSet();
}

bool Buttons::isConstantCurrentMode() {
    return !CC::IsSet();
}

int8_t Buttons::voltageEncoderPopDelta() {
    int8_t result = 0;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        result = encoder1Delta;
        encoder1Delta = 0;
    }
    return result;
}

int8_t Buttons::currentEncoderPopDelta() {
    int8_t result = 0;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        result = encoder2Delta;
        encoder2Delta = 0;
    }
    return result;
}

static constexpr int8_t states[16] = {
     0, 0, 0, 0,
     0, 0, 0,+1,
     0, 0, 0, 0,
     0,-1, 0, 0
};

void Buttons::poolISR() {
    static uint8_t old1State = 0;
    static uint8_t old2State = 0;

    uint8_t enc1State = (!ENC1B::IsSet() << 1) | !ENC1A::IsSet();
    uint8_t index1 = (old1State << 2) | enc1State;
    encoder1Delta += states[index1];
    old1State = enc1State;

    uint8_t enc2State = (!ENC2B::IsSet() << 1) | !ENC2A::IsSet();
    uint8_t index2 = (old2State << 2) | enc2State;
    encoder2Delta += states[index2];
    old2State = enc2State;
}

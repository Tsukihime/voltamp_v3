#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/atomic.h>

#include "Bluetooth.h"
#include "utils.h"
#include "lib/usart0.hpp"
#include "lib/AVRPin.hpp"

using BT_STATE = Pd2;

RingBuffer<UART_SEND_BUFFER_SIZE> Bluetooth::sendBuffer;
volatile bool Bluetooth::transmitActive;

ISR(USART_TXC_vect) {
    Bluetooth::ISRTransmitComplete();
}

inline bool isTransmitAllowed() {
    return BT_STATE::IsSet();
}

void Bluetooth::initialize(void) {
    BT_STATE::SetDirRead();

    Usart0::Init(UART_BAUDRATE, static_cast<Usart0::UsartMode>(
                 Usart0::DataBits8 |
                 Usart0::NoneParity |
                 Usart0::OneStopBit |
                 Usart0::TxEnable)
                 );

    Usart0::EnableInterrupt(Usart0::TxCompleteInt);

    transmitActive = false;
}

inline void Bluetooth::ISRTransmitComplete() {
    uint8_t byte = 0;

    if(!sendBuffer.pop(byte) || !isTransmitAllowed()) {
        transmitActive = false;
        sendBuffer.clear();
        return;
    }

    UDR = byte;
}

void Bluetooth::startTransmit() {
    transmitActive = true;
    ISRTransmitComplete();
}

void Bluetooth::sendChar(const char ch) {
    sendData(&ch, 1);
}

void Bluetooth::sendString(const char* str) {
    sendData(str, strlen(str));
}

void Bluetooth::sendData(const void *data, size_t length) {
    for(size_t i = 0; i < length; /*increment in cycle body*/) {
        if(!isTransmitAllowed()) {
            return;
        }

        bool push_success;
        uint8_t byte = reinterpret_cast<const uint8_t*>(data)[i];

        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
            push_success = sendBuffer.push(byte);
        }
       
        if (push_success) {
            i++;
        }

        if (!transmitActive) {
            startTransmit();
        }
    }
}

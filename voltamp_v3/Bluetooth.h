#ifndef UART_H
#define UART_H

#include <string.h>
#include "lib/RingBuffer.hpp"

const uint32_t UART_BAUDRATE = 9600;
const uint8_t UART_SEND_BUFFER_SIZE = 64;

extern "C" void USART_TXC_vect(void) __attribute__((signal));

class Bluetooth {
    friend void USART_TXC_vect();

    private:
        static RingBuffer<UART_SEND_BUFFER_SIZE> sendBuffer;
        static volatile bool transmitActive;

        static inline void startTransmit();
        static inline void ISRTransmitComplete();

    public:
        static void initialize(void);
        static void sendData(const void *data, size_t length);
        static void sendChar(const char ch);
        static void sendString(const char* str);
};

#endif /* UART_H */

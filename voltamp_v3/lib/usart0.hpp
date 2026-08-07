#ifndef USART_H_
#define USART_H_

#include <stdint.h>
#include <avr/sfr_defs.h>

class Usart0 {
    public:
        enum InterruptFlags {
            NoInterrupt = 0,
            RxNotEmptyInt = _BV(RXCIE),
            TxCompleteInt = _BV(TXCIE),
            TxEmptyInt = _BV(UDRIE),
            AllInterrupts = RxNotEmptyInt | TxCompleteInt | TxEmptyInt
        };

        enum UsartMode { /* 0x UCSRC UCSRB */
            DataBits5 = 0,
            DataBits6 = _BV(UCSZ0) << 8,
            DataBits7 = _BV(UCSZ1) << 8,
            DataBits8 = _BV(UCSZ1) << 8 | _BV(UCSZ0) << 8,
            DataBits9 = _BV(UCSZ2) | _BV(UCSZ1) << 8 | _BV(UCSZ0) << 8,

            NoneParity = 0,
            EvenParity = _BV(UPM1) << 8,
            OddParity = _BV(UPM0) << 8 | _BV(UPM1) << 8,

            Disabled = 0,
            RxEnable = _BV(RXEN),
            TxEnable = _BV(TXEN),
            RxTxEnable = RxEnable | TxEnable,

            OneStopBit = 0,
            HalfStopBit = 0,
            TwoStopBits = _BV(USBS) << 8,
            OneAndHalfStopBits = _BV(USBS) << 8,

            Default = RxTxEnable | DataBits8 | NoneParity | OneStopBit
        };

        enum Error {
            NoError = 0,
            OverrunError = _BV(DOR),
            NoiseError = 0,
            FramingError = _BV(FE),
            ParityError = _BV(/*UPE*/PE),
            ErrorMask = OverrunError | FramingError | ParityError
        };

        static inline void SetBaudRate(uint32_t baund) {
            uint32_t clock = F_CPU;
            uint16_t ubrr = (clock / 16 / baund - 1);
            uint16_t ubrr2x = (clock / 8 / baund - 1);
            uint32_t rbaund = (clock / 16 / (ubrr + 1));
            uint32_t rbaund2x = (clock / 8 / (ubrr2x + 1));

            uint32_t err1;
            if (baund > rbaund) {
                err1 = (baund - rbaund) * 1000 / baund;
                } else {
                err1 = (rbaund - baund) * 1000 / rbaund;
            }

            uint32_t err2;
            if (baund > rbaund2x) {
                err2 = (baund - rbaund2x) * 1000 / baund;
                } else {
                err2 = (rbaund2x - baund) * 1000 / rbaund2x;
            }

            uint16_t ubrrToUse;
            if (err1 > err2) {
                UCSRA |= _BV(U2X);
                ubrrToUse = ubrr2x;
                } else {
                UCSRA &= ~_BV(U2X);
                ubrrToUse = ubrr;
            }
            UBRRL = ubrrToUse & 0xff;
            UBRRH = ubrrToUse >> 8;
        }

        static void DisableTx() {
            UCSRB &= ~_BV(TXEN);
        }

        static void EnableTx() {
            UCSRB |= _BV(TXEN);
        }

        static inline void Init(unsigned long baud, UsartMode usartMode = Default) {
            UCSRC = ((uint8_t)(usartMode >> 8)) | 1 << URSEL;
            UCSRB = ((uint8_t)(usartMode));
            SetBaudRate(baud);
        }

        static void EnableInterrupt(InterruptFlags interruptSources = AllInterrupts) {
            UCSRB |= (uint8_t) interruptSources;
        }

        static void DisableInterrupt(InterruptFlags interruptSources = AllInterrupts) {
            UCSRB &= (uint8_t) ~interruptSources;
        }

        static void Write(uint8_t c) {
            while (!WriteReady())
            ;
            UDR = c;
        }

        static uint8_t Read() {
            while (!ReadReady())
            ;
            return UDR;
        }

        static bool WriteReady() {
            return UCSRA & _BV(UDRE);
        }

        static bool ReadReady() {
            return UCSRA & _BV(RXC);
        }

        static InterruptFlags InterruptSource() {
            uint8_t result = NoInterrupt;
            if (UCSRA & _BV(RXC)) {
                result |= RxNotEmptyInt;
            }
            if (UCSRA & _BV(UDRE)) {
                result |= TxEmptyInt;
            }
            if (UCSRA & _BV(TXC)) {
                result |= TxCompleteInt;
            }
            return (InterruptFlags)result;
        }

        static Error GetError() {
            return (Error)(UCSRA & ErrorMask);
        }
};

#endif /* USART_H_ */
#ifndef AVRPIN_H_
#define AVRPIN_H_

#include <avr/io.h>

#define MAKE_PORT(portName, ddrName, pinName, className) \
class className{\
    public:\
    typedef uint8_t DataT;\
    private:\
    static volatile DataT &data()\
    {\
        return portName;\
    }\
    static volatile DataT &dir()\
    {\
        return ddrName;\
    }\
    static volatile DataT &pin()\
    {\
        return pinName;\
    }\
    public:\
    static void Write(DataT value)\
    {\
        data() = value;\
    }\
    static void ClearAndSet(DataT clearMask, DataT value)\
    {\
        data() = (data() & ~clearMask) | value;\
    }\
    static DataT Read()\
    {\
        return data();\
    }\
    static void DirWrite(DataT value)\
    {\
        dir() = value;\
    }\
    static DataT DirRead()\
    {\
        return dir();\
    }\
    static void Set(DataT value)\
    {\
        data() |= value;\
    }\
    static void Clear(DataT value)\
    {\
        data() &= ~value;\
    }\
    static void Togle(DataT value)\
    {\
        data() ^= value;\
    }\
    static void DirSet(DataT value)\
    {\
        dir() |= value;\
    }\
    static void DirClear(DataT value)\
    {\
        dir() &= ~value;\
    }\
    static void DirTogle(DataT value)\
    {\
        dir() ^= value;\
    }\
    static DataT PinRead()\
    {\
        return pin();\
    }\
    enum{Width=sizeof(DataT)*8};\
};

template <class PORT, uint8_t PIN>
class TPin {
    public:
    typedef PORT Port;
    enum {
        Number = PIN
    };

    static void Set() {
        PORT::Set(1 << PIN);
    }

    static void Set(uint8_t val) {
        if (val)
        Set();
        else Clear();
    }

    static void SetDir(uint8_t val) {
        if (val)
        SetDirWrite();
        else SetDirRead();
    }

    static void Clear() {
        PORT::Clear(1 << PIN);
    }

    static void Togle() {
        PORT::Togle(1 << PIN);
    }

    static void SetDirRead() {
        PORT::DirClear(1 << PIN);
    }

    static void SetDirWrite() {
        PORT::DirSet(1 << PIN);
    }

    static uint8_t IsSet() {
        return PORT::PinRead() & (uint8_t)(1 << PIN);
    }
};

MAKE_PORT(PORTA, DDRA, PINA, Porta)
typedef TPin<Porta, 0> Pa0;
typedef TPin<Porta, 1> Pa1;
typedef TPin<Porta, 2> Pa2;
typedef TPin<Porta, 3> Pa3;
typedef TPin<Porta, 4> Pa4;
typedef TPin<Porta, 5> Pa5;
typedef TPin<Porta, 6> Pa6;
typedef TPin<Porta, 7> Pa7;

MAKE_PORT(PORTB, DDRB, PINB, Portb)
typedef TPin<Portb, 0> Pb0;
typedef TPin<Portb, 1> Pb1;
typedef TPin<Portb, 2> Pb2;
typedef TPin<Portb, 3> Pb3;
typedef TPin<Portb, 4> Pb4;
typedef TPin<Portb, 5> Pb5;
typedef TPin<Portb, 6> Pb6;
typedef TPin<Portb, 7> Pb7;

MAKE_PORT(PORTC, DDRC, PINC, Portc)
typedef TPin<Portc, 0> Pc0;
typedef TPin<Portc, 1> Pc1;
typedef TPin<Portc, 2> Pc2;
typedef TPin<Portc, 3> Pc3;
typedef TPin<Portc, 4> Pc4;
typedef TPin<Portc, 5> Pc5;
typedef TPin<Portc, 6> Pc6;
typedef TPin<Portc, 7> Pc7;

MAKE_PORT(PORTD, DDRD, PIND, Portd)
typedef TPin<Portd, 0> Pd0;
typedef TPin<Portd, 1> Pd1;
typedef TPin<Portd, 2> Pd2;
typedef TPin<Portd, 3> Pd3;
typedef TPin<Portd, 4> Pd4;
typedef TPin<Portd, 5> Pd5;
typedef TPin<Portd, 6> Pd6;
typedef TPin<Portd, 7> Pd7;

#endif /* AVRPIN_H_ */

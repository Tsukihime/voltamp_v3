#ifndef ADC_H_
#define ADC_H_

#include <stdint.h>

class Adc {
    public:
        typedef uint16_t DataT;

        enum Vref {
            External = 0 << REFS1 | 0 << REFS0,
            VCC = 0 << REFS1 | 1 << REFS0,
            Internal = 1 << REFS1 | 1 << REFS0
        };

        enum AdcDivider {
            Div2 = 0 << ADPS2 | 0 << ADPS1 | 1 << ADPS0,
            Div4 = 0 << ADPS2 | 1 << ADPS1 | 0 << ADPS0,
            Div8 = 0 << ADPS2 | 1 << ADPS1 | 1 << ADPS0,
            Div16 = 1 << ADPS2 | 0 << ADPS1 | 0 << ADPS0,
            Div32 = 1 << ADPS2 | 0 << ADPS1 | 1 << ADPS0,
            Div64 = 1 << ADPS2 | 1 << ADPS1 | 0 << ADPS0,
            Div128 = 1 << ADPS2 | 1 << ADPS1 | 1 << ADPS0
        };

        enum {
            DividerMask = 1 << ADPS2 | 1 << ADPS1 | 1 << ADPS0,
            MuxMask = 1 << MUX3 | 1 << MUX2 | 1 << MUX1 | 1 << MUX0,
            VrefMask = 1 << REFS1 | 1 << REFS0
        };

        static void SetClockDivider(AdcDivider divider) {
            ADCSRA = (ADCSRA & DividerMask) | divider;
        }

        static void SetVref(Vref ref) {
            ADMUX = (ADMUX & ~VrefMask) | ref;
        }

        static void SetChannel(uint8_t channel) {
            ADMUX = (ADMUX & ~MuxMask) | (channel & MuxMask);
        }

        static void Init(uint8_t channel = 0, AdcDivider divider = Div32, Vref ref = VCC) {
            ADMUX = (ADMUX & ~(MuxMask | VrefMask)) | (channel & MuxMask) | ref;
            ADCSRA = (ADCSRA & DividerMask) | divider | 1 << ADEN;
        }

        static void StartContinuousConversions() {
            ADCSRA |= (1 << ADATE) | (1 << ADSC) | (1 << ADEN);
        }

        static void EnableInterrupt() {
            ADCSRA |= (1 << ADIE) | (1 << ADEN);
        }

        static void StartSingleConversion() {
            ADCSRA |= 1 << ADSC | 1 << ADEN;
        }

        static DataT Read() {
            while (!ResultReady())
            ;
            return ADC;
        }

        static bool ResultReady() {
            return (ADCSRA & (1 << ADSC)) == 0;
        }

        static DataT SingleConversion() {
            StartSingleConversion();
            return Read();
        }

        static void Enable() {
            ADCSRA |= 1 << ADEN;
        }

        static void Disable() {
            ADCSRA &= ~(1 << ADEN);
        }
};

#endif /* ADC_H_ */
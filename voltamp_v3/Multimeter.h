#ifndef _ADC_H_
#define _ADC_H_

class Multimeter {
    public:
        static void updateValues();
        static int16_t getVoltage();
        static int16_t getRawVoltage();
        static int16_t getCurrent();
        static int16_t getRawCurrent();
};

#endif /* _ADC_H_ */

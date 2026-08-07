#ifndef FONT_H_
#define FONT_H_

#include <inttypes.h>
#include <avr/pgmspace.h>

class Font {
    private:
        uint8_t w;
        uint8_t h;
        const uint8_t* data;

    public:
        Font(uint8_t width, uint8_t height, const uint8_t FontData[]);
        uint8_t getWidth();
        uint8_t getHeight();
        const uint8_t* charData(uint8_t index);
};

#endif /* FONT_H_ */

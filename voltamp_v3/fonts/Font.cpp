#include "Font.h"

Font::Font(uint8_t width, uint8_t height, const uint8_t FontData[]) : w(width), h(height), data(FontData) {
}

uint8_t Font::getWidth() {
    return w;
}

uint8_t Font::getHeight() {
    return h;
}

const uint8_t* Font::charData(uint8_t index) {
    uint16_t packedCharSize = w * h / 8;
    return &data[index * packedCharSize];
}

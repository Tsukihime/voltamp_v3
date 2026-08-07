#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>
#include <avr/cpufunc.h>
#include <avr/pgmspace.h>

#include "lib/AVRPin.hpp"
#include "ST7735Lcd.h"

using namespace ST7735;

const uint8_t SPI_NO_INTERRUPT = (0 << SPIE);
const uint8_t SPI_ENABLE = (1 << SPE);
const uint8_t SPI_LSB_FIRST = (1 << DORD);
const uint8_t SPI_MSB_FIRST = (0 << DORD);
const uint8_t SPI_MASTER = (1 << MSTR);
const uint8_t SPI_PRESCALER_DIV4 = ((0 << SPR1) | (0 << SPR0));
const uint8_t SPI_PRESCALER_DIV16 = ((0 << SPR1) | (1 << SPR0));
const uint8_t SPI_DOUBLE_SPEED = (1 << SPI2X);

using LCD_RES = Pb2;
using LCD_CS = Pb4;
using LCD_DC = Pb3;

using MISO = Pb6;
using MOSI = Pb5;
using SCK = Pb7;

void ST7735Lcd::initialize(void) {
    MISO::SetDirRead();
    MOSI::SetDirWrite();
    SCK::SetDirWrite();

    SPSR = SPI_DOUBLE_SPEED;
    SPCR = SPI_NO_INTERRUPT | SPI_ENABLE | SPI_MSB_FIRST | SPI_MASTER | (0 << CPOL) | (0 << CPHA) | SPI_PRESCALER_DIV4;

    LCD_CS::SetDirWrite();
    LCD_RES::SetDirWrite();
    LCD_DC::SetDirWrite();
    Init();
}

void lcd_delay_ms(uint16_t ms) {
    while (ms--) {
        _delay_ms(1);
    }
}

void Select() {
    LCD_CS::Clear();
}

void Unselect() {
    LCD_CS::Set();
}

void Reset() {
    LCD_RES::Clear();
    lcd_delay_ms(5);
    LCD_RES::Set();
}

static void SendData(uint8_t* data, size_t size) {
    if (size == 0) {
        return;
    }

    SPDR = *data;
    while (--size > 0) {
        data++;
        while(!(SPSR & (1 << SPIF)));
        SPDR = *data;
    }
    while(!(SPSR & (1 << SPIF)));
}

static void Fill(uint16_t color, size_t size) {
    uint8_t b0 = color & 0xff;
    uint8_t b1 = color >> 8;

    SPDR = b0;
    while(--size) {
        while(!(SPSR & (1 << SPIF)));
        SPDR = b1;
        _NOP(); // magic - do code faster!!
        while(!(SPSR & (1 << SPIF)));
        SPDR = b0;
    }
    while(!(SPSR & (1 << SPIF)));
    SPDR = b1;
    while(!(SPSR & (1 << SPIF)));
}

void WriteCommand(uint8_t cmd) {
    LCD_DC::Clear();
    SendData(&cmd, 1);
}

void WriteData(uint8_t* buff, size_t buff_size) {
    LCD_DC::Set();
    SendData(buff, buff_size);
}

void ST7735Lcd::SetAddressWindow(uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1) {
    // column address set
    WriteCommand(CASET);
    uint8_t datax[] = { 0x00, (uint8_t)(x0 + XSTART), 0x00, (uint8_t)(x1 + XSTART) };
    WriteData(datax, sizeof(datax));

    // row address set
    WriteCommand(RASET);
    uint8_t datay[] = { 0x00, (uint8_t)(y0 + YSTART), 0x00, (uint8_t)(y1 + YSTART) };
    WriteData(datay, sizeof(datay));

    // write to RAM
    WriteCommand(RAMWR);
}

void ST7735Lcd::ExecuteCommandList(const uint8_t *addr) {
    uint8_t numCommands, numArgs;
    uint16_t ms;

    numCommands = *addr++;
    while(numCommands--) {
        uint8_t cmd = *addr++;
        WriteCommand(cmd);

        numArgs = *addr++;
        // If high bit set, delay follows args
        ms = numArgs & DELAY_MASK;
        numArgs &= ~DELAY_MASK;
        if(numArgs) {
            WriteData((uint8_t*)addr, numArgs);
            addr += numArgs;
        }

        if(ms) {
            ms = *addr++;
            if(ms == 255) ms = 500;
            lcd_delay_ms(ms);
        }
    }
}

void ST7735Lcd::Init() {
    Select();
    Reset();
    ExecuteCommandList(init_cmds1);
    ExecuteCommandList(init_cmds2);
    ExecuteCommandList(init_cmds3);
    Unselect();
}

void ST7735Lcd::FillScreen(uint16_t color) {
    FillRectangle(0, 0, WIDTH, HEIGHT, color);
}

void ST7735Lcd::FillRectangle(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint16_t color) {
    // clipping
    if((x >= WIDTH) || (y >= HEIGHT)) return;
    if((x + w - 1) >= WIDTH)  w = WIDTH - x;
    if((y + h - 1) >= HEIGHT) h = HEIGHT - y;

    Select();
    SetAddressWindow(x, y, x+w-1, y+h-1);

    LCD_DC::Set();
    Fill(color, w * h);

    Unselect();
}

void ST7735Lcd::DrawPixel(uint8_t x, uint8_t y, uint16_t color) {
    if((x >= WIDTH) || (y >= HEIGHT))
        return;

    Select();
    SetAddressWindow(x, y, x+1, y+1);
    WriteData((uint8_t*)&color, sizeof(color));
    Unselect();
}

void ST7735Lcd::DrawImage(uint8_t x, uint8_t y, uint8_t w, uint8_t h, const uint16_t* data) {
    if((x >= WIDTH) || (y >= HEIGHT)) return;
    if((x + w - 1) >= WIDTH) return;
    if((y + h - 1) >= HEIGHT) return;

    Select();
    SetAddressWindow(x, y, x+w-1, y+h-1);
    WriteData((uint8_t*)data, sizeof(uint16_t) * w * h);
    Unselect();
}

void ST7735Lcd::DrawOneBitImage(uint8_t x, uint8_t y, uint8_t w, uint8_t h,
                                uint16_t ForegroundColor, uint16_t BackgroundColor,
                                const uint8_t* pgm_data) {
    if((x >= WIDTH) || (y >= HEIGHT)) return;
    if((x + w - 1) >= WIDTH) return;
    if((y + h - 1) >= HEIGHT) return;

    Select();
    SetAddressWindow(x, y, x+w-1, y+h-1);

    LCD_DC::Set();

    uint16_t pixel_count = w * h;
    for(uint16_t i = 0; i < pixel_count; /* increment in inner for*/ ) {
        uint8_t byte = pgm_read_byte(pgm_data++);

        for(uint8_t k = 0; (k < 8) && (i < pixel_count); k++, i++) {
            if(byte & 1) {
                SendData((uint8_t*)&ForegroundColor, sizeof(ForegroundColor));
            } else {
                SendData((uint8_t*)&BackgroundColor, sizeof(BackgroundColor));
            }
            byte >>= 1;
        }
    }
    Unselect();
}

void ST7735Lcd::DrawChar(uint8_t charcode, uint8_t x, uint8_t y, 
                                 uint16_t ForegroundColor,
                                 uint16_t BackgroundColor,
                                 Font font) {
    DrawOneBitImage(x, y, font.getWidth(), font.getHeight(),
    ForegroundColor, BackgroundColor,
    font.charData(charcode));
}

void ST7735Lcd::InvertColors(bool invert) {
    Select();
    WriteCommand(invert ? INVON : INVOFF);
    Unselect();
}

const uint16_t ST7735Lcd::rgbTo16BitColor(uint8_t r, uint8_t g, uint8_t b) {
    const uint16_t color = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3);
    return (color >> 8) | (color << 8);
}

#ifndef ST7735_H_
#define ST7735_H_

#include <string.h>
#include "fonts/Font.h"

//#define ALI18_DEFAULT          1 // AliExpress/eBay 1.8" display, default orientation
#define ALI18_RIGHT            1 // AliExpress/eBay 1.8" display, rotate right
//#define ALI18_LEFT             1 // AliExpress/eBay 1.8" display, rotate left
//#define ALI18_UPSIDE_DOWN      1 // AliExpress/eBay 1.8" display, upside down
//#define WAVE18_DEFAULT         1 // WaveShare ST7735S-based 1.8" display, default orientation
//#define WAVE18_RIGHT           1 // WaveShare ST7735S-based 1.8" display, rotate right
//#define WAVE18_LEFT            1 // WaveShare ST7735S-based 1.8" display, rotate left
//#define WAVE18_UPSIDE_DOWN     1 // WaveShare ST7735S-based 1.8" display, upside down
//#define DISPLAY144_DEFAULT     1 // 1.44" display, default orientation
//#define DISPLAY144_RIGHT       1 // 1.44" display, rotate right
//#define DISPLAY144_LEFT        1 // 1.44" display, rotate left
//#define DISPLAY144_UPSIDE_DOWN 1 // 1.44" display, upside down
//#define MINI_DEFAULT           1 // mini 160x80 display (it's unlikely you want the default orientation)
//#define MINI_LEFT              1 // mini 160x80, rotate left
//#define MINI_RIGHT             1 // mini 160x80, rotate right

namespace ST7735 {
    namespace MadCTL {
        const uint8_t MY  = 0x80;
        const uint8_t MX  = 0x40;
        const uint8_t MV  = 0x20;
        const uint8_t ML  = 0x10;
        const uint8_t RGB = 0x00;
        const uint8_t BGR = 0x08;
        const uint8_t MH  = 0x04;
    }

    namespace InitialConstants {
        // AliExpress/eBay 1.8" display, default orientation
        #ifdef ALI18_DEFAULT
            #define ST7735_IS_160X128 1
            const uint8_t WIDTH =  128;
            const uint8_t HEIGHT = 160;
            const uint8_t XSTART = 0;
            const uint8_t YSTART = 0;
            const uint8_t ROTATION = (MadCTL::MX | MadCTL::MY);
        #endif

        // AliExpress/eBay 1.8" display, rotate right
        #ifdef ALI18_RIGHT
            #define ST7735_IS_160X128 1
            const uint8_t WIDTH =  160;
            const uint8_t HEIGHT = 128;
            const uint8_t XSTART = 0;
            const uint8_t YSTART = 0;
            const uint8_t ROTATION = (MadCTL::MY | MadCTL::MV);
        #endif

        // AliExpress/eBay 1.8" display, rotate left
        #ifdef ALI18_LEFT
            #define ST7735_IS_160X128 1
            const uint8_t WIDTH =  160;
            const uint8_t HEIGHT = 128;
            const uint8_t XSTART = 0;
            const uint8_t YSTART = 0;
            const uint8_t ROTATION = (MadCTL::MX | MadCTL::MV);
        #endif

        // AliExpress/eBay 1.8" display, upside down
        #ifdef ALI18_UPSIDE_DOWN
            #define ST7735_IS_160X128 1
            const uint8_t WIDTH =  128;
            const uint8_t HEIGHT = 160;
            const uint8_t XSTART = 0;
            const uint8_t YSTART = 0;
            const uint8_t ROTATION = (0);
        #endif

        // WaveShare ST7735S-based 1.8" display, default orientation
        #ifdef WAVE18_DEFAULT
            #define ST7735_IS_160X128 1
            const uint8_t WIDTH =  128;
            const uint8_t HEIGHT = 160;
            const uint8_t XSTART = 2;
            const uint8_t YSTART = 1;
            const uint8_t ROTATION = (MadCTL::MX | MadCTL::MY | MadCTL::RGB);
        #endif

        // WaveShare ST7735S-based 1.8" display, rotate right
        #ifdef WAVE18_RIGHT
            #define ST7735_IS_160X128 1
            const uint8_t WIDTH =  160;
            const uint8_t HEIGHT = 128;
            const uint8_t XSTART = 1;
            const uint8_t YSTART = 2;
            const uint8_t ROTATION = (MadCTL::MY | MadCTL::MV | MadCTL::RGB);
        #endif

        // WaveShare ST7735S-based 1.8" display, rotate left
        #ifdef WAVE18_LEFT
            #define ST7735_IS_160X128 1
            const uint8_t WIDTH =  160;
            const uint8_t HEIGHT = 128;
            const uint8_t XSTART = 1;
            const uint8_t YSTART = 2;
            const uint8_t ROTATION = (MadCTL::MX | MadCTL::MV | MadCTL::RGB);
        #endif

        // WaveShare ST7735S-based 1.8" display, upside down
        #ifdef WAVE18_UPSIDE_DOWN
            #define ST7735_IS_160X128 1
            const uint8_t WIDTH =  128;
            const uint8_t HEIGHT = 160;
            const uint8_t XSTART = 2;
            const uint8_t YSTART = 1;
            const uint8_t ROTATION = (MadCTL::RGB);
        #endif

        // 1.44" display, default orientation
        #ifdef DISPLAY144_DEFAULT
            #define ST7735_IS_128X128 1
            const uint8_t WIDTH =  128;
            const uint8_t HEIGHT = 128;
            const uint8_t XSTART = 2;
            const uint8_t YSTART = 3;
            const uint8_t ROTATION = (MadCTL::MX | MadCTL::MY | MadCTL::BGR);
        #endif

        // 1.44" display, rotate right
        #ifdef DISPLAY144_RIGHT
            #define ST7735_IS_128X128 1
            const uint8_t WIDTH =  128;
            const uint8_t HEIGHT = 128;
            const uint8_t XSTART = 3;
            const uint8_t YSTART = 2;
            const uint8_t ROTATION = (MadCTL::MY | MadCTL::MV | MadCTL::BGR);
        #endif

        // 1.44" display, rotate left
        #ifdef DISPLAY144_LEFT
            #define ST7735_IS_128X128 1
            const uint8_t WIDTH =  128;
            const uint8_t HEIGHT = 128;
            const uint8_t XSTART = 1;
            const uint8_t YSTART = 2;
            const uint8_t ROTATION = (MadCTL::MX | MadCTL::MV | MadCTL::BGR);
        #endif

        // 1.44" display, upside down
        #ifdef DISPLAY144_UPSIDE_DOWN
            #define ST7735_IS_128X128 1
            const uint8_t WIDTH =  128;
            const uint8_t HEIGHT = 128;
            const uint8_t XSTART = 2;
            const uint8_t YSTART = 1;
            const uint8_t ROTATION = (MadCTL::BGR);
        #endif

        // mini 160x80 display (it's unlikely you want the default orientation)
        #ifdef MINI_DEFAULT
            #define ST7735_IS_160X80 1
            const uint8_t XSTART = 26;
            const uint8_t YSTART = 1;
            const uint8_t WIDTH =  80;
            const uint8_t HEIGHT = 160;
            const uint8_t ROTATION = (MadCTL::MX | MadCTL::MY | MadCTL::BGR);
        #endif

        // mini 160x80, rotate left
        #ifdef MINI_LEFT
            #define ST7735_IS_160X80 1
            const uint8_t XSTART = 1;
            const uint8_t YSTART = 26;
            const uint8_t WIDTH =  160;
            const uint8_t HEIGHT = 80;
            const uint8_t ROTATION = (MadCTL::MX | MadCTL::MV | MadCTL::BGR);
        #endif

        // mini 160x80, rotate right
        #ifdef MINI_RIGHT
            #define ST7735_IS_160X80 1
            const uint8_t XSTART = 1;
            const uint8_t YSTART = 26;
            const uint8_t WIDTH =  160;
            const uint8_t HEIGHT = 80;
            const uint8_t ROTATION = (MadCTL::MY | MadCTL::MV | MadCTL::BGR);
        #endif
    }

    namespace Commands {
        const uint8_t NOP     = 0x00;
        const uint8_t SWRESET = 0x01;
        const uint8_t RDDID   = 0x04;
        const uint8_t RDDST   = 0x09;

        const uint8_t SLPIN   = 0x10;
        const uint8_t SLPOUT  = 0x11;
        const uint8_t PTLON   = 0x12;
        const uint8_t NORON   = 0x13;

        const uint8_t INVOFF  = 0x20;
        const uint8_t INVON   = 0x21;
        const uint8_t DISPOFF = 0x28;
        const uint8_t DISPON  = 0x29;
        const uint8_t CASET   = 0x2A;
        const uint8_t RASET   = 0x2B;
        const uint8_t RAMWR   = 0x2C;
        const uint8_t RAMRD   = 0x2E;

        const uint8_t PTLAR   = 0x30;
        const uint8_t COLMOD  = 0x3A;
        const uint8_t MADCTL  = 0x36;

        const uint8_t FRMCTR1 = 0xB1;
        const uint8_t FRMCTR2 = 0xB2;
        const uint8_t FRMCTR3 = 0xB3;
        const uint8_t INVCTR  = 0xB4;
        const uint8_t DISSET5 = 0xB6;

        const uint8_t PWCTR1  = 0xC0;
        const uint8_t PWCTR2  = 0xC1;
        const uint8_t PWCTR3  = 0xC2;
        const uint8_t PWCTR4  = 0xC3;
        const uint8_t PWCTR5  = 0xC4;
        const uint8_t VMCTR1  = 0xC5;

        const uint8_t RDID1   = 0xDA;
        const uint8_t RDID2   = 0xDB;
        const uint8_t RDID3   = 0xDC;
        const uint8_t RDID4   = 0xDD;

        const uint8_t PWCTR6  = 0xFC;

        const uint8_t GMCTRP1 = 0xE0;
        const uint8_t GMCTRN1 = 0xE1;
    }

    namespace Colors {
        const uint16_t BLACK   = 0x0000;
        const uint16_t BLUE    = 0x001F;
        const uint16_t RED     = 0xF800;
        const uint16_t GREEN   = 0x07E0;
        const uint16_t CYAN    = 0x07FF;
        const uint16_t MAGENTA = 0xF81F;
        const uint16_t YELLOW  = 0xFFE0;
        const uint16_t WHITE   = 0xFFFF;
    }

    const uint8_t DELAY_MASK = 0x80;

    using namespace Commands;
    using namespace InitialConstants;

    // based on Adafruit ST7735 library for Arduino
    static const uint8_t
    init_cmds1[] = {              // Init for 7735R, part 1 (red or green tab)
        15,                       // 15 commands in list:
        SWRESET,          DELAY_MASK,  //  1: Software reset, 0 args, w/delay
        150,                      //     150 ms delay
        SLPOUT ,          DELAY_MASK,  //  2: Out of sleep mode, 0 args, w/delay
        150,                      //     500 ms delay
        FRMCTR1,        3      ,  //  3: Frame rate ctrl - normal mode, 3 args:
        0x01, 0x2C, 0x2D,         //     Rate = fosc/(1x2+40) * (LINE+2C+2D)
        FRMCTR2,        3      ,  //  4: Frame rate control - idle mode, 3 args:
        0x01, 0x2C, 0x2D,         //     Rate = fosc/(1x2+40) * (LINE+2C+2D)
        FRMCTR3,        6      ,  //  5: Frame rate ctrl - partial mode, 6 args:
        0x01, 0x2C, 0x2D,         //     Dot inversion mode
        0x01, 0x2C, 0x2D,         //     Line inversion mode
        INVCTR ,        1      ,  //  6: Display inversion ctrl, 1 arg, no delay:
        0x07,                     //     No inversion
        PWCTR1 ,        3      ,  //  7: Power control, 3 args, no delay:
        0xA2,
        0x02,                     //     -4.6V
        0x84,                     //     AUTO mode
        PWCTR2 ,        1      ,  //  8: Power control, 1 arg, no delay:
        0xC5,                     //     VGH25 = 2.4C VGSEL = -10 VGH = 3 * AVDD
        PWCTR3 ,        2      ,  //  9: Power control, 2 args, no delay:
        0x0A,                     //     Opamp current small
        0x00,                     //     Boost frequency
        PWCTR4 ,        2      ,  // 10: Power control, 2 args, no delay:
        0x8A,                     //     BCLK/2, Opamp current small & Medium low
        0x2A,
        PWCTR5 ,        2      ,  // 11: Power control, 2 args, no delay:
        0x8A, 0xEE,
        VMCTR1 ,        1      ,  // 12: Power control, 1 arg, no delay:
        0x0E,
        INVOFF ,        0      ,  // 13: Don't invert display, no args, no delay
        MADCTL ,        1      ,  // 14: Memory access control (directions), 1 arg:
        ROTATION,                 //     row addr/col addr, bottom to top refresh
        COLMOD ,        1      ,  // 15: set color mode, 1 arg, no delay:
    0x05 },                       //     16-bit color

    #if (defined(ST7735_IS_128X128) || defined(ST7735_IS_160X128))
    init_cmds2[] = {              // Init for 7735R, part 2 (1.44" display)
        2,                        //  2 commands in list:
        CASET  ,        4      ,  //  1: Column addr set, 4 args, no delay:
        0x00, 0x00,               //     XSTART = 0
        0x00, 0x7F,               //     XEND = 127
        RASET  ,        4      ,  //  2: Row addr set, 4 args, no delay:
        0x00, 0x00,               //     XSTART = 0
    0x00, 0x7F },                 //     XEND = 127
    #endif // ST7735_IS_128X128

    #ifdef ST7735_IS_160X80
    init_cmds2[] = {              // Init for 7735S, part 2 (160x80 display)
        3,                        //  3 commands in list:
        CASET  ,        4      ,  //  1: Column addr set, 4 args, no delay:
        0x00, 0x00,               //     XSTART = 0
        0x00, 0x4F,               //     XEND = 79
        RASET  ,        4      ,  //  2: Row addr set, 4 args, no delay:
        0x00, 0x00,               //     XSTART = 0
        0x00, 0x9F ,              //     XEND = 159
        INVON, 0 },               //  3: Invert colors
    #endif

    init_cmds3[] = {              // Init for 7735R, part 3 (red or green tab)
        4,                        //  4 commands in list:
        GMCTRP1,        16      , //  1: Magical unicorn dust, 16 args, no delay:
        0x02, 0x1c, 0x07, 0x12,
        0x37, 0x32, 0x29, 0x2d,
        0x29, 0x25, 0x2B, 0x39,
        0x00, 0x01, 0x03, 0x10,
        GMCTRN1,        16      , //  2: Sparkles and rainbows, 16 args, no delay:
        0x03, 0x1d, 0x07, 0x06,
        0x2E, 0x2C, 0x29, 0x2D,
        0x2E, 0x2E, 0x37, 0x3F,
        0x00, 0x00, 0x02, 0x10,
        NORON  ,           DELAY_MASK, //  3: Normal display on, no args, w/delay
        10,                       //     10 ms delay
        DISPON ,           DELAY_MASK, //  4: Main screen turn on, no args w/delay
    100 };                        //     100 ms delay
}

class ST7735Lcd {
    private:
        static void SetAddressWindow(uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1);
        static void ExecuteCommandList(const uint8_t *addr);
        static void Init();

    public:
        static void initialize(void);

        static void FillScreen(uint16_t color);
        static void FillRectangle(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint16_t color);
        static void DrawPixel(uint8_t x, uint8_t y, uint16_t color);        
        static void DrawImage(uint8_t x, uint8_t y, uint8_t w, uint8_t h, const uint16_t* data);
        static void DrawOneBitImage(uint8_t x, uint8_t y, uint8_t w, uint8_t h,
                                    uint16_t ForegroundColor, uint16_t BackgroundColor,
                                    const uint8_t* pgm_data);

        static void DrawChar(uint8_t charcode, uint8_t x, uint8_t y,
                                     uint16_t ForegroundColor,
                                     uint16_t BackgroundColor,
                                     Font font);

        static void InvertColors(bool invert);

        static const uint16_t rgbTo16BitColor(uint8_t r, uint8_t g, uint8_t b);
};

#endif /* ST7735_H_ */

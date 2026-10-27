#include "utils.h"

#ifdef __AVR__
    #include <avr/pgmspace.h>
#else
    #define PROGMEM
    #define pgm_read_dword_near(addr) (*(addr))
#endif

uint8_t int32ToStrFixedPoint(int32_t value, char buffer[13], uint8_t point_position) {
    uint8_t len = 0;
    uint32_t u_value;

    if(value < 0) {
        u_value = -static_cast<uint32_t>(value);
        buffer[len++] = '-';
    } else {
        u_value = value;
    }

    static const uint32_t exp[10] PROGMEM = {1, 10, 100, 1000, 10000, 100000, 1000000, 10000000, 100000000, 1000000000};

    bool print_start = false;

    for (int8_t i = 9; i >= 0; i--) {
        char digit = '0';
        uint32_t exponent = pgm_read_dword_near(&exp[i]);
        while (u_value >= exponent) {
            u_value -= exponent;
            digit++;
        }

        bool point_expected = (i == point_position);
        if (!print_start && digit == '0' && !point_expected) {
            continue; // Skip leading zeros
        }

        print_start = true;
        buffer[len++] = digit;

        if(point_expected && (point_position != 0)) {
            buffer[len++] = '.';
        }
    }
    buffer[len] = '\0';
    return len;
}


#define isspace_fast(x) ((x) == ' ' || (x) == '\t' || (x) == '\n' || (x) == '\v' || (x) == '\f' || (x) == '\r')

int32_t fastatoi(const char *b) {
    int32_t res = 0;
    for (; isspace_fast(*b); ++b);

    if (*b == '-') {
        ++b;
        // Iterate through all characters of input string and update result
        for (; ; ++b) {
            unsigned d = static_cast<unsigned>(*b) - '0';
            if (d > 9) {
                return res;
            }
            res = res * 10 - d;
        }

    } else if (*b == '+') {
        ++b;
    }
    
    // Iterate through all characters of input string and update result
    for (; ; ++b) {
        unsigned d = static_cast<unsigned>(*b) - '0';
        if (d > 9) {
            return res;
        }
        res = res * 10 + d;
    }

    //  unreachable
    return res;
}


/*
    Converts a string with floating-point and exponential notation to fixed-point.

    target_exp - Target fixed-point exponent.
                 For example, target_exp = 3 means a scale of 10^3.

    Returns int32_t.

    Important: This function modifies the input string `s`.
               You must pass a RAM buffer, not a flash constant.
*/
int32_t str_to_fixedpoint(char *s, int16_t target_exp) {
    if (s == 0) {
        return 0;
    }

    while (isspace_fast(*s)) {
        ++s;
    }

    uint8_t neg = 0;

    if (*s == '-') {
        neg = 1;
        ++s;
    } else if (*s == '+') {
        ++s;
    }

    char *num = s;
    char *p = num;

    // Search for exponent E/e and truncate it from the string.
    while (*p && *p != 'e' && *p != 'E') {
        ++p;
    }

    int16_t str_exp = 0;

    if (*p) {
        *p = '\0';
        str_exp = fastatoi(p + 1);
    }

    /*
        Search for the decimal point.
        If found, count the number of digits after the point: N (stored in `frac`).
        At the same time, remove the point by shifting the fractional part to the left.
    */
    p = num;
    while (*p && *p != '.') {
        ++p;
    }

    uint16_t frac = 0;

    if (*p == '.') {
        char *dst = p;
        char *src = p + 1;

        while (*src) {
            ++frac;
            *dst++ = *src++;
        }

        *dst = '\0';
    }

    int32_t total_exp = (int32_t)target_exp
                      + (int32_t)str_exp
                      - (int32_t)frac;

    /*
        If the exponent is negative, truncate digits from the right.
        If the shift is greater than the length of the number, return 0.
    */
    if (total_exp < 0) {
        uint16_t len = 0;

        while (num[len]) {
            ++len;
        }

        uint32_t cut = (uint32_t)(-total_exp);

        if (cut >= (uint32_t)len) {
            return 0;
        }

        num[len - (uint16_t)cut] = '\0';
        total_exp = 0;
    }

    // Parse the integer value from the remaining digits.
    int32_t mag = fastatoi(num);

    if (total_exp > 10) {
        return neg ? INT32_MIN : INT32_MAX;
    }

    while (total_exp > 0) {
        mag = mag * 10;
        --total_exp;
    }

    if (neg) {
        return -mag;
    }

    return mag;
}

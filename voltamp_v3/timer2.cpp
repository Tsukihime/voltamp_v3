#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <avr/cpufunc.h>
#include "timer2.h"

#include "Buttons.h"
#include "lib/Scheduler.h"

uint32_t systemTicks = 0;
uint32_t cycleCount = 0;
uint8_t MCULoad = 0;

ISR(TIMER2_COMP_vect) {
    systemTicks++;
    static uint8_t iteration = 0;
    if(++iteration == 10) {          // 1000 ticks per second / 10 == 100 ticks per second = period 10ms
        Scheduler::TimerISR();
        iteration = 0;
    }

    Buttons::poolISR();
}

uint8_t Timer2::getMCULoad() {
    return MCULoad;
}

void calcMCULoad() {
    MCULoad = ((F_CPU - cycleCount) * 100 / F_CPU);
    cycleCount = 0;
}

#ifdef DEBUG
    const uint8_t IDLE_TASK_TIME = 41;
#else
    const uint8_t IDLE_TASK_TIME = 38;
#endif

void Timer2::poolTasksRun() {
    while(true) {
        Scheduler::processTasks();
        cycleCount += IDLE_TASK_TIME;
    }
}

uint32_t Timer2::getSystemTime() {
    return systemTicks / 100;
}

const uint8_t TIMER2_CTC_MODE = ((1 << WGM21) | (0 << WGM20));
const uint8_t TIMER2_PRESCALER_DIV1024 = ((1 << CS22) | (1 << CS21) | (1 << CS20));
const uint8_t TIMER2_PRESCALER_DIV128 = ((1 << CS22) | (0 << CS21) | (1 << CS20));
const uint8_t TIMER2_OUTPUT_COMPARE_MATCH_A_INTERRUPT_ENABLE = (1 << OCIE2);
const uint8_t TIMER2_ALL_INTERRUPT_DISABLE = 0;
const uint8_t TIMER2_NORMAL_PORT_OPERATION_OC2_DISCONNECTED = ((0 << COM21) | (0 << COM20));

void Timer2::initialize() {
    TIMSK = TIMER2_ALL_INTERRUPT_DISABLE;
    TCNT2 = 0;
    OCR2 = 0x7C; // 125 000 / (125 - 1) = 1000 ticks per second >> period = 1 ms
    TCCR2 = TIMER2_NORMAL_PORT_OPERATION_OC2_DISCONNECTED | TIMER2_CTC_MODE| TIMER2_PRESCALER_DIV128;
    TIFR = (1 << OCF2) | (1 << TOV2); // reset interrupt flags
    TIMSK = TIMER2_OUTPUT_COMPARE_MATCH_A_INTERRUPT_ENABLE;

    Scheduler::setTimer(&calcMCULoad, 100, true);
}

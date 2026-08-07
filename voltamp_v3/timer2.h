#ifndef TIMER_H_
#define TIMER_H_

class Timer2 {
    public:
        static void initialize();
        static uint32_t getSystemTime();        
        static uint8_t getMCULoad();
        static void poolTasksRun();
};

#endif /* TIMER_H_ */

#ifndef TIMER_HELPER_H
#define TIMER_HELPER_H

#include "stm32g4xx_hal.h"
#include "tim.h"

uint32_t get_time_us(void);

void delay_us(uint32_t us);
void delay_ms(uint32_t ms);
void delay_s(uint32_t s);

#endif // TIMER_HELPER_H

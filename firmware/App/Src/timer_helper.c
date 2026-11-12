#include "timer_helper.h"

uint32_t get_time_us(void) {
    return __HAL_TIM_GET_COUNTER(&htim2);
}
void delay_us(uint32_t us) {
    uint32_t start = get_time_us();
    while ((get_time_us() - start) < us);
}
void delay_ms(uint32_t ms) {
    for (uint32_t i = 0; i < ms; i++) {
        delay_us(1000);
    }
}
void delay_s(uint32_t s) {
    for (uint32_t i = 0; i < s; i++) {
        delay_ms(1000);
    }
}
#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

#include <stdint.h>
#include "stm32g4xx_hal.h"
#include "main.h"   // for DIR_x_Pin, GPIOx
#include "tim.h"    // for TIM_HandleTypeDef htim1/3/4/8

// Ports/pins for DIR signals (array entries are fixed at compile time)
extern GPIO_TypeDef * const dir_ports[16];
extern const uint16_t       dir_pins[16];

// ADC channel reordering map
extern const uint8_t        adc_index_map[16];

// PWM timer handles + channels per motor index
extern TIM_HandleTypeDef * const pwm_timer_handles[16];
extern const uint32_t       pwm_timer_channels[16];

#endif

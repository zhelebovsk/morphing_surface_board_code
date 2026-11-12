#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

#include <stdint.h>
#include "stm32g4xx_hal.h"
#include "main.h"   // for DIR_x_Pin, GPIOx [DIP Switches defined here too]
#include "tim.h"    // for TIM_HandleTypeDef htim1/3/4/8

// Ports/pins for DIR signals (array entries are fixed at compile time)
extern GPIO_TypeDef * const dir_ports[16];
extern const uint16_t       dir_pins[16];

// PWM timer handles + channels per motor index
extern TIM_HandleTypeDef * const pwm_timer_handles[16];
extern const uint32_t       pwm_timer_channels[16];

// DIP switch state 
extern uint16_t board_id;
extern uint32_t current_time_us;
extern const uint8_t active_motors[14];


#endif

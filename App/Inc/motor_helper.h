#ifndef MOTOR_HELPER_H
#define MOTOR_HELPER_H

#include "stm32g4xx_hal.h"
#include "adc.h"
#include "board_config.h"
// #include "main.h"
// void set_motor_directions(uint16_t *dir_values);
// void set_motor_power(uint16_t *pwm_values);

extern uint16_t buffer_adc1[13];
extern uint16_t buffer_adc2[3];
extern uint8_t  conv_complete[2];

void motor_power_setup(uint8_t mode);
void Start_ADC_DMA(void);
void fetch_potentiometer_values(uint16_t *pot_values);

void motor_pwm_timers_start(void);

void set_motor_directions(uint16_t *dir_values);
void set_motor_power(uint16_t *pwm_values);

#endif // MOTOR_HELPER_H

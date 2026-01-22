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

// void set_motor_direction(uint8_t motor_id, uint16_t dir_value);
// void set_motor_power(uint8_t motor_id, uint16_t pwm_value);
void set_motor(uint8_t motor_id, int16_t motor_set);
int32_t get_calibrated_potentiometer_value(uint8_t motor_id, int32_t raw_value);


#define pos_res uint16_t
#define MOTOR_AMOUNT 16
#define UP_SPEED -50
#define DOWN_SPEED 50

void get_motor_current_positions();
void fix_motor_speeds();
void motor_location_set(void* locations); //todo: change from void* to pos_res*
void motor_speed_set();
void debug_init();


#endif // MOTOR_HELPER_H

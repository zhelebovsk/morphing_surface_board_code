#ifndef MOTOR_HELPER_H
#define MOTOR_HELPER_H

#include "stm32g4xx_hal.h"
#include "adc.h"
#include "board_config.h"
#include <stdbool.h>
// #include "main.h"

// Startup
void motor_power_setup(uint8_t mode);
void Start_ADC_DMA(void);
void motor_pwm_timers_start(void);

//
void fetch_potentiometer_values(uint16_t *pot_values);
void set_motor(uint8_t motor_id, int16_t motor_set);


#define MOTOR_AMOUNT 16
#define UP_SPEED 50
#define DOWN_SPEED -50

void get_motor_current_positions();
void fix_motor_speeds();
void motors_location_set(uint16_t* locations); 
void motor_location_set(uint8_t motor_id, uint16_t location); 

void motor_speed_set(uint8_t motor_id, uint16_t speed_up, uint16_t speed_down);
void motor_speed_up_set(uint8_t motor_id, uint16_t speed_up);
void motor_speed_down_set(uint8_t motor_id, uint16_t speed_down);

void position_init();

void change_motor(bool right);
void change_scale(bool up);
void change_zero(bool pos);
int getmot();
int get_zero_val(int id);
int getscale();

#endif // MOTOR_HELPER_H

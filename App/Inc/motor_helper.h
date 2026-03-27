#ifndef MOTOR_HELPER_H
#define MOTOR_HELPER_H

#include "stm32g4xx_hal.h"
#include "adc.h"
#include "dac.h"
#include "board_config.h"
#include <stdbool.h>
#include "math.h"

#define MOTOR_AMOUNT 16

// Startup
void motor_power_setup(uint8_t mode);
void Calibrate_ADC(void);
void motor_pwm_timers_start(void);


// void update_potentiometer_values(void);

void start_potentiometer_limits(void);
void position_init(void);
void motor_location_set(uint8_t motor_id, uint16_t location); 
void fix_motor_speeds();


void set_controller(uint8_t kp, uint8_t ki, uint8_t kd, uint8_t a, uint8_t u_lim, uint8_t db);

// void fetch_potentiometer_values(void);
// void set_motor(uint8_t motor_id, int16_t motor_set);


// #define UP_SPEED -50
// #define DOWN_SPEED 50

// void motors_location_set(uint16_t* locations); 

// void motor_speed_set(uint8_t motor_id, uint16_t speed_up, uint16_t speed_down);
// void motor_speed_up_set(uint8_t motor_id, uint8_t speed_up);
// void motor_speed_down_set(uint8_t motor_id, uint8_t speed_down);


// void change_motor(bool right);
// void change_scale(bool up);
// void change_zero(bool pos);
// int getmot();
// int get_zero_val(int id);
// int getscale();

#endif // MOTOR_HELPER_H

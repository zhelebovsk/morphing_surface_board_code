#include "motor_helper.h"
#include "timer_helper.h"

#define INIT_SAMPLES 1000
#define DT 0.0005f

#define HI_LIMIT 3415 // 2.5V DAC output
#define LO_LIMIT 680 // 0.5V

float Kp = 0.2f;
float Ki = 0.1f;
float Kd = 0.0f;
uint8_t u_limit = 100;
uint8_t deadband = 10;
float alpha = 0.2f;

float integral[MOTOR_AMOUNT] = {0};
float prev_error[MOTOR_AMOUNT] = {0};

volatile uint32_t conv_counter[2] = {0, 0};
volatile uint8_t conv_complete[2] = {0, 0};
uint16_t buffer_adc1[13] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
uint16_t buffer_adc2[3] = {0, 0, 0};
const uint8_t adc_index_map[16] = {4,9,11,15,10,12,14,13,3,2,1,0,8,7,6,5};

uint16_t pot_raw[MOTOR_AMOUNT] = {0};
float pot_filtered[MOTOR_AMOUNT] = {0.0f};

static uint32_t pot_timer_us = 0;
static uint32_t pot_period_us = 500;

// uint16_t pot_zero = 1536;
uint16_t pot_zero = 1048;

float error[16];
uint16_t desired_position[MOTOR_AMOUNT];
int16_t motor_speeds[MOTOR_AMOUNT];

// Motor power supply voltage options
void motor_power_setup(uint8_t mode) {
  // Enable 6V power supply for motors
  //  voltage | 6.06 | 6.27 | 6.37 | 6.57
  //  6V_L    | 0    | 0    | 1    | 1
  //  6V_H    | 1    | 0    | 1    | 0
  // mode     | 1    | 2    | 3    | 4
  if (mode == 1) { // 6.06V
    HAL_GPIO_WritePin(CTRL_6V_L_GPIO_Port, CTRL_6V_L_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(CTRL_6V_H_GPIO_Port, CTRL_6V_H_Pin, GPIO_PIN_SET);
    return;
  } else if (mode == 2) { // 6.27V
    HAL_GPIO_WritePin(CTRL_6V_L_GPIO_Port, CTRL_6V_L_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(CTRL_6V_H_GPIO_Port, CTRL_6V_H_Pin, GPIO_PIN_RESET);
    return;
  } else if (mode == 3) { // 6.37V
    HAL_GPIO_WritePin(CTRL_6V_L_GPIO_Port, CTRL_6V_L_Pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(CTRL_6V_H_GPIO_Port, CTRL_6V_H_Pin, GPIO_PIN_SET);
    return;
  } 
  else if (mode == 4) { // 6.57V
    HAL_GPIO_WritePin(CTRL_6V_L_GPIO_Port, CTRL_6V_L_Pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(CTRL_6V_H_GPIO_Port, CTRL_6V_H_Pin, GPIO_PIN_RESET);
    return;
  }
}

// PWM timer start
void motor_pwm_timers_start(void) {
  for (int i = 0; i < MOTOR_AMOUNT; ++i) {
    HAL_TIM_PWM_Start(pwm_timer_handles[i], pwm_timer_channels[i]);
  }
}

// ADC Start
void Calibrate_ADC(void) {
  if (HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED) != HAL_OK) {
    Error_Handler();
  }
  if (HAL_ADCEx_Calibration_Start(&hadc2, ADC_SINGLE_ENDED) != HAL_OK) {
    Error_Handler();
  }
}

// ADC Conversion complete callback
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc) {
  if (hadc->Instance == ADC1) {
    conv_complete[0] = 1;
  } else if (hadc->Instance == ADC2) {
    conv_complete[1] = 1;
  }
}

// Position poll, all motors
void fetch_potentiometer_values(void) {
  conv_complete[0] = 0;
  conv_complete[1] = 0;
  HAL_ADC_Start_DMA(&hadc1, (uint32_t*)buffer_adc1, hadc1.Init.NbrOfConversion);
  HAL_ADC_Start_DMA(&hadc2, (uint32_t*)buffer_adc2, hadc2.Init.NbrOfConversion);
  while (!conv_complete[0] || !conv_complete[1]) {}
  conv_counter[0]++;
  uint16_t buffer[MOTOR_AMOUNT];
  for (int i = 0; i < hadc1.Init.NbrOfConversion; i++) {
    buffer[i] = buffer_adc1[i];
  }
  for (int i = hadc1.Init.NbrOfConversion; i < hadc1.Init.NbrOfConversion+hadc2.Init.NbrOfConversion; i++) {
    buffer[i] = buffer_adc2[i - hadc1.Init.NbrOfConversion];
  }
  for (int i = 0; i < MOTOR_AMOUNT; ++i) {
    pot_raw[i] = buffer[adc_index_map[i]];
  }
}

void filter_potentiometer_values(void) {
  for (int i = 0; i < MOTOR_AMOUNT; ++i) {
    pot_filtered[i] = alpha * pot_raw[i] + (1.0f - alpha) * pot_filtered[i];
  }
}

void update_potentiometer_values(void) {
	// The highest sample rate is 30kS/s for ADC1
	pot_timer_us = get_time_us();
  fetch_potentiometer_values();
	filter_potentiometer_values();
}

void start_potentiometer_limits(void) {
  HAL_DAC_SetValue(&hdac1, DAC_CHANNEL_1, DAC_ALIGN_12B_R, HI_LIMIT);
  HAL_DAC_SetValue(&hdac1, DAC_CHANNEL_2, DAC_ALIGN_12B_R, LO_LIMIT);
  HAL_DAC_Start(&hdac1, DAC_CHANNEL_1);
  HAL_DAC_Start(&hdac1, DAC_CHANNEL_2);
}

void position_init() {
	for (int j = 0; j < INIT_SAMPLES; j++) {
    update_potentiometer_values();
    delay_us(pot_period_us);  // keep spacing consistent
	}
	for(int i = 0; i < MOTOR_AMOUNT; i++) {
		desired_position[i] = pot_filtered[i];
		motor_speeds[i] = 0;
	}
}

void motor_location_set(uint8_t motor_id, uint16_t location) {
	desired_position[motor_id] = pot_zero + location;
}

// Motor direct control
void set_motor_direction(uint8_t motor_id, uint16_t dir_value) {
	HAL_GPIO_WritePin(dir_ports[motor_id], dir_pins[motor_id], dir_value ? GPIO_PIN_SET : GPIO_PIN_RESET);
}
void set_motor_power(uint8_t motor_id, uint16_t pwm_value) {
	__HAL_TIM_SET_COMPARE(pwm_timer_handles[motor_id], pwm_timer_channels[motor_id], pwm_value);
}
void set_motor(uint8_t motor_id, int16_t motor_set) {
	set_motor_direction(motor_id, motor_set >= 0 ? 1 : 0);
	uint16_t pwm_value = (uint16_t)(motor_set >= 0 ? motor_set : -motor_set);
	set_motor_power(motor_id, pwm_value);
}

void fix_motor_speeds(){
  update_potentiometer_values();
  for(int i = 0; i < MOTOR_AMOUNT; i++) {
    float e = (float)desired_position[i] - pot_filtered[i];
    error[i] = e;
    if (fabsf(e) < deadband) {
      motor_speeds[i] = 0;
      integral[i] = 0;          // IMPORTANT
      prev_error[i] = e;        // avoid derivative spike
      set_motor(i, 0);
      continue;
    }
    // Integral with anti-windup
    integral[i] += e * DT;
    if (integral[i] > 500) integral[i] = 500;
    if (integral[i] < -500) integral[i] = -500;
    // Derivative
    float derivative = (e - prev_error[i]) / DT;
    prev_error[i] = e;
    // PID output
    float u = Kp * e + Ki * integral[i] + Kd * derivative;
    u = -u;
    if (u > u_limit) u = u_limit;
    if (u < -u_limit) u = -u_limit;

    motor_speeds[i] = (int16_t)u;
    set_motor(i, motor_speeds[i]);
  }
}


void set_controller(uint8_t kp, uint8_t ki, uint8_t kd, uint8_t a, uint8_t u_lim, uint8_t db) {
  Kp = (float)kp / 255.0f; // Scale Kp to [0, 1]
  Ki = (float)ki / 255.0f; // Scale Ki to [0, 1]
  Kd = (float)kd / 255.0f; // Scale Kd to [0, 1]
  alpha = (float)a / 255.0f; // Scale alpha to [0, 1]
  u_limit = u_lim;
  deadband = db;
}

// void motors_location_set(uint16_t* locations) {
// 	uint16_t* locations_arr = (uint16_t*)locations;
// 	for(int i = 0; i < MOTOR_AMOUNT; i++){
// 		last_desired_position[i] = desired_position[i];
// 		desired_position[i] = 1536 + locations_arr[i];
// 		if(desired_position[i] > last_desired_position[i]){
// 			motor_speeds[i] = motor_speeds_up[i];
// 		}else if(desired_position[i] < last_desired_position[i]) {
// 			motor_speeds[i] = motor_speeds_down[i];
// 		}
// 	}
// }



// void motor_speed_set(uint8_t motor_id, uint16_t speed_up, uint16_t speed_down) {
// 	motor_speeds_up[motor_id] = speed_up;
// 	motor_speeds_down[motor_id] = speed_down;
// }
// void motor_speed_up_set(uint8_t motor_id, uint8_t speed_up) {
// 	motor_speeds_up[motor_id] = -(int16_t)speed_up;
// }
// void motor_speed_down_set(uint8_t motor_id, uint8_t speed_down) {
// 	motor_speeds_down[motor_id] = (int16_t)speed_down;
// }


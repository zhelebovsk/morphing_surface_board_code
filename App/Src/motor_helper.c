#include "motor_helper.h"

uint16_t buffer_adc1[13] = {0};
uint16_t buffer_adc2[3] = {0};
uint8_t conv_complete[2] = {0};

// Power
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
// ADC 
void Start_ADC_DMA(void) {
  if (HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED) != HAL_OK) {
    Error_Handler();
  }
  if (HAL_ADCEx_Calibration_Start(&hadc2, ADC_SINGLE_ENDED) != HAL_OK) {
    Error_Handler();
  }
  HAL_ADC_Start_DMA(&hadc1, (uint32_t*)buffer_adc1, hadc1.Init.NbrOfConversion);
  HAL_ADC_Start_DMA(&hadc2, (uint32_t*)buffer_adc2, hadc2.Init.NbrOfConversion);
}
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc->Instance == ADC1) {
    conv_complete[0] = 1;
    HAL_ADC_Start_DMA(&hadc1, (uint32_t*)buffer_adc1, hadc1.Init.NbrOfConversion);
  } else if (hadc->Instance == ADC2) {
    conv_complete[1] = 1;
    HAL_ADC_Start_DMA(&hadc2, (uint32_t*)buffer_adc2, hadc2.Init.NbrOfConversion);
  }
}
void fetch_potentiometer_values(uint16_t *pot_values) {
    if (!(conv_complete[0] && conv_complete[1])) {
      return;
    }
    for (int i = 0; i < hadc1.Init.NbrOfConversion; i++) {
      pot_values[i] = buffer_adc1[i];
    }
    for (int i = hadc1.Init.NbrOfConversion; i < hadc1.Init.NbrOfConversion+hadc2.Init.NbrOfConversion; i++) {
      pot_values[i] = buffer_adc2[i - hadc1.Init.NbrOfConversion];
    }
    // Reorder the values to match the expected order of motors
    uint16_t buffer_ordered[16] = {0};
    for (int i = 0; i < 16; ++i) {
        buffer_ordered[i] = pot_values[adc_index_map[i]];
    }
    for (int i = 0; i < 16; ++i) {
      pot_values[i] = buffer_ordered[i];
    }
    conv_complete[0] = 0;
    conv_complete[1] = 0;
}
// Output init settings
void motor_pwm_timers_start(void) {
  for (int i = 0; i < 16; ++i) {
    HAL_TIM_PWM_Start(pwm_timer_handles[i], pwm_timer_channels[i]);
  }
}
// Motor control
void set_motor_directions(uint16_t *dir_values)
{
    for (int i = 0; i < 16; ++i) {
        HAL_GPIO_WritePin(dir_ports[i], dir_pins[i], dir_values[i] ? GPIO_PIN_SET : GPIO_PIN_RESET);
    }
}
void set_motor_power(uint16_t *pwm_values) {
  for (int i = 0; i < 16; ++i) {
    __HAL_TIM_SET_COMPARE(pwm_timer_handles[i], pwm_timer_channels[i], pwm_values[i]);
  }
}

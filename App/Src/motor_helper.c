#include "motor_helper.h"

uint16_t buffer_adc1[13] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
uint16_t buffer_adc2[3] = {0, 0, 0};
uint8_t conv_complete[2] = {0, 0};
uint32_t pot_counter = 0;

// Potentiometer ADC parameters
const uint8_t adc_index_map[16] = {4,9,11,15,10,12,14,13,3,2,1,0,8,7,6,5};

const int32_t pot_calibration_zero[16] =  {2048, 2048, 2048, 2048,
                                           2048, 2048, 2048, 2048,
                                           2048, 2048, 2048, 2048,
                                           2048, 2048, 2048, 2048};


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
  if (conv_complete[0] == 0 && hadc->Instance == ADC1) {
    conv_complete[0] = 1;
  } else if (conv_complete[1] == 0 && hadc->Instance == ADC2) {
    conv_complete[1] = 1;
  }
}
void fetch_potentiometer_values(uint16_t *pot_values) {
    if (!(conv_complete[0] && conv_complete[1])) {
      return;
    }
    conv_complete[0] = 0;
    conv_complete[1] = 0;
    pot_counter++;
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
}
int32_t get_calibrated_potentiometer_value(uint8_t motor_id, int32_t raw_value) {
    int32_t calibrated_value = (raw_value - pot_calibration_zero[motor_id]);
    return calibrated_value;
}
// Output init settings
void motor_pwm_timers_start(void) {
  for (int i = 0; i < 16; ++i) {
    HAL_TIM_PWM_Start(pwm_timer_handles[i], pwm_timer_channels[i]);
  }
}
// Motor control
void set_motor_direction(uint8_t motor_id, uint16_t dir_value) {
    HAL_GPIO_WritePin(dir_ports[motor_id], dir_pins[motor_id], dir_value ? GPIO_PIN_SET : GPIO_PIN_RESET);
}
void set_motor_power(uint8_t motor_id, uint16_t pwm_value) {
    __HAL_TIM_SET_COMPARE(pwm_timer_handles[motor_id], pwm_timer_channels[motor_id], pwm_value);
}
void set_motor(uint8_t motor_id, int16_t motor_set) {
      set_motor_direction(motor_id, motor_set >= 0 ? 1 : 0);
      uint16_t pwm_value = (uint16_t)(motor_set >= 0 ? motor_set : -motor_set);
      if (pwm_value > 255) {pwm_value = 255;}
      set_motor_power(motor_id, pwm_value);
}



//control by position
pos_res current_position[MOTOR_AMOUNT], desired_position[MOTOR_AMOUNT], last_desired_position[MOTOR_AMOUNT];
int16_t motor_speeds[MOTOR_AMOUNT], motor_calib_fix[MOTOR_AMOUNT] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
int mot = 0, scale = 64;


void get_motor_current_positions(){
	fetch_potentiometer_values(current_position);
}

void fix_motor_speeds(){
	for(int i = 0; i < MOTOR_AMOUNT; i++){
		if(motor_speeds[i] == UP_SPEED && current_position[i] >= desired_position[i]){
			motor_speeds[i] = 0;
		}else if(motor_speeds[i] == DOWN_SPEED && current_position[i] <= desired_position[i]) {
			motor_speeds[i] = 0;
		}
	}
	motor_speed_set();
}

void motor_location_set(void* locations){
	// DEBUG ONLY
	char* debug_locations_arr = (char*)locations;
	pos_res loc = debug_locations_arr[0] - '0';
	for(int i = 0; i < MOTOR_AMOUNT; i++){
		last_desired_position[i] = desired_position[i];
		desired_position[i] = 1048 + (loc *200);
		if(desired_position[i] > last_desired_position[i]){
			motor_speeds[i] = UP_SPEED;
		}else if(desired_position[i] < last_desired_position[i]) {
			motor_speeds[i] = DOWN_SPEED;
		}
	}
	return;
	//REAL CODE
	pos_res* locations_arr = (pos_res*)locations;
	for(int i = 0; i < MOTOR_AMOUNT; i++){
		last_desired_position[i] = desired_position[i];
		desired_position[i] = 1536 + locations_arr[i];
		if(desired_position[i] > last_desired_position[i]){
			motor_speeds[i] = UP_SPEED;
		}else if(desired_position[i] < last_desired_position[i]) {
			motor_speeds[i] = DOWN_SPEED;
		}
	}
}

void motor_speed_set(){
	for(int i = 0; i < MOTOR_AMOUNT; i++){
		set_motor(i, motor_speeds[i]);
	}
}

void debug_init(){
	get_motor_current_positions();
	for(int i = 0; i < MOTOR_AMOUNT; i++){
		desired_position[i] = current_position[i];
		last_desired_position[i] = current_position[i];
		motor_speeds[i] = 0;
	}
}

//zeroing
void zero_motors(){
	for(int i = 0; i < MOTOR_AMOUNT; i++){
		last_desired_position[i] = desired_position[i];
		desired_position[i] = 2048 + motor_calib_fix[i];
		if(desired_position[i] > last_desired_position[i]){
			motor_speeds[i] = UP_SPEED;
		}else if(desired_position[i] < last_desired_position[i]) {
			motor_speeds[i] = DOWN_SPEED;
		}
	}
}

void change_motor(bool right){
	if ((right && mot == 15) || (!right && mot == 0)){
		return;
	}
	if(right){
		mot++;
	} else {
		mot--;
	}
}

void change_scale(bool up){
	if ((up && scale == 256) || (!up && scale == 1)){
		return;
	}
	if(up){
		scale *= 2;
	} else {
		scale /= 2;
	}
}

void change_zero(bool pos){
	//motor_calib_fix
	if (pos && ((motor_calib_fix[mot] + scale) > 512)){
		motor_calib_fix[mot] = 512;
		return;
	}
	if (!pos && ((motor_calib_fix[mot] - scale) < -512)){
		motor_calib_fix[mot] = -512;
		return;
	}
	if(pos){
		motor_calib_fix[mot] += scale;
	} else {
		motor_calib_fix[mot] -= scale;
	}
}

int getmot(){return mot;}
int get_zero_val(int id){return motor_calib_fix[id];}
int getscale(){return scale;}

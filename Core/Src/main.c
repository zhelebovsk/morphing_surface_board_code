/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2025 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "adc.h"
#include "dac.h"
#include "dma.h"
#include "fdcan.h"
#include "i2c.h"
#include "spi.h"
#include "tim.h"
#include "usart.h"
#include "usb_device.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "usbd_cdc_if.h"
#include "board_config.h"
#include "dip.h"
#include "timer_helper.h"
#include "can_helper.h"
#include "motor_helper.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
extern volatile uint8_t usb_rx_buf[4];
extern volatile uint8_t usb_rx_flag;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_ADC1_Init();
  MX_DAC1_Init();
  MX_FDCAN1_Init();
  MX_I2C1_Init();
  MX_TIM1_Init();
  MX_TIM3_Init();
  MX_TIM4_Init();
  MX_TIM8_Init();
  MX_USART1_UART_Init();
  MX_USART2_UART_Init();
  MX_USB_Device_Init();
  MX_ADC2_Init();
  MX_TIM2_Init();
  MX_TIM20_Init();
  MX_SPI1_Init();
  /* USER CODE BEGIN 2 */
  //user variables
  uint8_t dip_id = 255;
  uint16_t pot_values[16] = {0};
  char msg[128] = "";
  uint16_t dir_values[16] = {0};
  uint16_t pwm_values[16] = {0};
  int8_t k = 0;
  int8_t new_k = 0;
  uint32_t current_time_us = 0;
  uint32_t current_time_s = 0;
  // FPGA clock
  fpga_timer_start();
  // CAN bus
  HAL_FDCAN_Start(&hfdcan1);
  send_can_hello(dip_id);
  // Board ID settings
  dip_id = Read_DIP_ID();
  // Potentiometer initialization and buffers 
  Start_ADC_DMA();
  // Communication variable
  motor_power_setup(1);
  motor_pwm_timers_start();

  // onboard time
  HAL_TIM_Base_Start(&htim2);
  current_time_us = get_time_us();
  current_time_s = current_time_us / 1000000;
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */

  // EEPROM test
  // uint8_t write_val = 0xFF;
  // uint8_t read_val = 0x00;
  // uint16_t test_address = 0x010;
  // EEPROM_Write(test_address, write_val);
  // EEPROM_Read(test_address, &read_val);
  char *msg_usart = "Hello World from STM32!\r\n";
  uint8_t rx_buf[1];
  while (1)
  {
    // HAL_GPIO_WritePin(RS485_CONTROL_GPIO_Port, RS485_CONTROL_Pin, GPIO_PIN_SET); // Set pin high
    HAL_UART_Receive_IT(&huart2, rx_buf, 1);
    // HAL_UART_Transmit(&huart2, (uint8_t*)msg_usart, strlen(msg_usart), 100);
    delay_ms(100); // Main loop delay, 100 ms
    send_can_hello(dip_id);
    fetch_potentiometer_values(pot_values);
    current_time_us = get_time_us();
    current_time_s = current_time_us / 1000000;
    if (usb_rx_flag) {
        usb_rx_flag = 0;  // Clear flag
        new_k = (int8_t)atoi((char*)usb_rx_buf);
        if (new_k >= 0 && new_k < 16) {
            k = new_k;
        }
    }
    for (int i = 0; i < 16; ++i) {
        pwm_values[i] = 150;
        dir_values[i] = 1;
    }
    // pwm_values[k] = (current_time_us/2000) % 255;
    // pwm_values[k] = 0; // Example: minimum  power is 7/255, minimum starting power
    // dir_values[k] = current_time_s % 2; // Example: toggle direction every 2 seconds
    set_motor_directions(dir_values);
    set_motor_power(pwm_values);  
    // snprintf(msg, sizeof(msg),
    //    "ID: %u, TIME: %lu us, POTs: %u %u %u %u %u %u %u %u %u %u %u %u %u %u %u %u\r\n",
    //    dip_id, current_time_us,
    //    pot_values[0],  pot_values[1],  pot_values[2],  pot_values[3],
    //    pot_values[4],  pot_values[5],  pot_values[6],  pot_values[7],
    //    pot_values[8],  pot_values[9],  pot_values[10], pot_values[11],
    //    pot_values[12], pot_values[13], pot_values[14], pot_values[15]);
    // snprintf(msg, sizeof(msg),
    //    "ID: %u, TIME: %lu us, POT[%d]: %u, DIR[%d]: %u, PWM[%d]: %u\r\n",
    //    dip_id, current_time_us,
    //    k, pot_values[k],
    //    k, dir_values[k],
    //    k, pwm_values[k]);
    snprintf(msg, sizeof(msg),
    "RX: %02X\r\n",
      rx_buf[0]
    );
    CDC_Transmit_FS((uint8_t*)msg, strlen(msg));

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI48|RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSI48State = RCC_HSI48_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV2;
  RCC_OscInitStruct.PLL.PLLN = 40;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV6;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */

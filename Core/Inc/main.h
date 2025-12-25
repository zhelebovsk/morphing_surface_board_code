/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
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

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32g4xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define PWM_13_Pin GPIO_PIN_2
#define PWM_13_GPIO_Port GPIOE
#define PWM_14_Pin GPIO_PIN_3
#define PWM_14_GPIO_Port GPIOE
#define PWM_15_Pin GPIO_PIN_4
#define PWM_15_GPIO_Port GPIOE
#define PWM_16_Pin GPIO_PIN_5
#define PWM_16_GPIO_Port GPIOE
#define FPGA_CLOCK_Pin GPIO_PIN_6
#define FPGA_CLOCK_GPIO_Port GPIOE
#define nALARM_1_4_Pin GPIO_PIN_13
#define nALARM_1_4_GPIO_Port GPIOC
#define nALARM_1_4_EXTI_IRQn EXTI15_10_IRQn
#define nALARM_9_12_Pin GPIO_PIN_14
#define nALARM_9_12_GPIO_Port GPIOC
#define nALARM_9_12_EXTI_IRQn EXTI15_10_IRQn
#define nALARM_13_16_Pin GPIO_PIN_15
#define nALARM_13_16_GPIO_Port GPIOC
#define nALARM_13_16_EXTI_IRQn EXTI15_10_IRQn
#define CTRL_6V_L_Pin GPIO_PIN_9
#define CTRL_6V_L_GPIO_Port GPIOF
#define CTRL_6V_H_Pin GPIO_PIN_10
#define CTRL_6V_H_GPIO_Port GPIOF
#define POT_16_Pin GPIO_PIN_0
#define POT_16_GPIO_Port GPIOC
#define POT_15_Pin GPIO_PIN_1
#define POT_15_GPIO_Port GPIOC
#define POT_14_Pin GPIO_PIN_2
#define POT_14_GPIO_Port GPIOC
#define POT_13_Pin GPIO_PIN_3
#define POT_13_GPIO_Port GPIOC
#define POT_12_Pin GPIO_PIN_0
#define POT_12_GPIO_Port GPIOA
#define POT_11_Pin GPIO_PIN_1
#define POT_11_GPIO_Port GPIOA
#define POT_10_Pin GPIO_PIN_2
#define POT_10_GPIO_Port GPIOA
#define POT_9_Pin GPIO_PIN_3
#define POT_9_GPIO_Port GPIOA
#define DAC_1_Pin GPIO_PIN_4
#define DAC_1_GPIO_Port GPIOA
#define DAC_2_Pin GPIO_PIN_5
#define DAC_2_GPIO_Port GPIOA
#define POT_8_Pin GPIO_PIN_6
#define POT_8_GPIO_Port GPIOA
#define POT_7_Pin GPIO_PIN_7
#define POT_7_GPIO_Port GPIOA
#define DIP_1_Pin GPIO_PIN_5
#define DIP_1_GPIO_Port GPIOC
#define POT_6_Pin GPIO_PIN_0
#define POT_6_GPIO_Port GPIOB
#define POT_5_Pin GPIO_PIN_1
#define POT_5_GPIO_Port GPIOB
#define POT_X_Pin GPIO_PIN_2
#define POT_X_GPIO_Port GPIOB
#define DIR_1_Pin GPIO_PIN_7
#define DIR_1_GPIO_Port GPIOE
#define DIR_2_Pin GPIO_PIN_8
#define DIR_2_GPIO_Port GPIOE
#define PWM_1_Pin GPIO_PIN_9
#define PWM_1_GPIO_Port GPIOE
#define DIR_3_Pin GPIO_PIN_10
#define DIR_3_GPIO_Port GPIOE
#define PWM_2_Pin GPIO_PIN_11
#define PWM_2_GPIO_Port GPIOE
#define DIR_4_Pin GPIO_PIN_12
#define DIR_4_GPIO_Port GPIOE
#define PWM_3_Pin GPIO_PIN_13
#define PWM_3_GPIO_Port GPIOE
#define PWM_4_Pin GPIO_PIN_14
#define PWM_4_GPIO_Port GPIOE
#define DIR_5_Pin GPIO_PIN_15
#define DIR_5_GPIO_Port GPIOE
#define DIR_6_Pin GPIO_PIN_10
#define DIR_6_GPIO_Port GPIOB
#define POT_3_Pin GPIO_PIN_11
#define POT_3_GPIO_Port GPIOB
#define POT_2_Pin GPIO_PIN_12
#define POT_2_GPIO_Port GPIOB
#define DIR_7_Pin GPIO_PIN_13
#define DIR_7_GPIO_Port GPIOB
#define POT_1_Pin GPIO_PIN_14
#define POT_1_GPIO_Port GPIOB
#define DIR_8_Pin GPIO_PIN_15
#define DIR_8_GPIO_Port GPIOB
#define DIR_9_Pin GPIO_PIN_8
#define DIR_9_GPIO_Port GPIOD
#define DIR_10_Pin GPIO_PIN_9
#define DIR_10_GPIO_Port GPIOD
#define DIR_11_Pin GPIO_PIN_10
#define DIR_11_GPIO_Port GPIOD
#define DIR_12_Pin GPIO_PIN_11
#define DIR_12_GPIO_Port GPIOD
#define PWM_9_Pin GPIO_PIN_12
#define PWM_9_GPIO_Port GPIOD
#define PWM_10_Pin GPIO_PIN_13
#define PWM_10_GPIO_Port GPIOD
#define PWM_11_Pin GPIO_PIN_14
#define PWM_11_GPIO_Port GPIOD
#define PWM_12_Pin GPIO_PIN_15
#define PWM_12_GPIO_Port GPIOD
#define PWM_5_Pin GPIO_PIN_6
#define PWM_5_GPIO_Port GPIOC
#define PWM_6_Pin GPIO_PIN_7
#define PWM_6_GPIO_Port GPIOC
#define PWM_7_Pin GPIO_PIN_8
#define PWM_7_GPIO_Port GPIOC
#define PWM_8_Pin GPIO_PIN_9
#define PWM_8_GPIO_Port GPIOC
#define DIR_13_Pin GPIO_PIN_8
#define DIR_13_GPIO_Port GPIOA
#define DIR_14_Pin GPIO_PIN_9
#define DIR_14_GPIO_Port GPIOA
#define DIR_15_Pin GPIO_PIN_10
#define DIR_15_GPIO_Port GPIOA
#define DIR_16_Pin GPIO_PIN_10
#define DIR_16_GPIO_Port GPIOC
#define DIP_6_Pin GPIO_PIN_11
#define DIP_6_GPIO_Port GPIOC
#define DIP_5_Pin GPIO_PIN_12
#define DIP_5_GPIO_Port GPIOC
#define DIP_4_Pin GPIO_PIN_2
#define DIP_4_GPIO_Port GPIOD
#define DIP_3_Pin GPIO_PIN_3
#define DIP_3_GPIO_Port GPIOD
#define RS485_CONTROL_Pin GPIO_PIN_4
#define RS485_CONTROL_GPIO_Port GPIOD
#define RS485_TX_Pin GPIO_PIN_5
#define RS485_TX_GPIO_Port GPIOD
#define RS485_RX_Pin GPIO_PIN_6
#define RS485_RX_GPIO_Port GPIOD
#define DIP_2_Pin GPIO_PIN_7
#define DIP_2_GPIO_Port GPIOD
#define nALARM_5_8_Pin GPIO_PIN_7
#define nALARM_5_8_GPIO_Port GPIOB
#define nALARM_5_8_EXTI_IRQn EXTI9_5_IRQn
#define BOOT_Pin GPIO_PIN_8
#define BOOT_GPIO_Port GPIOB
#define SPI1_CS_Pin GPIO_PIN_0
#define SPI1_CS_GPIO_Port GPIOE

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */

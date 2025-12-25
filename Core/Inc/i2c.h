/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    i2c.h
  * @brief   This file contains all the function prototypes for
  *          the i2c.c file
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
#ifndef __I2C_H__
#define __I2C_H__

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

extern I2C_HandleTypeDef hi2c1;

/* USER CODE BEGIN Private defines */
#define EEPROM_ADDR 0xA0
/* USER CODE END Private defines */

void MX_I2C1_Init(void);

/* USER CODE BEGIN Prototypes */
HAL_StatusTypeDef EEPROM_Write(uint16_t MemAddr, uint8_t Data);
HAL_StatusTypeDef EEPROM_Read(uint16_t MemAddr, uint8_t *pData);
HAL_StatusTypeDef EEPROM_PageWrite(uint16_t Addr, uint8_t *pData, uint16_t Size);
HAL_StatusTypeDef EEPROM_Read_Sequential(uint16_t Addr, uint8_t *pData, uint16_t Size);
HAL_StatusTypeDef EEPROM_FullRead(uint8_t *pBuffer);
/* USER CODE END Prototypes */

#ifdef __cplusplus
}
#endif

#endif /* __I2C_H__ */


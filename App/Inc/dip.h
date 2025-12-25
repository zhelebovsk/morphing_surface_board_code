#ifndef DIP_H
#define DIP_H

#include "stm32g4xx_hal.h"
#include "board_config.h"
// #include "main.h"     // brings in DIP_x_Pin and DIP_x_GPIO_Port macros

uint8_t Read_DIP_ID(void);

#endif // DIP_H
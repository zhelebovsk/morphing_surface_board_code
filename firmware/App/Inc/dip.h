#ifndef DIP_H
#define DIP_H

#include "stm32g4xx_hal.h"
#include "board_config.h"

uint8_t Read_DIP_ID(void);
uint16_t Read_Board_ID(void);

#endif // DIP_H
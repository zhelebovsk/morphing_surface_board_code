#ifndef CAN_HELPER_H
#define CAN_HELPER_H

#include "stm32g4xx_hal.h"
#include "fdcan.h"
#include "board_config.h"
#include "motor_helper.h"

HAL_StatusTypeDef CAN_Send(uint32_t board_id, void *data, uint32_t dlc_len);
HAL_StatusTypeDef CAN_Send_ID(uint32_t board_id);
void CAN_Send_Pot(uint32_t board_id, uint16_t *pot_values);
void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef *hfdcan, uint32_t RxFifo0ITs);


#endif // CAN_HELPER_H

#ifndef CAN_HELPER_H
#define CAN_HELPER_H

#include "stm32g4xx_hal.h"
#include "fdcan.h"
#include "board_config.h"
#include "motor_helper.h"
#include "timer_helper.h"

// 0 = classic CAN (default). 1 = CAN FD with bit-rate switching: 1 Mbit/s
// arbitration, 2 Mbit/s data. Must match CAN_FD in cantest/config.py and
// `./can_start_kvaser.sh fd` (docs/OPEN_ISSUES.md #2).
#define CAN_FD_ENABLED 0

void CAN_Configure_FD(void);
HAL_StatusTypeDef CAN_Send(uint32_t board_id, void *data, uint32_t dlc_len);
HAL_StatusTypeDef CAN_Send_ID(uint32_t board_id);
void CAN_Send_Pot(uint32_t board_id, uint16_t *pot_values);
void CAN_Stream_Update(void);
void CAN_Check_Bus_Off(void);
void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef *hfdcan, uint32_t RxFifo0ITs);


#endif // CAN_HELPER_H

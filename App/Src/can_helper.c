#include "can_helper.h"


HAL_StatusTypeDef CAN_Send(uint32_t board_id, void *data, uint32_t dlc_len)
{
    FDCAN_TxHeaderTypeDef tx_header;
    tx_header.Identifier = board_id;
    tx_header.IdType = FDCAN_STANDARD_ID;
    tx_header.TxFrameType = FDCAN_DATA_FRAME;
    tx_header.DataLength = dlc_len; // e.g., FDCAN_DLC_BYTES_8
    tx_header.ErrorStateIndicator = FDCAN_ESI_ACTIVE;
    tx_header.BitRateSwitch = FDCAN_BRS_OFF;
    tx_header.FDFormat = FDCAN_CLASSIC_CAN;
    tx_header.TxEventFifoControl = FDCAN_NO_TX_EVENTS;
    tx_header.MessageMarker = 0;
    return HAL_FDCAN_AddMessageToTxFifoQ(&hfdcan1, &tx_header, (uint8_t*)data);
}

HAL_StatusTypeDef CAN_Send_ID(uint32_t board_id)
{
    return CAN_Send(board_id, &board_id, FDCAN_DLC_BYTES_1);
}

void CAN_Send_Pot(uint32_t board_id, uint16_t *pot_values) {
    CAN_Send(board_id, &pot_values[0], FDCAN_DLC_BYTES_8); 
    CAN_Send(board_id, &pot_values[8], FDCAN_DLC_BYTES_8);
}

void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef *hfdcan, uint32_t RxFifo0ITs) {
  if (RxFifo0ITs & FDCAN_IT_RX_FIFO0_NEW_MESSAGE) {
    FDCAN_RxHeaderTypeDef header;
    uint8_t data[8];
    HAL_FDCAN_GetRxMessage(hfdcan, FDCAN_RX_FIFO0, &header, data);
    if ((data[0] == 0x1) && (header.Identifier == board_id)) { 
    //   for(int i = 0; i < 7; i++) motor_location_set(active_motors[i], data[i+1]*4);
      for(int i = 0; i < 7; i++) set_motor(active_motors[i], data[i+1]*2-255);
    }
    if ((data[0] == 0x2) && (header.Identifier == board_id)) { 
    //   for(int i = 0; i < 7; i++) motor_location_set(active_motors[i+7], data[i+1]*4);
        for(int i = 0; i < 7; i++) set_motor(active_motors[i+7], data[i+1]*2-255);
    }
  }
}



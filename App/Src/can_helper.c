#include "can_helper.h"

void send_can_hello(uint8_t dip_id)
{
    FDCAN_TxHeaderTypeDef tx_header;
    uint8_t tx_data[6] = {'H','e','l','l','o', dip_id};

    tx_header.Identifier = 0x100 + dip_id;       // Your board ID in CAN space
    tx_header.IdType = FDCAN_STANDARD_ID; //0u
    tx_header.TxFrameType = FDCAN_DATA_FRAME; //0u
    tx_header.DataLength = FDCAN_DLC_BYTES_6; //6u
    tx_header.ErrorStateIndicator = FDCAN_ESI_ACTIVE; //0u
    tx_header.BitRateSwitch = FDCAN_BRS_OFF; //0u
    tx_header.FDFormat = FDCAN_CLASSIC_CAN; //0u
    tx_header.TxEventFifoControl = FDCAN_NO_TX_EVENTS; //0u
    tx_header.MessageMarker = 0;

    HAL_StatusTypeDef debug_temp = HAL_FDCAN_AddMessageToTxFifoQ(&hfdcan1, &tx_header, tx_data);
    int a = 15;
    int b = 2;
    a = a - b;
}
